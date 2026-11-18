"""上画面 (320x240) の描画。PIL で1枚の画像を作り、display.show() に渡す。"""
import datetime
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 320, 240
STATUS_H = 22
TAB_H = 34

# 色 (R, G, B)
BG = (14, 18, 24)
PANEL = (28, 35, 45)
LINE = (52, 62, 76)
FG = (232, 236, 240)
MUTED = (140, 152, 166)
ACCENT = (64, 170, 255)
OK = (80, 200, 120)
WARN = (240, 180, 60)
BAD = (235, 80, 80)

FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", True),
    ("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf", True),
    ("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf", True),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", False),
]
BOLD_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", True),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", False),
]
WEEK_JA = "月火水木金土日"


def _find(cands):
    for path, cjk in cands:
        if os.path.exists(path):
            return path, cjk
    return None, False


class Fonts:
    def __init__(self):
        self.path, self.cjk = _find(FONT_CANDIDATES)
        self.bold_path, _ = _find(BOLD_CANDIDATES)
        self._cache = {}

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self._cache:
            path = (self.bold_path if bold else None) or self.path
            self._cache[key] = (ImageFont.truetype(path, size) if path
                                else ImageFont.load_default(size=size))
        return self._cache[key]


def text_w(draw, text, font):
    l, _, r, _ = draw.textbbox((0, 0), text, font=font)
    return r - l


def draw_battery(d, x, y, pct, charging):
    color = MUTED if pct is None else (BAD if pct <= 15 else WARN if pct <= 35 else OK)
    d.rounded_rectangle((x, y, x + 22, y + 11), radius=2, outline=FG)
    d.rectangle((x + 23, y + 3, x + 24, y + 8), fill=FG)
    if pct is not None:
        fill_w = int(18 * pct / 100)
        if fill_w > 0:
            d.rectangle((x + 2, y + 2, x + 2 + fill_w, y + 9), fill=color)
    if charging:
        d.polygon([(x + 12, y + 1), (x + 8, y + 6), (x + 11, y + 6), (x + 10, y + 10),
                   (x + 14, y + 5), (x + 11, y + 5)], fill=FG)


def draw_wifi(d, x, y, quality):
    bars = 0 if quality is None else (1 + (quality >= 30) + (quality >= 55) + (quality >= 80))
    for i in range(4):
        h = 3 + i * 3
        color = FG if i < bars else LINE
        d.rectangle((x + i * 5, y + 12 - h, x + i * 5 + 3, y + 12), fill=color)


class Button:
    def __init__(self, box, label, on_tap):
        self.box, self.label, self.on_tap = box, label, on_tap
        self.pressed = False

    def hit(self, x, y):
        x1, y1, x2, y2 = self.box
        return x1 <= x < x2 and y1 <= y < y2

    def draw(self, d, fonts, active=False):
        fill = ACCENT if (self.pressed or active) else PANEL
        fg = BG if (self.pressed or active) else FG
        d.rounded_rectangle(self.box, radius=6, fill=fill, outline=LINE)
        f = fonts.get(13, bold=True)
        x1, y1, x2, y2 = self.box
        tw = text_w(d, self.label, f)
        d.text(((x1 + x2 - tw) // 2, (y1 + y2) // 2 - 8), self.label, font=f, fill=fg)


class Page:
    title = ""

    def __init__(self, app):
        self.app = app
        self.buttons = []

    def touch(self, ev):
        """タッチイベントを処理。再描画が必要なら True。"""
        changed = False
        for b in self.buttons:
            if ev.kind == "down" and b.hit(ev.x, ev.y):
                b.pressed = True
                changed = True
            elif ev.kind == "up" and b.pressed:
                b.pressed = False
                changed = True
                if b.hit(ev.x, ev.y):
                    b.on_tap()
            elif ev.kind == "move" and b.pressed and not b.hit(ev.x, ev.y):
                b.pressed = False
                changed = True
        return changed

    def draw(self, img, d, fonts, st):
        for b in self.buttons:
            b.draw(d, fonts)


class HomePage(Page):
    title = "HOME"

    def draw(self, img, d, fonts, st):
        now = st["now"]
        f_big = fonts.get(64, bold=True)
        hm = now.strftime("%H:%M")
        tw = text_w(d, hm, f_big)
        d.text(((W - tw) // 2, STATUS_H + 30), hm, font=f_big, fill=FG)
        f_sec = fonts.get(16)
        sec = now.strftime(":%S")
        d.text(((W + tw) // 2 + 2, STATUS_H + 76), sec, font=f_sec, fill=MUTED)
        if fonts.cjk:
            date = "%d月%d日 (%s)" % (now.month, now.day, WEEK_JA[now.weekday()])
        else:
            date = now.strftime("%a, %b %d")
        f_date = fonts.get(18)
        dw = text_w(d, date, f_date)
        d.text(((W - dw) // 2, STATUS_H + 112), date, font=f_date, fill=ACCENT)
        f_small = fonts.get(12)
        line = "%s   %s" % (st.get("ssid") or "Wi-Fi なし" if fonts.cjk else st.get("ssid") or "no Wi-Fi",
                           st.get("ip") or "")
        lw = text_w(d, line, f_small)
        d.text(((W - lw) // 2, STATUS_H + 148), line, font=f_small, fill=MUTED)
        super().draw(img, d, fonts, st)


class SystemPage(Page):
    title = "SYSTEM"

    def draw(self, img, d, fonts, st):
        rows = [
            ("CPU温度" if fonts.cjk else "CPU temp", st.get("temp"), 85, "%.1f°C"),
            ("負荷" if fonts.cjk else "Load", st.get("load"), 4, "%.2f"),
            ("メモリ" if fonts.cjk else "Memory", st.get("mem"), 100, "%.0f%%"),
            ("バッテリー" if fonts.cjk else "Battery", st.get("bat"), 100, "%d%%"),
        ]
        f = fonts.get(13)
        fv = fonts.get(13, bold=True)
        y = STATUS_H + 12
        for label, val, vmax, fmt in rows:
            d.text((16, y), label, font=f, fill=MUTED)
            vtxt = "--" if val is None else fmt % val
            d.text((W - 16 - text_w(d, vtxt, fv), y), vtxt, font=fv, fill=FG)
            bx1, bx2 = 16, W - 16
            d.rounded_rectangle((bx1, y + 21, bx2, y + 27), radius=3, fill=PANEL)
            if val is not None:
                ratio = max(0.0, min(1.0, val / vmax))
                color = BAD if ratio > 0.85 else WARN if ratio > 0.6 else ACCENT
                if label.startswith(("バッテリー", "Battery")):
                    color = BAD if ratio < 0.15 else WARN if ratio < 0.35 else OK
                if ratio > 0:
                    d.rounded_rectangle((bx1, y + 21, bx1 + int((bx2 - bx1) * ratio), y + 27),
                                        radius=3, fill=color)
            y += 42
        super().draw(img, d, fonts, st)


class PaintPage(Page):
    title = "TOUCH"
    COLORS = [FG, ACCENT, OK, WARN, BAD]

    def __init__(self, app):
        super().__init__(app)
        self.layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.color = 0
        self.last = None
        top = H - TAB_H - 30
        self.area = (0, STATUS_H, W, top)
        self.buttons = [
            Button((8, top + 2, 78, top + 26), "Color", self.next_color),
            Button((W - 78, top + 2, W - 8, top + 26), "Clear", self.clear),
        ]

    def next_color(self):
        self.color = (self.color + 1) % len(self.COLORS)

    def clear(self):
        self.layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def touch(self, ev):
        x1, y1, x2, y2 = self.area
        inside = x1 <= ev.x < x2 and y1 <= ev.y < y2
        if inside and ev.kind in ("down", "move") and not any(b.pressed for b in self.buttons):
            d = ImageDraw.Draw(self.layer)
            c = self.COLORS[self.color]
            if ev.kind == "move" and self.last:
                d.line((self.last, (ev.x, ev.y)), fill=c, width=4)
            d.ellipse((ev.x - 2, ev.y - 2, ev.x + 2, ev.y + 2), fill=c)
            self.last = (ev.x, ev.y)
            return True
        if ev.kind == "up":
            self.last = None
        return super().touch(ev)

    def draw(self, img, d, fonts, st):
        x1, y1, x2, y2 = self.area
        f = fonts.get(12)
        hint = "ここに描けます" if fonts.cjk else "Draw here"
        d.text((W // 2 - text_w(d, hint, f) // 2, y1 + 6), hint, font=f, fill=LINE)
        img.alpha_composite(self.layer) if img.mode == "RGBA" else img.paste(self.layer, (0, 0), self.layer)
        bx = 86
        d.rounded_rectangle((bx, y2 + 6, bx + 20, y2 + 22), radius=4, fill=self.COLORS[self.color])
        super().draw(img, d, fonts, st)


class App:
    def __init__(self):
        self.fonts = Fonts()
        self.pages = [HomePage(self), SystemPage(self), PaintPage(self)]
        self.index = 0
        n = len(self.pages)
        tw = W // n
        self.tabs = [Button((i * tw + 2, H - TAB_H + 3, (i + 1) * tw - 2, H - 3), p.title,
                            (lambda i=i: self.select(i)))
                     for i, p in enumerate(self.pages)]

    @property
    def page(self):
        return self.pages[self.index]

    def select(self, i):
        self.index = i

    def touch(self, ev):
        if ev.y >= H - TAB_H or any(t.pressed for t in self.tabs):
            changed = False
            for t in self.tabs:
                if ev.kind == "down" and t.hit(ev.x, ev.y):
                    t.pressed = changed = True
                elif ev.kind == "up" and t.pressed:
                    t.pressed = False
                    changed = True
                    if t.hit(ev.x, ev.y):
                        t.on_tap()
            if changed or ev.kind != "move":
                return changed
        return self.page.touch(ev)

    def render(self, st):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        # ステータスバー
        d.rectangle((0, 0, W, STATUS_H - 1), fill=PANEL)
        f = self.fonts.get(12, bold=True)
        d.text((8, 4), st["now"].strftime("%H:%M"), font=f, fill=FG)
        title = self.page.title
        d.text(((W - text_w(d, title, f)) // 2, 4), title, font=f, fill=MUTED)
        bat, chg = st.get("bat"), st.get("charging")
        btxt = "--" if bat is None else "%d%%" % bat
        bw = text_w(d, btxt, f)
        d.text((W - 8 - bw, 4), btxt, font=f, fill=FG)
        draw_battery(d, W - 8 - bw - 30, 5, bat, chg)
        draw_wifi(d, W - 8 - bw - 56, 4, st.get("wifi"))
        # 本体
        self.page.draw(img, d, self.fonts, st)
        # タブ
        d.rectangle((0, H - TAB_H, W, H), fill=BG)
        d.line((0, H - TAB_H, W, H - TAB_H), fill=LINE)
        for i, t in enumerate(self.tabs):
            t.draw(d, self.fonts, active=(i == self.index))
        return img


def sample_status(now=None):
    return {"now": now or datetime.datetime(2026, 11, 19, 1, 23, 45), "bat": 72, "charging": True,
            "wifi": 64, "ssid": "aterm-443a02-g", "ip": "192.168.0.20",
            "temp": 48.3, "load": 0.42, "mem": 61.0}
