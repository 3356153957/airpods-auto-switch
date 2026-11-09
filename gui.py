"""Light control panel and the Tk UI dispatcher used by the tray process."""
import json
import queue
import time
import gc
import threading
import webbrowser
from tkinter import messagebox
import customtkinter as ctk
from bluetooth_manager import BluetoothManager
from settings_manager import settings, SETTINGS_DIR, STATUS_FILE, send_command, write_json
from ui_styles import BG, SURFACE, TEXT, MUTED, BORDER, BLUE, BLUE_SOFT, GREEN, FONT, icon, button, apply_native_chrome
from app_version import VERSION, RELEASES_URL

TITLE = 'AirPods 自动接管'


class SettingsGUI(ctk.CTk):
    def __init__(self, background=False, preview=False):
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        super().__init__()
        self.withdraw()
        self.title('AirPods 界面预览' if preview else TITLE)
        try:
            self._form_state = json.loads((SETTINGS_DIR / 'panel-state.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self._form_state = {}
        from ui_popups import monitor_workarea
        work = monitor_workarea()
        scale = self._get_window_scaling()
        available_width = max(520, int((work.right-work.left) / scale)-32)
        available_height = max(320, int((work.bottom-work.top) / scale)-52)
        size = self._form_state.get('size', [760, 780])
        self._normal_size = [min(max(520, int(size[0])), available_width), min(max(320, int(size[1])), available_height)]
        self.geometry(f'{self._normal_size[0]}x{self._normal_size[1]}')
        self.minsize(min(650, available_width), min(650, available_height))
        self.configure(fg_color=BG)
        self.preview = preview
        self.tasks = queue.SimpleQueue()
        self._menu = None
        self._toast = None
        self._hidden = background
        self._restore_state = 'zoomed' if self._form_state.get('window_state') == 'zoomed' else 'normal'
        self._tray_hint_shown = False
        self._closed = False
        self._view_built = False
        self._view_roots = ()
        self._unload_job = None
        self.on_background_request = None
        self._checking_update = False
        self._update_result = None
        cfg = settings.snapshot()
        self._form_base = {key: cfg[key] for key in ('DEVICE_NAME', 'AUDIO_START_DELAY', 'APP_BLACKLIST')}
        self.enabled = ctk.BooleanVar(value=cfg['AUTO_CONNECT_ENABLED'])
        self.notifications = ctk.BooleanVar(value=cfg['NOTIFICATIONS_ENABLED'])
        self.tray_hint = ctk.BooleanVar(value=cfg.get('TRAY_HINT_ENABLED', True))
        self.delay = ctk.StringVar(value=self._delay_text(cfg['AUDIO_START_DELAY']))
        self.device = ctk.StringVar(value=cfg['DEVICE_NAME'])
        if not self.device.get():
            devices = BluetoothManager.paired_devices()
            if devices:
                self.device.set(devices[0])
        self.blacklist = ctk.StringVar(value=', '.join(cfg['APP_BLACKLIST']))
        self._advanced_open = bool(self._form_state.get('advanced_open', False))
        self._saved_signature = (cfg['DEVICE_NAME'].strip(), self._delay_text(cfg['AUDIO_START_DELAY']), ', '.join(cfg['APP_BLACKLIST']))
        if self._form_state.get('base') == self._form_base:
            draft = self._form_state.get('draft', {})
            self.device.set(draft.get('device', self.device.get()))
            self.delay.set(draft.get('delay', self.delay.get()))
            self.blacklist.set(draft.get('blacklist', self.blacklist.get()))
            self._saved_signature = tuple(self._form_state.get('saved_signature', self._saved_signature))
        if not background:
            self._build_view()
        for variable in (self.device, self.delay, self.blacklist):
            variable.trace_add('write', self._mark_dirty)
        self.protocol('WM_DELETE_WINDOW', self._hide)
        self.bind('<Unmap>', self._on_unmap)
        self.bind('<Configure>', self._remember_state)
        self.bind('<Control-s>', lambda _: self.save_settings())
        apply_native_chrome(self)
        self.after(150, self._refresh_status)
        self.after(80, self._process_tasks)
        if not background:
            self.after(250, lambda: self._show_window() if not self._hidden else None)

    @staticmethod
    def _delay_text(value):
        return f'{float(value):g} 秒'

    def label(self, parent, text, size=12, color=TEXT, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=color, font=ctk.CTkFont(FONT, size, 'bold' if bold else 'normal'), **kwargs)

    def _card(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=SURFACE, border_color=BORDER, border_width=1, corner_radius=12)
        frame.pack(fill='x', padx=4, pady=(0, 12))
        return frame

    def _icon_label(self, parent, symbol, text, size=14):
        return ctk.CTkLabel(parent, text=text, image=icon(symbol, 18), compound='left', anchor='w', text_color=TEXT, font=ctk.CTkFont(FONT, size, 'bold'))

    def _build(self):
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=30, pady=(22, 17))
        badge = ctk.CTkFrame(header, width=44, height=44, corner_radius=12, fg_color=BLUE_SOFT)
        badge.pack(side='left', padx=(0, 13)); badge.pack_propagate(False)
        ctk.CTkLabel(badge, text='', image=icon('headphones', 26)).pack(expand=True)
        titles = ctk.CTkFrame(header, fg_color='transparent')
        titles.pack(side='left')
        self.label(titles, 'AirPods 自动接管', 23, bold=True).pack(anchor='w')
        self.label(titles, '设备与连接', 12, MUTED).pack(anchor='w', pady=(1, 0))
        self.header_status = self.label(header, '本机运行', 11, MUTED)
        self.header_status.pack(side='right', anchor='center')

        self.body = ctk.CTkScrollableFrame(self, fg_color='transparent', scrollbar_button_color='#CBD5DF', scrollbar_button_hover_color='#AFBECC')
        self.body.pack(fill='both', expand=True, padx=24)
        hero = self._card(self.body)
        self.label(hero, '当前设备', 11, MUTED).pack(anchor='w', padx=22, pady=(17, 7))
        device_row = ctk.CTkFrame(hero, fg_color='transparent')
        device_row.pack(fill='x', padx=22)
        self.device_menu = ctk.CTkComboBox(device_row, values=BluetoothManager.paired_devices() or [self.device.get()], variable=self.device,
            font=ctk.CTkFont(FONT, 17, 'bold'), dropdown_font=ctk.CTkFont(FONT, 13), height=38, fg_color=SURFACE,
            border_color=BORDER, button_color='#EDF2F7', button_hover_color='#E0EAF5', text_color=TEXT, dropdown_fg_color=SURFACE, dropdown_text_color=TEXT)
        self.device_menu.pack(side='left', fill='x', expand=True)
        self.refresh_button = button(device_row, '刷新', self._refresh_devices, 'refresh', width=76)
        self.refresh_button.pack(side='right', padx=(10, 0))
        state_row = ctk.CTkFrame(hero, fg_color='transparent')
        state_row.pack(fill='x', padx=22, pady=(10, 17))
        self.status = self.label(state_row, '正在读取连接状态…', 12, BLUE)
        self.status.pack(side='left')
        self.connect_button = button(state_row, '立即连接', lambda: self._command('connect'), 'connect', width=112)
        self.connect_button.pack(side='right')

        auto = self._card(self.body)
        first = ctk.CTkFrame(auto, fg_color='transparent')
        first.pack(fill='x', padx=22, pady=(17, 2))
        self._icon_label(first, 'power', '电脑播放时自动接管').pack(side='left')
        self.auto_switch = ctk.CTkSwitch(first, text='', variable=self.enabled, command=self._toggle, width=44, switch_width=40, switch_height=22,
            progress_color=BLUE, fg_color='#CAD4DE', button_color=SURFACE, button_hover_color='#F0F5FA')
        self.auto_switch.pack(side='right')
        self.label(auto, '需要时打开，耳机会在电脑开始播放后连接过来。', 12, MUTED).pack(anchor='w', padx=22, pady=(3, 12))
        ctk.CTkFrame(auto, height=1, fg_color='#EDF0F4').pack(fill='x', padx=22)
        timing = ctk.CTkFrame(auto, fg_color='transparent')
        timing.pack(fill='x', padx=22, pady=(12, 15))
        timing_text = ctk.CTkFrame(timing, fg_color='transparent')
        timing_text.pack(side='left')
        self.label(timing_text, '播放确认时间', 12).pack(anchor='w')
        self.label(timing_text, '过滤短促声音，连接另需几秒', 11, MUTED).pack(anchor='w')
        self.delay_control = ctk.CTkSegmentedButton(timing, values=['0.5 秒', '1 秒', '2 秒', '3 秒'], variable=self.delay,
            height=32, corner_radius=6, font=ctk.CTkFont(FONT, 12), selected_color='#D5E5FA', selected_hover_color='#C6DCF8',
            fg_color='#EDF2F7', unselected_color='#EDF2F7', unselected_hover_color='#DEE8F4', text_color=TEXT, text_color_disabled=MUTED, dynamic_resizing=False, width=240)
        self.delay_control.pack(side='right', padx=(12, 0))

        preferences = self._card(self.body)
        self._preference_row(preferences, 'bell', '右下角连接通知', '显示连接进度和结果', self.notifications, self._toggle_notifications, first=True)
        ctk.CTkFrame(preferences, height=1, fg_color='#EDF0F4').pack(fill='x', padx=22)
        self._preference_row(preferences, 'tray', '收起到托盘时提醒', '首次收起后显示 5 秒，可一键恢复窗口', self.tray_hint, self._toggle_tray_hint)

        advanced = self._card(self.body)
        self.advanced_button = ctk.CTkButton(advanced, text='高级设置', image=icon('sliders', 18), compound='left', anchor='w',
            command=self._toggle_advanced, height=48, corner_radius=10, fg_color=SURFACE, hover_color='#F7F9FC', text_color=TEXT, font=ctk.CTkFont(FONT, 13, 'bold'))
        self.advanced_button.pack(fill='x', padx=9, pady=4)
        self.advanced_area = ctk.CTkFrame(advanced, fg_color='transparent')
        self.label(self.advanced_area, '忽略这些应用', 12, bold=True).pack(anchor='w', padx=22, pady=(0, 7))
        self.blacklist_entry = ctk.CTkEntry(self.advanced_area, textvariable=self.blacklist, height=36, corner_radius=7, fg_color='#FAFBFD', border_color='#DCE2E8', text_color=TEXT, font=ctk.CTkFont(FONT, 12))
        self.blacklist_entry.pack(fill='x', padx=22)
        self.label(self.advanced_area, '进程名以逗号分隔，默认忽略动态壁纸。\n系统提示音、麦克风和已静音应用不会触发接管。', 11, MUTED, justify='left').pack(anchor='w', padx=22, pady=(6, 12))
        actions = ctk.CTkFrame(self.advanced_area, fg_color='transparent')
        actions.pack(fill='x', padx=22, pady=(0, 17))
        button(actions, '测试通知', lambda: self._command('test_notification'), 'bell', width=116).pack(side='left')
        button(actions, '断开并暂停', self._disconnect, 'disconnect', width=128).pack(side='right')

        updates = self._card(self.body)
        update_row = ctk.CTkFrame(updates, fg_color='transparent')
        update_row.pack(fill='x', padx=22, pady=(14, 5))
        self._icon_label(update_row, 'info', f'版本与更新  ·  v{VERSION}', 13).pack(side='left')
        self.update_button = button(update_row, '检测更新', self._check_updates, 'refresh', width=110)
        self.update_button.pack(side='right')
        self.update_status = self.label(updates, '手动检查 GitHub 正式版本', 11, MUTED, anchor='w', justify='left')
        self.update_status.pack(fill='x', padx=22, pady=(0, 12))
        self.release_button = button(updates, '前往发布页', self._open_release, 'chevron', width=130)
        self._render_update()

        footer = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        footer.pack(fill='x', side='bottom', pady=(10, 0), before=self.body._parent_frame)
        ctk.CTkFrame(footer, height=1, fg_color=BORDER).pack(fill='x')
        footer_row = ctk.CTkFrame(footer, fg_color='transparent')
        footer_row.pack(fill='x', padx=30, pady=16)
        self.feedback = self.label(footer_row, '设置保存在本机', 11, MUTED)
        self.feedback.pack(side='left')
        self.save_button = button(footer_row, '保存设置', self.save_settings, 'check', primary=True, width=118)
        self.save_button.pack(side='right')
        button(footer_row, '收起到托盘', self._hide, 'tray', width=124).pack(side='right', padx=(10, 10))

    def _build_view(self):
        if self._view_built:
            return
        previous = set(self.winfo_children())
        advanced = self._advanced_open
        self._build()
        self._view_roots = tuple(child for child in self.winfo_children() if child not in previous)
        self._view_built = True
        if advanced:
            self._advanced_open = False
            self._toggle_advanced()
        self._mark_dirty()

    def _unload_view(self):
        self._unload_job = None
        if not self._hidden or not self._view_built:
            return
        for child in self._view_roots:
            child.destroy()
        self._view_roots = ()
        for attribute in ('body', 'header_status', 'device_menu', 'refresh_button', 'status', 'connect_button', 'auto_switch',
                          'delay_control', 'advanced_button', 'advanced_area', 'blacklist_entry', 'feedback', 'save_button'):
            setattr(self, attribute, None)
        self.update_button = self.update_status = self.release_button = None
        self._view_built = False
        for attribute in ('_toast', '_menu'):
            popup = getattr(self, attribute)
            if popup is not None and not popup.winfo_exists():
                setattr(self, attribute, None)
        gc.collect()
        if self.on_background_request:
            write_json(SETTINGS_DIR / 'panel-state.json', {'base': self._form_base,
                'draft': {'device': self.device.get(), 'delay': self.delay.get(), 'blacklist': self.blacklist.get()},
                'saved_signature': self._saved_signature, 'advanced_open': self._advanced_open,
                'window_state': self._restore_state, 'size': self._normal_size})
            self.on_background_request()

    def _preference_row(self, parent, symbol, title, description, variable, callback, first=False):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', padx=22, pady=(14, 13))
        ctk.CTkLabel(row, text='', image=icon(symbol, 19, MUTED)).pack(side='left', padx=(0, 12))
        text = ctk.CTkFrame(row, fg_color='transparent')
        text.pack(side='left')
        self.label(text, title, 12, bold=True).pack(anchor='w')
        self.label(text, description, 11, MUTED).pack(anchor='w', pady=(1, 0))
        ctk.CTkSwitch(row, text='', variable=variable, command=callback, width=44, switch_width=40, switch_height=22,
            progress_color=BLUE, fg_color='#CAD4DE', button_color=SURFACE, button_hover_color='#F0F5FA').pack(side='right')

    def _signature(self):
        return (self.device.get().strip(), self.delay.get(), self.blacklist.get().strip())

    def _mark_dirty(self, *_):
        if not self._view_built:
            return
        if self._signature() != self._saved_signature:
            self.feedback.configure(text='有未保存的更改', text_color=BLUE)
        else:
            self.feedback.configure(text='设置保存在本机', text_color=MUTED)

    def _toggle_advanced(self):
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.advanced_area.pack(fill='x')
            self.advanced_button.configure(text='收起高级设置')
        else:
            self.advanced_area.pack_forget()
            self.advanced_button.configure(text='高级设置')

    def _refresh_devices(self):
        names = BluetoothManager.paired_devices()
        if self.device.get() not in names:
            names.insert(0, self.device.get())
        self.device_menu.configure(values=names)
        self.feedback.configure(text='设备列表已刷新', text_color=GREEN)

    def _check_updates(self):
        if self._checking_update:
            return
        self._checking_update = True
        self._render_update()
        def worker():
            from update_checker import check_for_updates
            self.tasks.put(('update_result', (check_for_updates(),)))
        threading.Thread(target=worker, name='ReleaseCheck', daemon=True).start()

    def _render_update(self):
        self.update_button.configure(text='正在检查…' if self._checking_update else '检测更新',
                                     state='disabled' if self._checking_update else 'normal')
        result = self._update_result
        text = '正在连接 GitHub…' if self._checking_update else result.message if result else '手动检查 GitHub 正式版本'
        color = MUTED if self._checking_update or not result else BLUE if result.status == 'available' else GREEN if result.status == 'current' else MUTED
        self.update_status.configure(text=text, text_color=color)
        if result and not self._checking_update and result.status != 'current':
            self.release_button.configure(text='下载新版本' if result.status == 'available' else '前往发布页')
            self.release_button.pack(anchor='w', padx=22, pady=(0, 14))
        else:
            self.release_button.pack_forget()

    def _open_release(self):
        url = self._update_result.url if self._update_result and self._update_result.url else RELEASES_URL
        if not webbrowser.open(url):
            self.update_status.configure(text='浏览器未能打开，请在 GitHub 项目页查看 Releases。', text_color=MUTED)

    def _command(self, action):
        if self.preview:
            self.feedback.configure(text='界面预览，不操作耳机', text_color=MUTED)
            return
        send_command(action)

    def _toggle(self):
        if not self.preview:
            if self.enabled.get() and not settings.get('DEVICE_NAME'):
                self.enabled.set(False)
                messagebox.showinfo('请先保存耳机', '请选择目标耳机，点击“保存设置”后再开启自动接管。', parent=self)
                return
            settings.set('AUTO_CONNECT_ENABLED', self.enabled.get())

    def _toggle_notifications(self):
        if not self.preview:
            settings.set('NOTIFICATIONS_ENABLED', self.notifications.get())

    def _toggle_tray_hint(self):
        if not self.preview:
            settings.set('TRAY_HINT_ENABLED', self.tray_hint.get())

    def _disconnect(self):
        self.enabled.set(False)
        self._toggle()
        self._command('disconnect')

    def save_settings(self):
        name = self.device.get().strip()
        if not name:
            messagebox.showerror('请填写耳机名称', '请输入 Windows 蓝牙设置中显示的完整名称。', parent=self)
            self.device_menu.focus_set()
            return
        if not self.preview:
            settings.update({'DEVICE_NAME': name, 'AUDIO_START_DELAY': float(self.delay.get().split()[0]),
                'APP_BLACKLIST': [p.strip().casefold() for p in self.blacklist.get().replace('，', ',').split(',') if p.strip()]})
            current = settings.snapshot()
            self._form_base = {key: current[key] for key in self._form_base}
        self._saved_signature = self._signature()
        self.feedback.configure(text='已保存，立即生效', text_color=GREEN)

    def _refresh_status(self):
        if self._closed:
            return
        if self._hidden or not self._view_built:
            self.after(3000, self._refresh_status)
            return
        try:
            data = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
            running = time.time() - data['time'] < 30
            text = data['state'] if running else '后台未运行，请重新打开程序'
        except (OSError, ValueError, KeyError):
            text, running = '正在等待后台启动…', False
        color = GREEN if text == '已连接到电脑' else '#AA6C15' if '正在连接' in text else '#B34B50' if text == '连接未成功' else MUTED if '关闭' in text else BLUE
        self.status.configure(text=text, text_color=color)
        self.header_status.configure(text='本机运行' if running else '等待后台', text_color=MUTED)
        cfg = settings.snapshot()
        if not self.preview:
            self.enabled.set(bool(cfg['AUTO_CONNECT_ENABLED']))
            self.notifications.set(bool(cfg['NOTIFICATIONS_ENABLED']))
            self.tray_hint.set(bool(cfg.get('TRAY_HINT_ENABLED', True)))
        self.after(1000, self._refresh_status)

    def dispatch(self, action, *args):
        if getattr(self, 'quick_menu', False) and action in ('show_settings', 'quit'):
            send_command(action)
            self.tasks.put(('quit', ()))
            return
        self.tasks.put((action, args))

    def _process_tasks(self):
        if self._closed:
            return
        while not self.tasks.empty():
            action, args = self.tasks.get()
            if action == 'show_settings':
                self._show_window()
            elif action == 'hide_settings':
                self._hide()
            elif action == 'tray_menu':
                from ui_popups import TrayMenu
                if self._menu and self._menu.winfo_exists():
                    self._menu.destroy()
                self._menu = TrayMenu(self, *args)
            elif action == 'quit':
                self._closed = True
                self.destroy()
                return
            elif action == 'update_result':
                self._checking_update = False
                self._update_result = args[0]
                if self._view_built:
                    self._render_update()
            elif action == 'relaunch':
                from app_lifecycle import launch_replacement
                launch_replacement(args[0])
                self.destroy()
                return
        self.after(80, self._process_tasks)

    def _remember_state(self, event):
        if event.widget == self and not self._hidden and self.state() in ('normal', 'zoomed'):
            self._restore_state = self.state()
            if self._restore_state == 'normal':
                scale = self._get_window_scaling()
                self._normal_size = [round(self.winfo_width()/scale), round(self.winfo_height()/scale)]

    def _on_unmap(self, event):
        if event.widget == self and self.state() == 'iconic':
            self.after(10, self._hide)

    def _hide(self):
        if self.preview:
            self.destroy()
            return
        if self._hidden:
            return
        self._hidden = True
        self.withdraw()
        self._unload_job = self.after(6000, self._unload_view)
        if settings.get('TRAY_HINT_ENABLED', True) and not self._tray_hint_shown:
            from ui_popups import TrayHint
            self._tray_hint_shown = True
            self._toast = TrayHint(self)

    def _show_window(self):
        if self._unload_job is not None:
            self.after_cancel(self._unload_job)
            self._unload_job = None
        self._build_view()
        if self._toast and self._toast.winfo_exists():
            self._toast.destroy()
        self._hidden = False
        self.deiconify()
        self.state(self._restore_state)
        self.lift()
        self.focus_force()

    def destroy(self):
        if getattr(self, '_destroyed', False):
            return
        self._destroyed = True
        self._closed = True
        # This app owns one Tcl interpreter. Cancel both UI and toolkit timers on exit.
        for job in self.tk.call('after', 'info'):
            self.after_cancel(job)
        super().destroy()


def open_settings_window():
    SettingsGUI(preview=True).mainloop()
