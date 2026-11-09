"""Tray menu and short-lived, non-activating tray hint using the panel's palette."""
import ctypes
from ctypes import wintypes
import customtkinter as ctk
from settings_manager import settings, send_command
from ui_styles import SURFACE, TEXT, MUTED, BORDER, BLUE, GREEN, FONT, icon, button


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def monitor_workarea(x=None, y=None):
    user = ctypes.windll.user32
    point = wintypes.POINT()
    if x is None:
        user.GetCursorPos(ctypes.byref(point))
    else:
        point.x, point.y = x, y
    user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user.MonitorFromPoint.restype = ctypes.c_void_p
    user.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user.GetMonitorInfoW(user.MonitorFromPoint(point, 2), ctypes.byref(info))
    return info.rcWork


def clamp_popup(width, height, work, x=None, y=None, inset=12):
    left = work.right - width - inset if x is None else x - width
    top = work.bottom - height - inset if y is None else y - height
    return max(work.left, min(left, work.right-width)), max(work.top, min(top, work.bottom-height))


def place_popup(window, x=None, y=None, activate=True):
    window.update_idletasks()
    user = ctypes.windll.user32
    user.GetParent.argtypes = [ctypes.c_void_p]
    user.GetParent.restype = ctypes.c_void_p
    hwnd = user.GetParent(window.winfo_id())
    user.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    style = user.GetWindowLongPtrW(hwnd, -20) | 0x80
    if not activate:
        style |= 0x08000000  # WS_EX_NOACTIVATE; clicks do not steal focus.
    user.SetWindowLongPtrW(hwnd, -20, style)
    window.deiconify()
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    left, top = clamp_popup(width, height, monitor_workarea(x, y), x, y)
    user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user.SetWindowPos(hwnd, ctypes.c_void_p(-1), left, top, 0, 0, 0x0011)  # NOSIZE | NOACTIVATE
    if activate:
        window.lift()
        window.focus_force()


class TrayMenu(ctk.CTkToplevel):
    def __init__(self, owner, x=None, y=None, preview=False):
        super().__init__(owner)
        self.withdraw()
        self.title('AirPods 菜单预览' if preview else 'AirPods 托盘菜单')
        self.overrideredirect(not preview)
        self.configure(fg_color=BORDER)
        self.resizable(False, False)
        self.geometry('300x420')
        self.owner = owner
        self._focus_timer = None
        self._place_timer = None
        self._buttons = []
        panel = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=12)
        panel.pack(fill='both', expand=True, padx=1, pady=1)
        title = ctk.CTkLabel(panel, text='AirPods 自动接管', image=icon('headphones', 20), compound='left', anchor='w', text_color=TEXT, font=ctk.CTkFont(FONT, 14, 'bold'))
        title.pack(fill='x', padx=18, pady=(17, 3))
        enabled = settings.get('AUTO_CONNECT_ENABLED')
        ctk.CTkLabel(panel, text='自动接管已开启' if enabled else '自动接管已暂停', text_color=GREEN if enabled else MUTED, anchor='w', font=ctk.CTkFont(FONT, 11)).pack(fill='x', padx=44, pady=(0, 10))
        self._divider(panel)
        self._row(panel, 'window', '打开控制面板', lambda: owner.dispatch('show_settings'))
        self._row(panel, 'power', '电脑播放时自动接管', self._toggle_auto, checked=enabled)
        self._row(panel, 'connect', '立即连接', lambda: owner._command('connect'))
        self._row(panel, 'disconnect', '断开并暂停接管', lambda: owner._command('disconnect'))
        self._divider(panel)
        self._row(panel, 'bell', '右下角连接通知', self._toggle_notice, checked=settings.get('NOTIFICATIONS_ENABLED'))
        self._row(panel, 'info', '测试通知', lambda: owner._command('test_notification'))
        self._divider(panel)
        self._row(panel, 'quit', '退出程序', lambda: owner.dispatch('quit'), color='#B34B50')
        self.bind('<Escape>', lambda _: self.destroy())
        if not preview:
            self.bind('<FocusOut>', self._focus_out)
        self.bind('<Down>', lambda _: self._move_focus(1))
        self.bind('<Up>', lambda _: self._move_focus(-1))
        self._place_timer = self.after(250, self.deiconify if preview else lambda: place_popup(self, x, y))

    @staticmethod
    def _divider(parent):
        ctk.CTkFrame(parent, height=1, fg_color='#EDF0F4').pack(fill='x', padx=13, pady=5)

    def _row(self, parent, symbol, text, action, checked=None, color=TEXT):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', padx=7, pady=1)
        control = ctk.CTkButton(row, text=text, image=icon(symbol, 17, MUTED if color == TEXT else color), compound='left', anchor='w', height=35,
            fg_color=SURFACE, hover_color='#EDF4FC', corner_radius=7, text_color=color, font=ctk.CTkFont(FONT, 12), command=lambda: self._invoke(action))
        control.pack(fill='x')
        control._canvas.configure(takefocus=1)
        control.bind('<Return>', lambda _: control.invoke())
        control.bind('<space>', lambda _: control.invoke())
        control.bind('<FocusIn>', lambda _: control.configure(fg_color='#EDF4FC'))
        control.bind('<FocusOut>', lambda _: control.configure(fg_color=SURFACE))
        self._buttons.append(control)
        if checked:
            mark = ctk.CTkLabel(row, text='', image=icon('check', 15), width=20, height=25, fg_color='transparent')
            mark.place(relx=1, rely=.5, x=-10, anchor='e')
            mark.bind('<Button-1>', lambda _: self._invoke(action))

    def _move_focus(self, delta):
        focused = self.focus_get()
        current = next((i for i, b in enumerate(self._buttons) if focused in (b, b._canvas)), -1)
        self._buttons[(current + delta) % len(self._buttons)].focus_set()
        return 'break'

    def _focus_out(self, _):
        if self._focus_timer:
            self.after_cancel(self._focus_timer)
        self._focus_timer = self.after(120, self._check_focus)

    def _check_focus(self):
        if self.winfo_exists():
            focus = self.focus_displayof()
            if focus is None or focus.winfo_toplevel() != self:
                self.destroy()

    def _invoke(self, action):
        self.destroy()
        action()

    def _toggle_auto(self):
        if not self.owner.preview:
            settings.set('AUTO_CONNECT_ENABLED', not settings.get('AUTO_CONNECT_ENABLED'))

    def _toggle_notice(self):
        if not self.owner.preview:
            settings.set('NOTIFICATIONS_ENABLED', not settings.get('NOTIFICATIONS_ENABLED'))

    def destroy(self):
        for timer in (self._focus_timer, self._place_timer):
            if timer:
                self.after_cancel(timer)
        self._focus_timer = self._place_timer = None
        super().destroy()
        ctk.ScalingTracker.window_dpi_scaling_dict.pop(self, None)


class TrayHint(ctk.CTkToplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.withdraw()
        self.title('AirPods 收起提醒')
        self.overrideredirect(True)
        self.configure(fg_color=BORDER)
        self.geometry('380x188')
        self._timer = None
        self._place_timer = None
        panel = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=12)
        panel.pack(fill='both', expand=True, padx=1, pady=1)
        header = ctk.CTkFrame(panel, fg_color='transparent')
        header.pack(fill='x', padx=17, pady=(13, 5))
        ctk.CTkLabel(header, text='AirPods 自动接管', image=icon('headphones', 19), compound='left', text_color=MUTED, font=ctk.CTkFont(FONT, 11)).pack(side='left')
        ctk.CTkButton(header, text='', image=icon('close', 13, MUTED), width=26, height=26, fg_color=SURFACE, hover_color='#EDF2F7', command=self.destroy).pack(side='right')
        ctk.CTkLabel(panel, text='窗口已收起到系统托盘', anchor='w', text_color=TEXT, font=ctk.CTkFont(FONT, 15, 'bold')).pack(fill='x', padx=18)
        enabled = settings.get('AUTO_CONNECT_ENABLED')
        description = '自动接管继续运行。\n双击托盘耳机图标可重新打开窗口。' if enabled else '自动接管当前已暂停。\n可从托盘菜单随时开启。'
        ctk.CTkLabel(panel, text=description, justify='left', anchor='w', text_color=MUTED, font=ctk.CTkFont(FONT, 11)).pack(fill='x', padx=18, pady=(2, 8))
        footer = ctk.CTkFrame(panel, fg_color='transparent')
        footer.pack(fill='x', padx=18)
        ctk.CTkLabel(footer, text='已开启自动接管' if enabled else '自动接管已暂停', text_color=GREEN if enabled else MUTED, font=ctk.CTkFont(FONT, 11)).pack(side='left')
        button(footer, '显示窗口', lambda: (self.destroy(), owner.dispatch('show_settings')), 'window', width=104).pack(side='right')
        self._place_timer = self.after(60, lambda: place_popup(self, activate=False))
        self._timer = self.after(5000, self.destroy)

    def destroy(self):
        if self._place_timer is not None:
            self.after_cancel(self._place_timer)
            self._place_timer = None
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        super().destroy()
        ctk.ScalingTracker.window_dpi_scaling_dict.pop(self, None)
