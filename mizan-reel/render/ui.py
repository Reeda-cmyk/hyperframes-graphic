"""Mizan Tracker UI replica renderer (Pillow).

Renders the app screen seen in the user's screenshot at 2x supersampling so it
can be scaled / perspective-warped into the video.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.environ.get("MZ_FONTS", os.path.join(HERE, "..", "assets", "fonts"))

CREAM = (244, 240, 229)
CREAM2 = (248, 244, 234)
SIDE = (247, 243, 232)
LINE = (228, 222, 204)
INK = (18, 39, 31)
INK2 = (45, 62, 52)
MUTED = (108, 122, 112)
MUTED2 = (138, 150, 140)
GREEN = (14, 59, 46)
GREEN_L = (23, 80, 63)
GOLD = (201, 162, 39)
GOLD_L = (240, 199, 94)
WHITE = (255, 255, 255)

FONT_FILES = {
    "serif": "Playfair-Bold.ttf",
    "serifm": "Playfair-Med.ttf",
    "sans": "Inter.ttf",
    "sansb": "Inter-Bold.ttf",
    "sansblk": "Inter-Black.ttf",
    "ar": "Amiri-Arabic.ttf",
    "arg": "Cairo-Arabic-Bold.ttf",
    "dejavu": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "dejavub": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}


class C:
    """Canvas with CSS-pixel coordinates and supersampling."""

    def __init__(self, w, h, s=2):
        self.s = s
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * s, h * s), CREAM)
        self.d = ImageDraw.Draw(self.im)
        self._fonts = {}

    # ---------- helpers ----------
    def font(self, name, size):
        p = FONT_FILES[name]
        if not os.path.isabs(p) and not os.path.exists(os.path.join(F, p)):
            p = os.path.join(HERE, "..", "compose", "fonts", p)
        else:
            p = os.path.join(F, p) if not os.path.isabs(p) else p
        key = (p, size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(p, int(round(size * self.s)))
        return self._fonts[key]

    def p(self, *v):
        return [x * self.s for x in v]

    def rect(self, x, y, w, h, fill=None, r=0, outline=None, ow=1):
        s = self.s
        box = [x * s, y * s, (x + w) * s, (y + h) * s]
        if r:
            self.d.rounded_rectangle(box, radius=r * s, fill=fill, outline=outline,
                                     width=int(ow * s) if outline else 0)
        else:
            self.d.rectangle(box, fill=fill, outline=outline,
                             width=int(ow * s) if outline else 0)

    def text(self, x, y, s, fnt, fill, anchor="la", tracking=0):
        if not s:
            return
        if tracking:
            cx = x
            for ch in s:
                self.d.text((cx * self.s, y * self.s), ch, font=fnt, fill=fill, anchor=anchor)
                cx += self.d.textlength(ch, font=fnt) / self.s + tracking
            return
        self.d.text((x * self.s, y * self.s), s, font=fnt, fill=fill, anchor=anchor)

    def tw(self, s, fnt, tracking=0):
        if tracking:
            return sum(self.d.textlength(ch, font=fnt) for ch in s) / self.s + tracking * (len(s) - 1)
        return self.d.textlength(s, font=fnt) / self.s

    def circle(self, cx, cy, r, fill=None, outline=None, ow=1):
        s = self.s
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s],
                       fill=fill, outline=outline, width=int(ow * s) if outline else 0)

    def line(self, pts, fill, width=1):
        s = self.s
        self.d.line([(x * s, y * s) for x, y in pts], fill=fill, width=max(1, int(width * s)),
                    joint="curve")

    def vgrad(self, x, y, w, h, c1, c2, r=0, steps=256):
        s = self.s
        W, H = int(w * s), max(1, int(h * s))
        g = np.zeros((H, W, 3), dtype=np.uint8)
        t = np.linspace(0, 1, H)[:, None, None]
        for i in range(3):
            g[:, :, i] = (np.array(c1[i]) * (1 - t) + np.array(c2[i]) * t).astype(np.uint8)[:, 0, 0][:, None]
        gi = Image.fromarray(g)
        if r:
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=int(r * s), fill=255)
            self.im.paste(gi, (int(x * s), int(y * s)), mask)
        else:
            self.im.paste(gi, (int(x * s), int(y * s)))

    def radial_glow(self, cx, cy, r, color, alpha=0.3):
        s = self.s
        d = int(2 * r * s)
        yy, xx = np.mgrid[0:d, 0:d]
        dist = np.sqrt((xx - d / 2) ** 2 + (yy - d / 2) ** 2) / (d / 2)
        a = np.clip(1 - dist, 0, 1) ** 2 * alpha
        layer = Image.new("RGBA", (d, d), tuple(color) + (0,))
        layer.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
        self.im.paste(layer, (int((cx - r) * s), int((cy - r) * s)), layer)

    def icon(self, kind, cx, cy, size, color=(124, 140, 129), w=1.2):
        """Tiny vector icons drawn from primitives."""
        h = size / 2
        s = self.s
        dd = self.d
        col = color
        ww = max(1, int(w * s))

        def ell(box, fill=None, outline=None):
            dd.ellipse([v * s for v in box], fill=fill, outline=outline, width=ww if outline else 0)

        def rct(box, r=0, fill=None, outline=None):
            if r:
                dd.rounded_rectangle([v * s for v in box], radius=r * s, fill=fill, outline=outline,
                                     width=ww if outline else 0)
            else:
                dd.rectangle([v * s for v in box], fill=fill, outline=outline, width=ww if outline else 0)

        def pl(pts):
            dd.line([(x * s, y * s) for x, y in pts], fill=col, width=ww, joint="curve")

        if kind == "grid":
            for i in range(2):
                for j in range(2):
                    rct([cx - h + i * (h + 0.6), cy - h + j * (h + 0.6),
                         cx - h + i * (h + 0.6) + h - 0.6, cy - h + j * (h + 0.6) + h - 0.6],
                        r=0.8, outline=col)
        elif kind == "heart":
            dd.arc([cx - h, cy - h * 0.9, cx, cy + h * 0.35], 180, 360, fill=col, width=ww)
            dd.arc([cx, cy - h * 0.9, cx + h, cy + h * 0.35], 180, 360, fill=col, width=ww)
            pl([(cx - h, cy - h * 0.15), (cx, cy + h), (cx + h, cy - h * 0.15)])
        elif kind == "pen":
            pl([(cx - h, cy + h), (cx - h * 0.3, cy + h * 0.6), (cx + h, cy - h * 0.7)])
        elif kind == "target":
            ell([cx - h, cy - h, cx + h, cy + h], outline=col)
            ell([cx - h * 0.45, cy - h * 0.45, cx + h * 0.45, cy + h * 0.45], outline=col)
        elif kind == "cal":
            rct([cx - h, cy - h * 0.8, cx + h, cy + h], r=1, outline=col)
            pl([(cx - h, cy - h * 0.2), (cx + h, cy - h * 0.2)])
        elif kind == "swap":
            pl([(cx - h, cy - h * 0.4), (cx + h * 0.7, cy - h * 0.4), (cx + h * 0.7, cy - h * 0.9)])
            pl([(cx + h, cy + h * 0.4), (cx - h * 0.7, cy + h * 0.4), (cx - h * 0.7, cy + h * 0.9)])
        elif kind == "chart":
            for i, hh in enumerate([0.5, 1.0, 0.75]):
                x0 = cx - h + i * (h * 0.9)
                rct([x0, cy + h - hh * h, x0 + h * 0.55, cy + h], r=0.4, fill=col)
        elif kind == "spark":
            pl([(cx, cy - h), (cx, cy + h)])
            pl([(cx - h, cy), (cx + h, cy)])
            pl([(cx - h * 0.55, cy - h * 0.55), (cx + h * 0.55, cy + h * 0.55)])
        elif kind == "list":
            for i in range(3):
                yy = cy - h + i * h
                ell([cx - h, yy - 0.7, cx - h + 1.4, yy + 0.7], fill=col)
                pl([(cx - h * 0.2, yy), (cx + h, yy)])
        elif kind == "book":
            rct([cx - h, cy - h * 0.8, cx + h, cy + h * 0.9], r=1, outline=col)
            pl([(cx - h * 0.2, cy - h * 0.8), (cx - h * 0.2, cy + h * 0.9)])
        elif kind == "crown":
            pl([(cx - h, cy + h * 0.5), (cx - h, cy - h * 0.5), (cx - h * 0.45, cy + h * 0.1),
                (cx, cy - h * 0.8), (cx + h * 0.45, cy + h * 0.1), (cx + h, cy - h * 0.5),
                (cx + h, cy + h * 0.5), (cx - h, cy + h * 0.5)])
        elif kind == "shield":
            pl([(cx - h, cy - h * 0.7), (cx, cy - h), (cx + h, cy - h * 0.7),
                (cx - h * 0.2, cy + h), (cx - h, cy - h * 0.7)])
        elif kind == "gear":
            ell([cx - h * 0.55, cy - h * 0.55, cx + h * 0.55, cy + h * 0.55], outline=col)
            for a in range(0, 360, 45):
                ar = np.radians(a)
                pl([(cx + np.cos(ar) * h * 0.62, cy + np.sin(ar) * h * 0.62),
                    (cx + np.cos(ar) * h, cy + np.sin(ar) * h)])
        elif kind == "card":
            rct([cx - h, cy - h * 0.65, cx + h, cy + h * 0.65], r=1.2, outline=col)
            pl([(cx - h, cy - h * 0.1), (cx + h, cy - h * 0.1)])
        elif kind == "ticket":
            rct([cx - h, cy - h * 0.65, cx + h, cy + h * 0.65], r=1.2, outline=col)
            pl([(cx + h * 0.15, cy - h * 0.65), (cx + h * 0.15, cy + h * 0.65)])
        elif kind == "guide":
            ell([cx - h, cy - h, cx + h, cy + h], outline=col)
            ell([cx - h * 0.3, cy - h * 0.3, cx + h * 0.3, cy + h * 0.3], fill=col)
        elif kind == "week":
            rct([cx - h, cy - h, cx + h, cy + h], r=1, outline=col)
            pl([(cx - h, cy - h * 0.3), (cx + h, cy - h * 0.3)])
            pl([(cx - h * 0.3, cy - h), (cx - h * 0.3, cy - h * 1.35)])
        elif kind == "ticket2":
            rct([cx - h, cy - h * 0.6, cx + h, cy + h * 0.6], r=1.2, outline=col)
        elif kind == "down":
            pl([(cx - h, cy - h * 0.35), (cx, cy + h * 0.4), (cx + h, cy - h * 0.35)])
        elif kind == "comm":
            ell([cx - h, cy - h, cx + h * 0.4, cy + h * 0.4], outline=col)
            ell([cx - h * 0.1, cy + h * 0.1, cx + h, cy + h], outline=col)

    # ---------- output ----------
    def save(self, path, size=None):
        im = self.im
        if size:
            im = im.resize(size, Image.LANCZOS)
        else:
            im = im.resize((self.w, self.h), Image.LANCZOS)
        im.save(path)
        return im


def logo_mark(c, cx, cy, r):
    """Green disc + gold crescent + star."""
    s = c.s
    c.circle(cx, cy, r, fill=(18, 53, 42))
    # crescent: gold disc minus offset green disc
    d = int(2 * r * s) + 4
    mask = Image.new("L", (d, d), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, d - 1, d - 1], fill=255)
    off = r * 0.46 * s
    md.ellipse([off * 0.9, -off * 0.15, d - 1 + off * 0.9, d - 1 - off * 0.15], fill=0)
    gold = Image.new("RGB", (d, d), GOLD_L)
    c.im.paste(gold, (int(cx * s - d / 2), int(cy * s - d / 2)), mask)
    c.circle(cx + r * 0.52, cy - r * 0.52, r * 0.17, fill=GOLD_L)


def render_app(out_path, W=1440, H=1200, s=2):
    c = C(W, H, s)
    d = c.d

    # ---------------- top bar ----------------
    c.rect(0, 0, W, 66, fill=CREAM2)
    c.line([(0, 66), (W, 66)], LINE, 1)
    logo_mark(c, 34, 33, 15)
    c.text(54, 19, "Mizan", c.font("serif", 21), INK)
    c.text(55, 42, "DEEN & HABITS", c.font("sans", 7), MUTED2, tracking=1.5)

    # top nav pill
    nav = [("sun", "Today", True), ("cal", "Day planner", False), ("target", "Focus", False),
           ("list", "Habits", False), ("book", "Quran", False)]
    f_nav = c.font("sans", 11.5)
    widths = [c.tw(t, f_nav) + 32 for _, t, _ in nav]
    total = sum(widths) + 6
    nx = W / 2 - total / 2
    c.rect(nx, 15, total, 36, fill=(251, 248, 239), r=11, outline=LINE, ow=1)
    x = nx + 3
    for (ic, t, active), w in zip(nav, widths):
        if active:
            c.rect(x, 19, w, 28, fill=GREEN, r=8)
            col = (243, 239, 226)
        else:
            col = (84, 101, 91)
        c.icon(ic, x + 13, 33, 9, color=(237, 231, 213) if active else (124, 140, 129))
        c.text(x + 21, 33, t, (c.font("sansb", 11.5) if active else f_nav), col, anchor="lm")
        x += w + 3

    # right cluster
    rx = W - 22
    c.rect(rx - 60, 20, 60, 26, fill=(233, 226, 206), r=13)
    c.text(rx - 43, 33, "G", c.font("sansb", 11), (60, 75, 66), anchor="mm")
    c.text(rx - 30, 33, "⌄", c.font("dejavu", 10), (107, 122, 112), anchor="mm")
    rx -= 72
    pill_w = 118
    c.rect(rx - pill_w, 19, pill_w, 28, fill=(251, 248, 239), r=9, outline=LINE, ow=1)
    c.rect(rx - pill_w + 3, 22, 36, 22, fill=GREEN, r=7)
    c.text(rx - pill_w + 21, 33, "Light", c.font("sans", 10), (243, 239, 226), anchor="mm")
    c.text(rx - pill_w + 60, 33, "Dark", c.font("sans", 10), (108, 122, 112), anchor="mm")
    c.text(rx - pill_w + 95, 33, "System", c.font("sans", 10), (108, 122, 112), anchor="mm")
    rx -= pill_w + 14
    c.text(rx - 26, 33, "EN", c.font("sans", 11), (91, 106, 96), anchor="mm")
    c.icon("globe", rx - 44, 33, 9, color=(124, 140, 129))

    # ---------------- sidebar ----------------
    c.rect(0, 67, 230, H - 67, fill=SIDE)
    c.line([(230, 67), (230, H)], LINE, 1)
    f_sh = c.font("sansb", 8)
    f_si = c.font("sans", 11.5)
    y = 88
    groups = [
        ("YOUR SPACE", [("grid", "Overview"), ("heart", "Adhkar"), ("pen", "Journal")]),
        ("GROW WITH INTENTION", [("comm", "Community"), ("target", "Niyyah & Goals"), ("cal", "Monthly Planner"),
                                 ("swap", "Barakah Routines"), ("chart", "Insights"), ("spark", "AI Guide"),
                                 ("week", "Weekly Review"), ("crown", "Barakah Challenges"), ("ticket", "Ticket")]),
        ("PRIVATE", [("shield", "Owner control")]),
    ]
    for gi, (head, items) in enumerate(groups):
        if gi:
            y += 10
        c.text(20, y, head, f_sh, (154, 167, 157), tracking=0.9)
        y += 20
        for ic, label in items:
            c.icon(ic, 26, y + 4, 9.5, color=(124, 140, 129))
            c.text(39, y + 4, label, f_si, (75, 90, 81), anchor="lm")
            y += 23
    y = H - 188
    c.icon("gear", 26, y, 9.5, color=(124, 140, 129))
    c.text(39, y, "Settings", f_si, (75, 90, 81), anchor="lm")
    y += 23
    c.icon("card", 26, y, 9.5, color=(124, 140, 129))
    c.text(39, y, "Membership", f_si, (75, 90, 81), anchor="lm")
    # vip card
    c.rect(12, H - 118, 206, 100, fill=(252, 250, 243), r=10, outline=(226, 219, 198), ow=1)
    c.text(24, H - 100, "Your VIP space", c.font("sansb", 10), (44, 64, 52))
    c.text(24, H - 82, "All your tools, in one quiet place.", c.font("sans", 8.5), (138, 150, 140))
    c.text(24, H - 58, "Manage membership", c.font("sans", 8.5), (44, 64, 52))
    c.line([(24, H - 52), (83, H - 52)], (44, 64, 52), 0.7)

    # ---------------- main column ----------------
    M = 230 + 26          # left edge of content
    R = W - 26            # right edge
    CW = R - M            # content width
    top = 88
    c.circle(M + 3, top + 5, 2.4, fill=(60, 122, 92))
    c.text(M + 11, top, "Your everyday, in balance", c.font("sans", 9.5), (126, 141, 131))

    c.text(M, top + 22, "As-salamu alaykum, Guts.", c.font("serif", 31), (18, 39, 31))
    c.text(M, top + 66, "Make space for what matters. One small step at a time.",
           c.font("sans", 11.5), MUTED)

    # preview pill
    pp = "PREVIEW FRIDAY DESIGN"
    fpp = c.font("sans", 8)
    pw = c.tw(pp, fpp, tracking=0.8) + 24
    c.rect(R - pw, top + 18, pw, 25, fill=(252, 250, 243), r=13, outline=(226, 219, 198), ow=1)
    c.text(R - pw + 12, top + 30, pp, fpp, (122, 106, 58), anchor="lm", tracking=0.8)

    # date row
    dy = top + 100
    c.icon("cal", M + 5, dy + 4, 10, color=(124, 140, 129))
    c.text(M + 16, dy + 4, "Thursday 5 November, 25 Jumada al-Oula 1448 AH",
           c.font("sans", 10.5), MUTED, anchor="lm")
    c.icon("down", M + 268, dy + 4, 5, color=(154, 167, 157), w=1.0)
    fr = "Fajr  in 6h 3min  ·  Rabat"
    fw = c.tw(fr, c.font("sans", 10.5))
    c.text(R, dy + 4, fr, c.font("sans", 10.5), MUTED2, anchor="rm")

    # ---------------- banner ----------------
    by = dy + 24
    c.vgrad(M, by, CW, 74, (251, 247, 234), (246, 239, 218), r=12)
    c.rect(M, by, CW, 74, r=12, outline=(228, 220, 196), ow=1)
    c.circle(M + 34, by + 37, 16, fill=(240, 230, 200))
    c.icon("crown", M + 34, by + 37, 12, color=(169, 138, 43), w=1.1)
    c.rect(M + 60, by + 12, 118, 15, fill=(239, 232, 210), r=7)
    c.text(M + 66, by + 19, "MONTHLY COMPETITION", c.font("sans", 7.5), (138, 114, 49),
           anchor="lm", tracking=0.7)
    c.rect(M + 184, by + 12, 106, 15, fill=(245, 227, 168), r=7)
    c.text(M + 190, by + 19, "1 MONTH FREE PRO", c.font("sansb", 7.5), (122, 92, 18),
           anchor="lm", tracking=0.7)
    c.text(M + 60, by + 34, "Show up this month. Win a free month of Mizan Pro.",
           c.font("serif", 15.5), (29, 50, 39))
    c.text(M + 60, by + 56, "#1 on the board · 3 consistent days · 2 participants · 25 days left",
           c.font("sans", 8.5), MUTED2)
    # buttons
    bx2 = R - 14
    lb = "View leaderboard  ›"
    fbtn = c.font("sans", 9.5)
    wb = c.tw(lb, fbtn) + 22
    c.rect(bx2 - wb, by + 26, wb, 26, fill=(253, 251, 244), r=8, outline=(222, 214, 191), ow=1)
    c.text(bx2 - wb + 11, by + 39, lb, fbtn, (75, 90, 81), anchor="lm")
    bx2 -= wb + 7
    gb = "1 Month Free Pro"
    wg = c.tw(gb, c.font("sansb", 9.5)) + 22
    c.rect(bx2 - wg, by + 26, wg, 26, fill=(240, 223, 166), r=8)
    c.icon("crown", bx2 - wg + 12, by + 39, 8, color=(94, 71, 16), w=1)
    c.text(bx2 - wg + 22, by + 39, gb, c.font("sansb", 9.5), (94, 71, 16), anchor="lm")

    # ---------------- hero + quote ----------------
    ry = by + 88
    herow = CW * 0.618
    quotew = CW - herow - 14
    heroh = 284
    c.vgrad(M, ry, herow, heroh, (26, 82, 64), (11, 48, 36), r=14)
    # soft gold glow inside hero
    glow = Image.new("RGBA", (int(herow * s), int(heroh * s)), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([herow * s * 0.55, -heroh * s * 0.25, herow * s * 1.1, heroh * s * 0.85],
               fill=(240, 199, 94, 26))
    glow = glow.filter(ImageFilter.GaussianBlur(40 * s / 2))
    c.im.paste(glow, (int(M * s), int(ry * s)), glow)

    c.text(M + 20, ry + 20, "Your daily intention", c.font("sans", 9.5), (185, 201, 189))
    c.text(M + 20, ry + 42, "Small steps.", c.font("serif", 34), (246, 242, 230))
    c.text(M + 20, ry + 84, "Sincere intentions.", c.font("serif", 34), (246, 242, 230))
    c.text(M + 20, ry + 140, "You don't need a perfect day.", c.font("sans", 11.5), (191, 205, 194))
    c.text(M + 20, ry + 160, "Just a present one.", c.font("sans", 11.5), (191, 205, 194))
    c.rect(M + 20, ry + 196, 108, 32, fill=(251, 248, 238), r=9)
    c.text(M + 32, ry + 212, "+", c.font("sansb", 13), (18, 53, 42), anchor="lm")
    c.text(M + 45, ry + 212, "Begin my day", c.font("sansb", 11.5), (18, 53, 42), anchor="lm")

    # ring
    rcx, rcy, rr = M + herow - 105, ry + 128, 56
    c.circle(rcx, rcy, rr, outline=(255, 255, 255, 40), ow=4)
    arc = Image.new("RGBA", (int(rr * 2.4 * s), int(rr * 2.4 * s)), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arc)
    k = rr * 2.4 * s / 2
    ad.arc([k - rr * s, k - rr * s, k + rr * s, k + rr * s], -90, -90 + 0.28 * 360,
           fill=GOLD_L + (255,), width=int(4 * s))
    c.im.paste(arc, (int(rcx * s - k), int(rcy * s - k)), arc)
    c.text(rcx, rcy - 8, "28%", c.font("serif", 26), (246, 242, 230), anchor="mm")
    c.text(rcx, rcy + 16, "Daily balance", c.font("sans", 9.5), (175, 192, 180), anchor="mm")
    c.text(rcx, ry + heroh - 34, "A little better, every day.", c.font("sans", 9), (159, 180, 166), anchor="mm")

    # quote card
    qx = M + herow + 14
    c.vgrad(qx, ry, quotew, heroh, (18, 66, 50), (11, 47, 35), r=14)
    c.text(qx + 16, ry + 15, "QURAN · QUOTE FOR TODAY", c.font("sans", 7.5), (159, 180, 166), tracking=0.7)
    c.text(qx + quotew - 16, ry + 15, "REFRESHES DAILY", c.font("sans", 7.5), (159, 180, 166),
           anchor="ra")
    ar = get_display(arabic_reshaper.reshape("إِنَّ مَعَ الْعُسْرِ يُسْرًا"))
    c.text(qx + quotew - 18, ry + 58, ar, c.font("ar", 34), (244, 233, 200), anchor="ra")
    c.text(qx + 16, ry + 132, "Indeed, with hardship comes ease.", c.font("serifm", 12.5), (230, 223, 201))
    c.text(qx + 16, ry + 158, "The ease is not after the hardship only.", c.font("sans", 9.5), (159, 180, 166))
    c.text(qx + 16, ry + 174, "It travels with it.", c.font("sans", 9.5), (159, 180, 166))
    c.text(qx + 16, ry + 205, "Ash-Sharh 94:6", c.font("sans", 8.5), (143, 167, 154))

    # ---------------- prayers + calendar ----------------
    py2 = ry + heroh + 14
    ph = 214
    c.rect(M, py2, herow, ph, fill=WHITE, r=14, outline=(237, 231, 214), ow=1)
    c.text(M + 16, py2 + 15, "FIVE DAILY ANCHORS", c.font("sans", 8), (154, 167, 157), tracking=0.8)
    c.text(M + herow - 16, py2 + 15, "3 / 5 prayers", c.font("sans", 8.5), (138, 150, 140), anchor="ra")
    c.text(M + 16, py2 + 32, "Your salah, held gently.", c.font("serif", 17.5), (29, 50, 39))

    prayers = [("Fajr", "5:20", "In jama'ah", (232, 242, 230), (76, 122, 94)),
               ("Dhuhr", "12:12", "On time", (251, 243, 220), (76, 122, 94)),
               ("Asr", "15:09", "Prayed later", (251, 233, 231), (76, 122, 94)),
               ("Maghrib", "17:31", "Not logged", (249, 237, 239), (76, 122, 94)),
               ("Isha", "18:51", "Not logged", (245, 242, 233), (76, 122, 94))]
    gridx, gridy = M + 16, py2 + 64
    gw = herow - 32
    gap = 9
    cellw = (gw - gap * 4) / 5
    for i, (nm, tm, st, bg, ic_col) in enumerate(prayers):
        cx0 = gridx + i * (cellw + gap)
        c.rect(cx0, gridy, cellw, 130, fill=bg, r=10)
        c.circle(cx0 + cellw / 2, gridy + 20, 6.5, outline=ic_col, ow=1.2)
        c.circle(cx0 + cellw / 2, gridy + 20, 2.2, fill=ic_col)
        c.text(cx0 + cellw / 2, gridy + 46, nm, c.font("sansb", 11), INK2, anchor="mm")
        c.text(cx0 + cellw / 2, gridy + 66, tm, c.font("sans", 12.5), (74, 90, 80), anchor="mm")
        c.text(cx0 + cellw / 2, gridy + 100, st, c.font("sans", 8.5), (124, 140, 129), anchor="mm")
    c.line([(M + 16, py2 + ph - 30), (M + herow - 16, py2 + ph - 30)], (241, 236, 221), 1)
    c.circle(M + 19, py2 + ph - 19, 2.2, outline=(154, 167, 157), ow=0.9)
    c.text(M + 26, py2 + ph - 20, "Prayer times for Rabat", c.font("sans", 8), (154, 167, 157))
    c.text(M + herow - 16, py2 + ph - 20, "Your worship, not a score.", c.font("sans", 8),
           (154, 167, 157), anchor="ra")

    # calendar
    cx0 = M + herow + 14
    c.rect(cx0, py2, quotew, ph, fill=WHITE, r=14, outline=(237, 231, 214), ow=1)
    c.text(cx0 + 16, py2 + 15, "A month of small steps", c.font("sansb", 13), INK2)
    c.text(cx0 + 16, py2 + 40, "November 2026", c.font("sansb", 9), INK2)
    c.text(cx0 + quotew - 16, py2 + 40, "Today", c.font("sans", 9), MUTED2, anchor="ra")
    days = ["M", "T", "W", "T", "F", "S", "S"]
    cw2 = (quotew - 32) / 7
    for i, dd in enumerate(days):
        c.text(cx0 + 16 + cw2 * (i + 0.5), py2 + 66, dd, c.font("sans", 8), (166, 177, 168), anchor="mm")
    nums = [26, 27, 28, 29, 30, 31] + list(range(1, 31))
    for i, n in enumerate(nums):
        row, col = divmod(i, 7)
        cxx = cx0 + 16 + cw2 * (col + 0.5)
        cyy = py2 + 88 + row * 21
        if i < 6:
            col_t = (193, 201, 194)
            bgc = None
        elif n in (2, 3, 4):
            col_t = (45, 90, 66)
            bgc = (220, 233, 220)
        elif n == 5:
            col_t = (243, 239, 226)
            bgc = GREEN
        else:
            col_t = (84, 101, 91)
            bgc = None
        if bgc:
            c.circle(cxx, cyy, 10, fill=bgc)
        c.text(cxx, cyy - 1, str(n), c.font("sansb" if n == 5 else "sans", 9.5), col_t, anchor="mm")

    c.save(out_path, size=(W * s, H * s))
    return c


if __name__ == "__main__":
    out = os.path.join(HERE, "..", "assets", "ui")
    os.makedirs(out, exist_ok=True)
    im = render_app(os.path.join(out, "app_ui.png"))
    print("saved")
