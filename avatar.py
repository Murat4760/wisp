"""On-screen avatar: shows what Wisp is doing (listening / thinking / talking).
Styles: cartoon ghost (bottom-right), orb (bottom-right), island (pill at top-center), off.
Click-through, always on top, never takes focus. Frames are drawn with Pillow and pushed to a
per-pixel-alpha layered window (UpdateLayeredWindow), so edges and glows are smooth."""
import ctypes
import math
import random
import time
import tkinter as tk
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

STYLES = ("cartoon", "orb", "island", "off")
HOLD = {"done": 2.5, "reply": 7.0, "error": 5.0}  # seconds before going back to idle
COLORS = {  # state -> RGB
    "idle": (110, 160, 255), "listening": (70, 200, 255), "thinking": (165, 120, 255),
    "talking": (80, 225, 165), "done": (80, 225, 165), "reply": (80, 225, 165), "error": (255, 95, 95),
}
LABELS = {"dictate": "Listening…", "command": "Command…", "screen": "Ask about your screen…"}

_s = {"style": "cartoon", "state": "idle", "mode": "", "text": "", "since": 0.0, "level": 0.0, "talking": False}


# ---------- API used by wisp.py (safe to call from any thread) ----------
def set_state(state, text="", mode=""):
    _s.update(state=state, text=text or "", mode=mode or _s["mode"], since=time.time())


def set_level(level):
    _s["level"] = max(0.0, min(1.0, level))


def set_talking(on):
    _s["talking"] = on
    _s["since"] = time.time()


def set_style(style):
    _s["style"] = style if style in STYLES else "cartoon"


def style():
    return _s["style"]


# ---------- Win32 plumbing ----------
user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # crisp on high-DPI screens
except Exception:
    pass


class _BLEND(ctypes.Structure):
    _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_H = ctypes.c_void_p
user32.GetDC.restype = _H
user32.GetDC.argtypes = [_H]
user32.ReleaseDC.argtypes = [_H, _H]
user32.GetAncestor.restype = _H
user32.GetAncestor.argtypes = [_H, ctypes.c_uint]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [_H, ctypes.c_int]
user32.SetWindowLongPtrW.argtypes = [_H, ctypes.c_int, ctypes.c_ssize_t]
user32.UpdateLayeredWindow.argtypes = [_H, _H, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE), _H,
                                       ctypes.POINTER(wintypes.POINT), wintypes.DWORD, ctypes.POINTER(_BLEND),
                                       wintypes.DWORD]
gdi32.CreateCompatibleDC.restype = _H
gdi32.CreateCompatibleDC.argtypes = [_H]
gdi32.CreateDIBSection.restype = _H
gdi32.CreateDIBSection.argtypes = [_H, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), _H,
                                   wintypes.DWORD]
gdi32.SelectObject.restype = _H
gdi32.SelectObject.argtypes = [_H, _H]
gdi32.DeleteObject.argtypes = [_H]
gdi32.DeleteDC.argtypes = [_H]


def _work_area():
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA (excludes taskbar)
    return r.left, r.top, r.right, r.bottom


def _blit(hwnd, img, x, y):
    """Show an RGBA Pillow image as the whole window, at screen position x, y."""
    w, h = img.size
    a = np.asarray(img, dtype=np.uint16)
    a[..., :3] = a[..., :3] * a[..., 3:4] // 255  # Windows wants premultiplied alpha
    data = np.ascontiguousarray(a[..., [2, 1, 0, 3]].astype(np.uint8)).tobytes()  # BGRA
    screen = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bmi = _BMIH(ctypes.sizeof(_BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, data, len(data))
    old = gdi32.SelectObject(dc, bmp)
    user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(x, y)), ctypes.byref(wintypes.SIZE(w, h)),
                               dc, ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(_BLEND(0, 0, 255, 1)), 2)
    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(None, screen)


# ---------- drawing helpers ----------
SS = 2  # supersampling for smooth edges


def _font(px, bold=False):
    try:
        return ImageFont.truetype("segoeuib.ttf" if bold else "segoeui.ttf", px)
    except OSError:
        return ImageFont.load_default()


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _glow(img, cx, cy, r, color, alpha, blur):
    layer = Image.new("RGBA", img.size, color + (0,))  # transparent *colored* pixels: blur won't darken the edge
    ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _ball(d, cx, cy, r, color):
    """Filled circle with a soft top-left highlight, so it reads as a 3D sphere."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (255,))
    for i in range(6):
        t = (i + 1) / 7
        rr = r * (1 - t * 0.7)
        ox, oy = cx - r * 0.28 * t, cy - r * 0.32 * t
        d.ellipse((ox - rr, oy - rr, ox + rr, oy + rr), fill=_mix(color, (255, 255, 255), t * 0.55) + (255,))


def _wrap(text, font, width, lines=2):
    words, out, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if font.getlength(test) <= width:
            cur = test
            continue
        out.append(cur)
        cur = w
        if len(out) == lines:
            break
    else:
        out.append(cur)
        return [l for l in out if l]
    last = out[-1]
    while last and font.getlength(last + "…") > width:
        last = last[:-1]
    return out[:-1] + [last.rstrip() + "…"]


# ---------- the window ----------
class Avatar:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry("1x1+-100+-100")
        self.root.update_idletasks()
        self.hwnd = user32.GetAncestor(self.root.winfo_id(), 2)  # GA_ROOT
        ex = user32.GetWindowLongPtrW(self.hwnd, -20)
        # layered | click-through | no taskbar button | never steals focus | topmost
        user32.SetWindowLongPtrW(self.hwnd, -20, ex | 0x80000 | 0x20 | 0x80 | 0x8000000 | 0x8)
        self.scale = user32.GetDpiForSystem() / 96 if hasattr(user32, "GetDpiForSystem") else 1.0
        self.color = COLORS["idle"]
        self.lvl = 0.0
        self.width = 0.0  # island width, animated
        self.blink_at = time.time() + 3
        self.hidden = False

    def px(self, v):
        return int(v * self.scale)

    def state(self):
        st = _s["state"]
        if st in HOLD and not _s["talking"] and time.time() - _s["since"] > HOLD[st]:
            _s["state"] = st = "idle"
        if _s["talking"]:
            return "talking"
        return st

    def tick(self):
        st = self.state()
        style = _s["style"]
        self.color = _mix(self.color, COLORS.get(st, COLORS["idle"]), 0.18)
        self.lvl += (_s["level"] - self.lvl) * 0.35
        if st != "listening":
            _s["level"] *= 0.8
        if style == "off":
            if not self.hidden:
                _blit(self.hwnd, Image.new("RGBA", (1, 1), (0, 0, 0, 0)), -10, -10)
                self.hidden = True
            self.root.after(250, self.tick)
            return
        self.hidden = False
        t = time.time()
        img, pos = {"orb": self.orb, "cartoon": self.cartoon, "island": self.island}[style](st, t)
        _blit(self.hwnd, img, *pos)
        self.root.after(66 if st == "idle" else 33, self.tick)

    # bottom-right corner, just above the taskbar
    def corner(self, size):
        l, t, r, b = _work_area()
        return r - size - self.px(16), b - size - self.px(16)

    def orb(self, st, t):
        size = self.px(130)
        n = size * SS
        img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        c = n / 2
        r = n * 0.16
        glow_a = 110
        if st == "idle":
            r *= 1 + 0.05 * math.sin(t * 2)
            glow_a = 70
        elif st == "listening":
            r *= 1.2 + 0.45 * self.lvl
            glow_a = 150 + int(90 * self.lvl)
        elif st == "thinking":
            r *= 1.1 + 0.04 * math.sin(t * 6)
        elif st == "talking":
            r *= 1.15 + 0.12 * abs(math.sin(t * 9))
        elif st == "error":
            r *= 1.05 + 0.06 * math.sin(t * 25) * max(0, 1 - (t - _s["since"]))
        # glow + blur must stay inside the window or it gets clipped into a visible square
        _glow(img, c, c, min(r * 1.9, n * 0.3), self.color, glow_a, min(r * 0.6, n * 0.07))
        if st == "talking" or st == "reply":  # ripples
            for k in range(2):
                ph = (t * 0.9 + k * 0.5) % 1
                rr = min(r * (1.1 + ph * 1.2), n * 0.46)
                ImageDraw.Draw(img).ellipse((c - rr, c - rr, c + rr, c + rr),
                                            outline=self.color + (int(160 * (1 - ph)),), width=int(SS * 2))
        d = ImageDraw.Draw(img)
        _ball(d, c, c, r, self.color)
        if st == "thinking":  # three orbiting sparks
            for k in range(3):
                a = t * 3.2 + k * 2.094
                ox, oy = c + math.cos(a) * r * 1.6, c + math.sin(a) * r * 1.6
                s = r * 0.16
                d.ellipse((ox - s, oy - s, ox + s, oy + s), fill=(235, 225, 255, 230))
        img = img.resize((size, size), Image.LANCZOS)
        return img, self.corner(size)

    def cartoon(self, st, t):
        """A little ghost - a 'wisp': outlined cartoon body with a wavy tail, arms and blush.
        Idle floats and blinks, listening shows sound waves, thinking has thought bubbles, talking moves its
        mouth, done waves with sparkles, error gets dizzy eyes and a sweat drop."""
        size = self.px(150)
        n = size * SS
        img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        ink = (38, 40, 64, 255)
        lw = max(SS * 2, int(SS * 2.4 * self.scale))
        thin = max(SS, lw // 2)
        R = n * 0.25  # head radius
        cx = n * 0.5
        bob = math.sin(t * 2.2) * n * 0.02
        if st == "talking":
            bob -= abs(math.sin(t * 9)) * n * 0.008
        if st == "error":  # short shake when the error appears
            cx += math.sin(t * 30) * n * 0.012 * max(0.0, 1 - (t - _s["since"]))
        hy = n * 0.2 + bob + R  # head center
        yb = hy + R * 1.05  # where the wavy tail starts
        wide = 1 + (0.06 * self.lvl if st == "listening" else 0)

        d = ImageDraw.Draw(img)
        sw = R * (0.85 - bob / n * 3)  # ground shadow shrinks as it floats up
        d.ellipse((cx - sw, n * 0.9 - R * 0.11, cx + sw, n * 0.9 + R * 0.11), fill=(0, 0, 0, 38))
        _glow(img, cx, hy + R * 0.35, R * 1.2, self.color, 70 if st == "idle" else 140, R * 0.3)
        d = ImageDraw.Draw(img)

        light = _mix((252, 252, 255), self.color, 0.06)
        shade = _mix((210, 218, 240), self.color, 0.22)
        # arms, drawn first so the body overlaps them
        ar = R * 0.2
        left = (cx - R * wide, hy + R * 0.55)
        right = (cx + R * wide, hy + R * 0.55)
        if st in ("done", "reply"):  # wave
            right = (cx + R * 1.12, hy - R * 0.05 + math.sin(t * 12) * R * 0.14)
        elif st == "listening":  # hand up by the "ear"
            right = (cx + R * 1.05, hy - R * 0.05)
        elif st == "thinking":  # hand on chin
            left = (cx - R * 0.55, hy + R * 0.72)
        for ax, ay in (left, right):
            d.ellipse((ax - ar, ay - ar * 0.85, ax + ar, ay + ar * 0.85), fill=light, outline=ink, width=lw)

        # body: round head, straight sides, wavy tail
        pts = [(cx + R * wide * math.cos(a), hy + R * math.sin(a))
               for a in (math.pi + math.pi * i / 36 for i in range(37))]
        for i in range(49):
            u = i / 48
            pts.append((cx + R * wide - 2 * R * wide * u,
                        yb + R * 0.2 * (0.5 + 0.5 * math.sin(u * 3 * 2 * math.pi + t * 5))))
        d.polygon(pts, fill=shade)
        hx, hy2 = cx - R * 0.18, hy - R * 0.22  # highlight: same shape shrunk toward the top-left
        d.polygon([(hx + (x - hx) * 0.84, hy2 + (y - hy2) * 0.84) for x, y in pts], fill=light)
        d.line(pts + [pts[0]], fill=ink, width=lw, joint="curve")

        for sx in (-1, 1):  # cheeks
            bx, by = cx + sx * R * 0.6, hy + R * 0.36
            # solid color: ImageDraw replaces pixels, so a see-through pink would let the desktop show through
            d.ellipse((bx - R * 0.14, by - R * 0.08, bx + R * 0.14, by + R * 0.08),
                      fill=_mix(light, (255, 140, 165), 0.45) + (255,))

        # eyes; blink every few seconds, closed for 0.13s
        if t > self.blink_at + 0.13:
            self.blink_at = t + random.uniform(2.5, 5.5)
        open_ = 0.12 if self.blink_at <= t else 1.0
        ew, eh = R * 0.15, R * 0.23
        if st == "listening":
            ew, eh = ew * 1.12, eh * 1.12
        look = (0.0, 0.0)
        if st == "thinking":
            look = (-0.35 + 0.1 * math.sin(t * 2), -0.5)
        elif st == "idle" and math.sin(t * 0.35) > 0.6:  # glance around now and then
            look = (0.3 * math.sin(t * 0.7), 0.0)
        for sx in (-1, 1):
            x, y = cx + sx * R * 0.36 + look[0] * ew, hy + R * 0.02 + look[1] * eh * 0.5
            if st in ("done", "reply"):  # happy ^ ^
                d.arc((x - ew * 1.1, y - eh * 0.4, x + ew * 1.1, y + eh * 1.1), 200, 340, fill=ink, width=lw)
            elif st == "error":  # dizzy spirals
                sp = [(x + ew * 1.2 * (1 - k / 40) * math.cos(k * 0.5 + t * 8 * sx),
                       y + ew * 1.2 * (1 - k / 40) * math.sin(k * 0.5 + t * 8 * sx)) for k in range(40)]
                d.line(sp, fill=ink, width=thin, joint="curve")
            else:
                h = eh * open_
                d.ellipse((x - ew, y - h, x + ew, y + h), fill=ink)
                if open_ > 0.5:
                    s1 = ew * 0.42
                    d.ellipse((x + ew * 0.1, y - h * 0.62, x + ew * 0.1 + s1 * 2, y - h * 0.62 + s1 * 2),
                              fill=(255, 255, 255, 255))

        # mouth
        mx, my = cx, hy + R * 0.42
        mouth, tongue = (90, 30, 50, 255), (255, 120, 140, 255)
        if st == "talking":
            mh = R * (0.05 + 0.16 * abs(math.sin(t * 13) * math.sin(t * 5.3)))
            d.ellipse((mx - R * 0.13, my - mh, mx + R * 0.13, my + mh), fill=mouth, outline=ink, width=thin)
        elif st == "listening":
            mh = R * (0.04 + 0.1 * self.lvl)
            d.ellipse((mx - mh, my - mh, mx + mh, my + mh), fill=mouth, outline=ink, width=thin)
        elif st in ("done", "reply"):
            d.chord((mx - R * 0.2, my - R * 0.12, mx + R * 0.2, my + R * 0.2), 0, 180, fill=mouth, outline=ink,
                    width=thin)
            d.chord((mx - R * 0.09, my + R * 0.04, mx + R * 0.09, my + R * 0.19), 0, 180, fill=tongue)
        elif st == "thinking":
            d.line([(mx - R * 0.1, my + R * 0.02), (mx, my - R * 0.02), (mx + R * 0.1, my + R * 0.03)],
                   fill=ink, width=lw, joint="curve")
        elif st == "error":
            d.arc((mx - R * 0.14, my, mx + R * 0.14, my + R * 0.22), 200, 340, fill=ink, width=lw)
        else:
            d.arc((mx - R * 0.14, my - R * 0.16, mx + R * 0.14, my + R * 0.08), 25, 155, fill=ink, width=lw)

        # extras per state
        if st == "listening":  # sound waves by the raised hand; louder voice = stronger waves
            for k in range(1, 4):
                rr = R * 0.17 * k
                a = int(255 * min(1.0, 0.25 + self.lvl * 1.4) * (1 - (k - 1) * 0.25))
                ox = right[0] + R * 0.15
                d.arc((ox - rr, right[1] - rr, ox + rr, right[1] + rr), -50, 50, fill=self.color + (a,), width=lw)
        elif st == "thinking":  # bubbles rising from the head
            for k in range(3):
                ph = (t * 0.8 + k / 3) % 1
                br = R * (0.07 + 0.05 * k)
                bx, by = cx + R * (0.72 + 0.22 * k), hy - R * (0.8 + 0.2 * k) - ph * R * 0.08
                d.ellipse((bx - br, by - br, bx + br, by + br), fill=(255, 255, 255, 255), outline=ink, width=thin)
        elif st in ("done", "reply"):  # twinkling sparkles
            for k, (px_, py_) in enumerate(((-1.15, -0.85), (1.2, -0.95), (-1.3, 0.25))):
                s = R * 0.12 * (0.5 + 0.5 * abs(math.sin(t * 4 + k * 2)))
                sx_, sy_ = cx + px_ * R, hy + py_ * R
                d.polygon([(sx_, sy_ - s), (sx_ + s * 0.28, sy_ - s * 0.28), (sx_ + s, sy_),
                           (sx_ + s * 0.28, sy_ + s * 0.28), (sx_, sy_ + s), (sx_ - s * 0.28, sy_ + s * 0.28),
                           (sx_ - s, sy_), (sx_ - s * 0.28, sy_ - s * 0.28)], fill=(255, 210, 90, 255))
        elif st == "error":  # sweat drop
            sx_, sy_, dr = cx + R * 0.82, hy - R * 0.55, R * 0.1
            d.polygon([(sx_, sy_ - dr * 2.2), (sx_ - dr, sy_), (sx_ + dr, sy_)], fill=(140, 200, 255, 255))
            d.ellipse((sx_ - dr, sy_ - dr, sx_ + dr, sy_ + dr), fill=(140, 200, 255, 255))

        img = img.resize((size, size), Image.LANCZOS)
        return img, self.corner(size)

    def island(self, st, t):
        text, sub = "", ""
        if st == "listening":
            text = LABELS.get(_s["mode"], "Listening…")
        elif st == "thinking":
            text = "Thinking" + "." * (int(t * 3) % 4)
        elif st in ("talking", "reply", "done", "error"):
            text = _s["text"] or {"done": "Done", "error": "Something went wrong"}.get(st, "")
        f = _font(self.px(15) * SS)
        if st == "idle":
            target_w, h = self.px(110), self.px(30)
            lines = []
        else:
            lines = _wrap(text, f, self.px(420) * SS) if text else []
            tw = max([f.getlength(l) for l in lines] or [0]) / SS
            extra = self.px(70) if st == "listening" else 0
            target_w = max(self.px(200), min(self.px(520), tw + self.px(70) + extra))
            h = self.px(44) if len(lines) <= 1 else self.px(66)
        self.width += (target_w - self.width) * 0.25
        w = int(self.width)
        W, H = w * SS, h * SS
        img = Image.new("RGBA", (W + 2 * SS, H + 2 * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((SS, SS, W, H), radius=H / 2 if len(lines) <= 1 else 22 * SS,
                            fill=(14, 15, 20, 238), outline=self.color + (90,), width=SS)
        # status dot
        dr = H * 0.16 if len(lines) <= 1 else self.px(30) * SS * 0.16
        dx, dy = H / 2 if len(lines) <= 1 else self.px(22) * SS, H / 2
        pulse = 1 + (0.6 * self.lvl if st == "listening" else 0.15 * math.sin(t * 6) if st != "idle" else 0)
        _glow(img, dx, dy, dr * 1.9 * pulse, self.color, 140, dr * 0.8)
        d = ImageDraw.Draw(img)
        d.ellipse((dx - dr * pulse, dy - dr * pulse, dx + dr * pulse, dy + dr * pulse), fill=self.color + (255,))
        if lines and w > target_w * 0.85:
            lh = f.size * 1.25
            y0 = H / 2 - lh * len(lines) / 2
            for i, line in enumerate(lines):
                d.text((dx + dr * 2.2, y0 + i * lh), line, font=f, fill=(240, 242, 248, 255))
        if st == "listening" and w > target_w * 0.85:  # level bars on the right
            for k in range(5):
                bh = H * (0.15 + 0.5 * self.lvl * (0.6 + 0.4 * math.sin(t * 15 + k * 1.3)))
                bx = W - H * 0.55 - (4 - k) * H * 0.18
                d.rounded_rectangle((bx, H / 2 - bh / 2, bx + H * 0.09, H / 2 + bh / 2), radius=H * 0.05,
                                    fill=self.color + (255,))
        img = img.resize((img.width // SS, img.height // SS), Image.LANCZOS)
        l, top, r, b = _work_area()
        return img, ((l + r) // 2 - img.width // 2, top + self.px(10))

    def run(self):
        self.tick()
        self.root.mainloop()


def run(default_style="cartoon"):
    """Blocks: runs the avatar window on the calling (main) thread."""
    set_style(default_style)
    Avatar().run()
