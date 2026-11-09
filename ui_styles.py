"""Shared light palette and a small, consistent set of line icons."""
from pathlib import Path
import ctypes
import sys
from PIL import Image, ImageDraw

BG = '#F4F6F8'
SURFACE = '#FFFFFF'
TEXT = '#18232D'
MUTED = '#5A6D7D'
BORDER = '#E4E8ED'
BLUE = '#2F70BF'
BLUE_SOFT = '#EDF4FC'
GREEN = '#147D5F'
FONT = 'Microsoft YaHei UI'


def icon_image(name, size=20, color=BLUE):
    scale = 4
    image = Image.new('RGBA', (24 * scale, 24 * scale))
    d = ImageDraw.Draw(image)
    def line(points, width=1.65):
        d.line([(round(x * scale), round(y * scale)) for x, y in points], fill=color, width=round(width * scale), joint='curve')
    def oval(box, width=1.65, fill=None):
        d.ellipse(tuple(round(v * scale) for v in box), outline=color, width=round(width * scale), fill=fill)
    def rect(box, radius=2):
        d.rounded_rectangle(tuple(round(v * scale) for v in box), radius=round(radius * scale), outline=color, width=round(1.65 * scale))
    if name == 'headphones':
        d.arc((4*scale, 3*scale, 20*scale, 20*scale), 180, 360, fill=color, width=round(1.8*scale))
        rect((3, 10, 8, 20)); rect((16, 10, 21, 20))
    elif name == 'bell':
        line([(5, 17), (7, 14), (7, 9), (8, 6), (10, 4), (14, 4), (16, 6), (17, 9), (17, 14), (19, 17), (5, 17)])
        line([(10, 21), (14, 21)])
    elif name == 'power':
        d.arc((4*scale,4*scale,20*scale,21*scale), -55, 235, fill=color, width=round(1.7*scale))
        line([(12, 2), (12, 11)])
    elif name == 'check':
        line([(5, 12), (10, 17), (20, 6)], 2)
    elif name == 'refresh':
        d.arc((4*scale,4*scale,20*scale,20*scale), 30, 320, fill=color, width=round(1.6*scale))
        line([(21, 3), (21, 9), (15, 9)])
    elif name == 'close':
        line([(6, 6), (18, 18)]); line([(18, 6), (6, 18)])
    elif name == 'chevron':
        line([(9, 5), (16, 12), (9, 19)])
    elif name == 'down':
        line([(5, 9), (12, 16), (19, 9)])
    elif name == 'window':
        rect((3, 4, 21, 20)); line([(3, 9), (21, 9)])
    elif name == 'disconnect':
        line([(5, 3), (5, 8), (13, 8), (13, 3)])
        line([(3, 8), (3, 12), (6, 15), (12, 15), (15, 12), (15, 8)])
        line([(9, 15), (9, 21)]); line([(17, 16), (22, 21)]); line([(22, 16), (17, 21)])
    elif name == 'connect':
        line([(8, 3), (8, 8), (16, 8), (16, 3)])
        line([(6, 8), (6, 13), (9, 16), (15, 16), (18, 13), (18, 8)])
        line([(12, 16), (12, 22)])
    elif name == 'sliders':
        for x, y in [(5, 8), (12, 16), (19, 7)]:
            line([(x, 3), (x, y-3)]); line([(x, y+3), (x, 21)])
            oval((x-2.5, y-2.5, x+2.5, y+2.5), 1.5)
    elif name == 'clock':
        oval((3, 3, 21, 21)); line([(12, 7), (12, 12), (16, 14)])
    elif name == 'info':
        oval((3, 3, 21, 21)); line([(12, 11), (12, 17)]); oval((11.5, 7, 12.5, 8), 1, color)
    elif name == 'quit':
        line([(10, 3), (4, 3), (4, 21), (10, 21)])
        line([(10, 12), (21, 12), (17, 8)]); line([(21, 12), (17, 16)])
    elif name == 'tray':
        line([(3, 13), (3, 20), (21, 20), (21, 13)])
        line([(12, 3), (12, 15), (7, 10)]); line([(12, 15), (17, 10)])
    return image.resize((size, size), Image.Resampling.LANCZOS)


def icon(name, size=20, color=BLUE):
    import customtkinter as ctk
    image = icon_image(name, size * 2, color)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def app_icon(size=128):
    image = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size-1, size-1), radius=size//4, fill=BLUE)
    mark = icon_image('headphones', round(size * .68), '#FFFFFF')
    image.alpha_composite(mark, ((size-mark.width)//2, (size-mark.height)//2))
    return image


def apply_native_chrome(window):
    """Style our own HWND while retaining native resize, snap and caption behavior."""
    window.update_idletasks()
    try:
        user = ctypes.windll.user32
        user.GetParent.argtypes = [ctypes.c_void_p]
        user.GetParent.restype = ctypes.c_void_p
        hwnd = user.GetParent(window.winfo_id())
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        for key, value in [(20, 0), (33, 2), (35, 0x00FFFFFF), (36, 0x002D2318)]:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, key, ctypes.byref(v), ctypes.sizeof(v))
    except (OSError, AttributeError):
        pass
    path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'app.ico'
    if path.exists():
        window.iconbitmap(str(path))


def button(parent, text, command, symbol=None, primary=False, width=116):
    import customtkinter as ctk
    control = ctk.CTkButton(parent, text=text, command=command, image=icon(symbol, 16, '#FFFFFF' if primary else MUTED) if symbol else None,
        compound='left', width=width, height=36, corner_radius=7, border_width=0 if primary else 1,
        border_color='#DCE2E8', fg_color=BLUE if primary else SURFACE, hover_color='#2865AF' if primary else '#EDF2F7',
        text_color='#FFFFFF' if primary else '#263340', font=ctk.CTkFont(FONT, 12))
    control._canvas.configure(takefocus=1)
    control.bind('<Return>', lambda _: control.invoke())
    control.bind('<FocusIn>', lambda _: control.configure(border_width=2, border_color=BLUE))
    control.bind('<FocusOut>', lambda _: control.configure(border_width=0 if primary else 1, border_color='#DCE2E8'))
    return control
