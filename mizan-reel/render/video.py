"""Mizan Tracker — Instagram reel renderer (1080x1920, 30fps).

Deterministic: every frame is a pure function of time. No network, no randomness
beyond fixed seeds.
"""
import os
import sys
import json
import math
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx
import shape as shp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

W, H = 1080, 1920
FPS = 30

FONTS = os.environ.get("MZ_FONTS", os.path.join(ROOT, "assets", "fonts"))
AR_BOLD = os.path.join(FONTS, "Cairo-Arabic-Bold.ttf")
AR_REG = os.path.join(FONTS, "Cairo-Arabic.ttf")
AR_AMIRI = os.path.join(FONTS, "Amiri-Arabic.ttf")
LAT_BOLD = os.path.join(FONTS, "Inter-Bold.ttf")
LAT_BLK = os.path.join(FONTS, "Inter-Black.ttf")
LAT = os.path.join(FONTS, "Inter.ttf")
SERIF = os.path.join(FONTS, "Playfair-Bold.ttf")

# ---------------------------------------------------------------- palette
GREEN = (14, 59, 46)
GREEN_DEPTH = (7, 29, 23)
GREEN_MID = (20, 72, 55)
CREAM = (245, 241, 230)
CREAM_D = (232, 225, 206)
GOLD = (230, 193, 92)
GOLD_D = (198, 158, 44)
GOLD_L = (245, 216, 132)
INK = (16, 38, 30)
WHITE = (255, 253, 246)

ease = gfx.ease
ease_out = gfx.ease_out
clamp = gfx.clamp
lerp = gfx.lerp
keyframe = gfx.keyframe


# ---------------------------------------------------------------- resources
def load_bg(name):
    im = Image.open(os.path.join(ASSETS, "broll", name)).convert("RGB")
    # pre-scale so ken-burns crops stay cheap and sharp
    iw, ih = im.size
    s = max(W * 1.5 / iw, H * 1.5 / ih)
    return im.resize((int(iw * s), int(ih * s)), Image.LANCZOS)


BG = {}


def bg(name):
    if name not in BG:
        BG[name] = load_bg(name)
    return BG[name]


_APP = None


def app_screen():
    global _APP
    if _APP is None:
        _APP = Image.open(os.path.join(ASSETS, "ui", "app_screen.png")).convert("RGB")
    return _APP


def kb(img, zoom=1.0, ox=0.0, oy=0.0, blur=0.0):
    """Ken-burns crop of a pre-scaled image."""
    iw, ih = img.size
    cw, ch = W * zoom, H * zoom
    s = max(cw / iw, ch / ih)
    nw, nh = cw / s, ch / s
    x = (iw - nw) / 2 + ox * iw
    y = (ih - nh) / 2 + oy * ih
    x = clamp(x, 0, iw - nw)
    y = clamp(y, 0, ih - nh)
    out = img.crop((int(x), int(y), int(x + nw), int(y + nh))).resize((W, H), Image.LANCZOS)
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    return out


# ---------------------------------------------------------------- sprites
_TS = {}


def spr_ar(text, size, color=WHITE, font=AR_BOLD, tracking=0.0):
    key = ("ar", text, size, color, font, tracking)
    if key not in _TS:
        img = shp.render_rtl(text, font, LAT_BOLD, size, color, tracking)
        # tight-crop
        bbox = img.getbbox() or (0, 0, 1, 1)
        _TS[key] = img.crop(bbox)
    return _TS[key]


def spr_lat(text, size, color=WHITE, font=SERIF, tracking=0.0):
    key = ("lat", text, size, color, font, tracking)
    if key not in _TS:
        sh = shp.shaper()
        img, adv, _ = sh.render(text, font, size, color, tracking=tracking)
        bbox = img.getbbox() or (0, 0, 1, 1)
        img = img.crop((0, 0, max(1, bbox[2]), bbox[3] if False else img.size[1]))
        _TS[key] = img
    return _TS[key]


def put(im, spr, cx, cy, scale=1.0, alpha=1.0, rot=0.0, blur=0.0, anchor="c"):
    if alpha <= 0.003:
        return
    s = spr
    if abs(scale - 1.0) > 0.002:
        nw, nh = max(1, int(s.size[0] * scale)), max(1, int(s.size[1] * scale))
        s = s.resize((nw, nh), Image.LANCZOS)
    if abs(rot) > 0.05:
        s = s.rotate(rot, resample=Image.BICUBIC, expand=True)
    if blur > 0.15:
        s = s.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 0.997:
        a = s.getchannel("A").point(lambda v: int(v * alpha))
        s = s.copy()
        s.putalpha(a)
    w, h = s.size
    if anchor == "c":
        x, y = cx - w / 2, cy - h / 2
    elif anchor == "r":     # right edge at cx, vertically centred
        x, y = cx - w, cy - h / 2
    elif anchor == "l":
        x, y = cx, cy - h / 2
    else:
        x, y = cx - w / 2, cy - h / 2
    im.alpha_composite(s, (int(round(x)), int(round(y))))


def reveal(im, spr, cx, cy, p, dy=40, blur=0.0, scale=1.0, alpha=1.0):
    """Slide-up + fade reveal clipped to the sprite's own height."""
    if p <= 0:
        return
    e = ease_out(p)
    put(im, spr, cx, cy + (1 - e) * dy, scale=scale, alpha=alpha * min(1.0, p * 1.8), blur=blur)


def tex_grain(im, strength=16):
    g = gfx.grain(W, H)
    layer = g.copy()
    a = np.array(layer.getchannel("A"), np.float32) * (strength / 26.0)
    layer.putalpha(Image.fromarray(a.clip(0, 255).astype(np.uint8)))
    im.alpha_composite(layer)


def finish(im, vig=105, grain=15):
    im.alpha_composite(gfx.vignette(W, H, vig))
    tex_grain(im, grain)
    return im


def base_bg(img, dark=0.55, zoom=1.0, ox=0.0, oy=0.0, blur=0.0):
    frame = Image.new("RGBA", (W, H), GREEN_DEPTH + (255,))
    b = kb(img, zoom, ox, oy, blur).convert("RGBA")
    if dark:
        d = Image.new("RGBA", (W, H), (4, 16, 12, int(255 * dark)))
        b = Image.alpha_composite(b, d)
    frame.alpha_composite(b)
    return frame


def green_wash(im, alpha=140):
    im.alpha_composite(Image.new("RGBA", (W, H), GREEN + (alpha,)))


def pattern_over(im, alpha=12):
    im.alpha_composite(gfx.pattern(W, H, alpha))


def logo_lock(im, cx, cy, scale=1.0, alpha=1.0, mark=True, tagline=True):
    """Crescent + MIZAN TRACKER lockup."""
    a = alpha
    if mark:
        r = 46 * scale
        gfx.crescent(im, cx, cy - 62 * scale, r, color=GOLD, disc=None)
    t = spr_lat("MIZAN TRACKER", 62 * scale, WHITE, SERIF, tracking=8 * scale)
    put(im, t, cx, cy + 46 * scale, alpha=a)
    if tagline:
        s = spr_ar("توازنك اليومي، خطوة بخطوة", 34 * scale, GOLD_L)
        put(im, s, cx, cy + 108 * scale, alpha=a * 0.95)


# ---------------------------------------------------------------- audio plan
def vo_plan():
    raw = json.load(open(os.path.join(ASSETS, "vo", "trim.json")))
    gap = 0.42
    t = 0.55
    plan = []
    for k in ["01_hook", "02_problem", "03_app", "04_progress", "05_minutes", "06_cta"]:
        plan.append({"file": k, "start": round(t, 3), "dur": raw[k]})
        t += raw[k] + gap
    total = plan[-1]["start"] + plan[-1]["dur"] + 1.9
    return plan, total


# ---------------------------------------------------------------- scenes
def scene1(t, dur):
    """HOOK — 'how many times did you tell yourself: tomorrow?'"""
    p = clamp(t / dur, 0, 1)
    f = base_bg(bg("b1_night_phone.png"), dark=0.42,
                zoom=lerp(1.28, 1.10, ease(p)), ox=0.0, oy=lerp(0.03, -0.02, ease(p)))
    # bottom scrim for type
    f.alpha_composite(gfx.scrim(W, H, from_top=False, h_frac=0.62, strength=225))
    f.alpha_composite(gfx.scrim(W, H, from_top=True, h_frac=0.28, strength=150))
    pattern_over(f, 10)

    # open push-in
    q = clamp(t / 0.45, 0, 1)
    if q < 1:
        f = f.filter(ImageFilter.GaussianBlur((1 - q) * 6))

    cx = 540
    y1 = 1085
    l1 = spr_ar("شحال من مرة قلتي لراسك:", 52, CREAM)
    reveal(f, l1, cx, y1, clamp((t - 0.55) / 0.55, 0, 1), dy=34)

    l2 = spr_ar("من غدا نبدّل؟", 100, GOLD)
    p2 = clamp((t - 1.35) / 0.6, 0, 1)
    sc = 1.0 + 0.22 * (1 - ease_out(p2)) + 0.02 * math.sin(t * 6.0) * clamp((t - 2.0) / 1.0, 0, 1)
    put(f, l2, cx, y1 + 122, scale=sc, alpha=clamp(p2 * 1.6, 0, 1))
    # gold flare on the punch
    fl = clamp((t - 1.35) / 0.55, 0, 1)
    if 0 < fl < 1:
        a = int(120 * (1 - fl))
        band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(band).rectangle([0, y1 + 70, W, y1 + 176], fill=GOLD + (a,))
        f.alpha_composite(band.filter(ImageFilter.GaussianBlur(30)))

    # underline swipe
    pw = clamp((t - 2.05) / 0.45, 0, 1)
    if pw > 0:
        d = ImageDraw.Draw(f)
        half = 300 * ease_out(pw)
        d.line([(cx - half, y1 + 186), (cx + half, y1 + 186)], fill=GOLD + (110,), width=3)

    l3 = spr_ar("ومن غدا، اللي هو اليوم…", 50, CREAM)
    reveal(f, l3, cx, y1 + 258, clamp((t - 3.35) / 0.55, 0, 1), dy=30)
    l4 = spr_ar("والو ما تبدّل.", 66, WHITE)
    p4 = clamp((t - 4.55) / 0.5, 0, 1)
    put(f, l4, cx, y1 + 348, scale=1.0 + 0.08 * (1 - ease_out(p4)), alpha=p4)

    # dim everything slightly after the punchline
    dim = clamp((t - 5.0) / 0.8, 0, 1) * 0.45
    if dim > 0:
        f.alpha_composite(Image.new("RGBA", (W, H), (4, 16, 12, int(255 * dim))))

    # sign-off card: brand stamp
    pst = clamp((t - 5.4) / 0.7, 0, 1)
    if pst > 0:
        s = spr_lat("@mizan.tracker", 34, GOLD_L, LAT_BOLD, tracking=2)
        put(f, s, cx, 1660, alpha=pst)

    return finish(f, 120, 16)


def scene2(t, dur):
    """PROBLEM — the issue isn't intention, it's following through."""
    p = clamp(t / dur, 0, 1)
    f = base_bg(bg("b2_laptop_desk.png"), dark=0.5,
                zoom=lerp(1.05, 1.30, ease(p)), ox=lerp(0.04, -0.03, ease(p)), oy=0.02)
    f.alpha_composite(gfx.scrim(W, H, from_top=False, h_frac=0.7, strength=235))
    pattern_over(f, 10)
    cx = 540

    a = spr_ar("المشكل ماشي فالنية.", 72, CREAM)
    reveal(f, a, cx, 1210, clamp(t / 0.55, 0, 1), dy=44)
    b = spr_ar("النية كاينة.", 52, (196, 214, 202))
    reveal(f, b, cx, 1310, clamp((t - 1.35) / 0.5, 0, 1), dy=26)

    # broken progress bar
    pb = clamp((t - 2.2) / 0.7, 0, 1)
    if pb > 0:
        n = 8
        seg_w, gap = 78, 14
        total = n * seg_w + (n - 1) * gap
        x0 = cx - total / 2
        d = ImageDraw.Draw(f)
        for i in range(n):
            segp = clamp((pb * n - i) / 1.0, 0, 1)
            if segp <= 0:
                continue
            filled = i < 5
            col = GOLD if filled else (255, 255, 255)
            xx = x0 + i * (seg_w + gap)
            d.rounded_rectangle([xx, 1420, xx + seg_w * segp, 1434], radius=7,
                                fill=col + ((255,) if filled else (46,)))
        # the cut
        cut = clamp((t - 3.3) / 0.5, 0, 1)
        if cut > 0:
            gxx = x0 + 5 * (seg_w + gap) - gap / 2
            d.line([(gxx, 1390), (gxx, 1462)], fill=(250, 240, 225, int(220 * cut)), width=3)

    c = spr_ar("المشكل فالمتابعة.", 86, GOLD)
    pc = clamp((t - 3.55) / 0.55, 0, 1)
    put(f, c, cx, 1610, scale=1.0 + 0.14 * (1 - ease_out(pc)), alpha=pc)

    return finish(f, 120, 16)


def _homography(dst, src):
    """3x3 H mapping dst -> src (for sampling)."""
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B.append(v)
    h = np.linalg.solve(np.array(A, np.float64), np.array(B, np.float64))
    return np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])


def persp_paste(frame, ui, quad, brightness=1.0, alpha=1.0, blur=0.0):
    """Paste `ui` into a 4-point quad (TL,TR,BR,BL) with a real homography."""
    q = np.array(quad, np.float64)
    pad = 3
    x0, y0 = q[:, 0].min(), q[:, 1].min()
    x1, y1 = q[:, 0].max(), q[:, 1].max()
    Wp, Hp = int(round(x1 - x0)) + 1, int(round(y1 - y0)) + 1
    if Wp < 4 or Hp < 4:
        return
    iw, ih = ui.size
    Hm = _homography([(px - x0, py - y0) for px, py in q],
                     [(0.0, 0.0), (float(iw), 0.0), (float(iw), float(ih)), (0.0, float(ih))])
    gx, gy = np.meshgrid(np.arange(Wp, dtype=np.float64) + 0.5,
                         np.arange(Hp, dtype=np.float64) + 0.5)
    den = Hm[2, 0] * gx + Hm[2, 1] * gy + Hm[2, 2]
    sx = (Hm[0, 0] * gx + Hm[0, 1] * gy + Hm[0, 2]) / den
    sy = (Hm[1, 0] * gx + Hm[1, 1] * gy + Hm[1, 2]) / den
    xi = np.clip(np.rint(sx - 0.5), 0, iw - 1).astype(np.int32)
    yi = np.clip(np.rint(sy - 0.5), 0, ih - 1).astype(np.int32)
    src = np.array(ui.convert("RGB"), np.uint8)[yi, xi]
    mask = Image.new("L", (Wp, Hp), 0)
    ImageDraw.Draw(mask).polygon([(px - x0 - 0.5, py - y0 - 0.5) for px, py in q], fill=255)
    if brightness != 1.0:
        src = (src.astype(np.float32) * brightness).clip(0, 255).astype(np.uint8)
    out = Image.fromarray(src, "RGB").convert("RGBA")
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    m = mask if alpha >= 1 else mask.point(lambda v: int(v * alpha))
    out.putalpha(m)
    frame.alpha_composite(out, (int(round(x0)), int(round(y0))))


def screen_quad_paste(frame, ui, corners, brightness=1.0, alpha=1.0, blur=0.0):
    """Paste the app UI into an arbitrary (nearly axis-aligned) quad."""
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    w = max(2, int(max(xs) - min(xs)))
    h = max(2, int(max(ys) - min(ys)))
    ui2 = ui.resize((w, h), Image.LANCZOS)
    if brightness != 1.0:
        arr = np.array(ui2).astype(np.float32) * brightness
        ui2 = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    if blur:
        ui2 = ui2.filter(ImageFilter.GaussianBlur(blur))
    # rotation from the top edge
    ang = -math.degrees(math.atan2(corners[1][1] - corners[0][1],
                                   corners[1][0] - corners[0][0]))
    ui2 = ui2.rotate(ang, resample=Image.BICUBIC, expand=True)
    img = ui2.convert("RGBA")
    if alpha < 1:
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    ccx = sum(xs) / 4
    ccy = sum(ys) / 4
    frame.alpha_composite(img, (int(ccx - img.size[0] / 2), int(ccy - img.size[1] / 2)))


def scene3(t, dur):
    """REVEAL — the laptop, the product, a light sweep."""
    p = clamp(t / dur, 0, 1)
    zoom = lerp(1.52, 1.30, ease(p))
    ox = lerp(0.0, -0.02, ease(p))
    oy = lerp(0.0, -0.035, ease(p))
    f = base_bg(bg("b4_laptop_front.png"), dark=0.12, zoom=zoom, ox=ox, oy=oy)
    pattern_over(f, 6)

    # screen corners in the *cropped* frame coordinate space
    def corners_for(zoom, ox, oy):
        img = bg("b4_laptop_front.png")
        iw, ih = img.size
        cw, ch = W * zoom, H * zoom
        sc_ = max(cw / iw, ch / ih)
        nw, nh = cw / sc_, ch / sc_
        x = clamp((iw - nw) / 2 + ox * iw, 0, iw - nw)
        y = clamp((ih - nh) / 2 + oy * ih, 0, ih - nh)
        k = W / nw
        # quad corners in *original image* pixels -> normalised -> bg-image px
        base = [(355.1, 602.0), (665.7, 654.0), (629.5, 870.4), (318.9, 818.5)]
        return [((px / 768.0 * iw - x) * k, (py / 1376.0 * ih - y) * k) for px, py in base]

    corners = corners_for(zoom, ox, oy)

    # screen switches on
    pon = clamp((t - 0.55) / 0.75, 0, 1)
    if pon > 0:
        persp_paste(f, app_screen(), corners, brightness=0.95, alpha=ease(pon))

        # light sweep across the screen
        ps = clamp((t - 1.35) / 1.05, 0, 1)
        if 0 < ps < 1:
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(gl)
            gx = lerp(min(xs) - 160, max(xs) + 160, ease(ps))
            d.polygon([(gx, min(ys) - 80), (gx + 90, min(ys) - 80),
                       (gx + 30, max(ys) + 80), (gx - 60, max(ys) + 80)],
                      fill=(255, 250, 230, 90))
            gl = gl.filter(ImageFilter.GaussianBlur(26))
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).polygon([(x, y) for x, y in corners], fill=255)
            gl.putalpha(Image.composite(gl.getchannel("A"), Image.new("L", (W, H), 0), mask))
            f.alpha_composite(gl)

    # bottom type
    f.alpha_composite(gfx.scrim(W, H, from_top=False, h_frac=0.42, strength=215))
    cx = 540
    p1 = clamp((t - 1.5) / 0.6, 0, 1)
    a = spr_ar("هاذي هي ميزان تراكر", 78, WHITE)
    put(f, a, cx, 1565, scale=1.0 + 0.06 * (1 - ease_out(p1)), alpha=p1)
    p2 = clamp((t - 2.3) / 0.5, 0, 1)
    b = spr_ar("صلاتك · أذكارك · وردك · أهدافك", 42, GOLD_L)
    put(f, b, cx, 1655, alpha=p2, scale=1.0 + 0.02 * (1 - ease_out(p2)))
    p3 = clamp((t - 3.1) / 0.5, 0, 1)
    c = spr_ar("كلشي فبلاصة وحدة.", 46, CREAM)
    put(f, c, cx, 1740, alpha=p3)

    # push into the screen for the cut
    pp = clamp((t - (dur - 1.05)) / 1.05, 0, 1)
    if pp > 0:
        z = 1.0 + 1.5 * ease(pp)
        big = f.resize((int(W * z), int(H * z)), Image.BILINEAR)
        offx = (big.size[0] - W) / 2 - (corners[0][0] + corners[2][0]) / 2 * (z - 1) * 0.6
        offy = (big.size[1] - H) / 2 - (corners[0][1] + corners[2][1]) / 2 * (z - 1) * 0.6
        offx = clamp(offx, 0, big.size[0] - W)
        offy = clamp(offy, 0, big.size[1] - H)
        f = big.crop((int(offx), int(offy), int(offx) + W, int(offy) + H))
        f = f.filter(ImageFilter.GaussianBlur(pp * 3.2))

    return finish(f, 110, 16)


# ---- in-app scene -------------------------------------------------------
CARD_W, CARD_H = 1360, 944      # 1440x1000 dashboard crop, kept in proportion


def app_card(f, cx, cy, scale, rot=0.0, alpha=1.0, shadow=True):
    w, h = int(CARD_W * scale), int(CARD_H * scale)
    if w < 8 or h < 8:
        return None
    img = app_screen().resize((w, h), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(18 * scale), fill=255)
    img.putalpha(mask)
    if rot:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        sw, shh = img.size
        d.rounded_rectangle([cx - sw / 2 + 0, cy - shh / 2 + 26, cx + sw / 2, cy + shh / 2 + 26],
                            radius=int(20 * scale), fill=(0, 0, 0, 130))
        sh = sh.filter(ImageFilter.GaussianBlur(34))
        f.alpha_composite(sh)
    if alpha < 1:
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    pos = (int(cx - img.size[0] / 2), int(cy - img.size[1] / 2))
    f.alpha_composite(img, pos)
    return (pos[0], pos[1], img.size[0], img.size[1])


def chip(f, text, cx, cy, alpha=1.0, scale=1.0, dot=True):
    s = spr_ar(text, int(38 * scale), WHITE)
    pad = int(26 * scale)
    w = s.size[0] + pad * 2 + (int(22 * scale) if dot else 0)
    h = int(66 * scale)
    box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=GREEN + (232,),
                        outline=(GOLD + (150,)), width=2)
    if dot:
        d.ellipse([pad - int(4 * scale), h / 2 - int(5 * scale),
                   pad + int(6 * scale), h / 2 + int(5 * scale)], fill=GOLD + (255,))
    box.alpha_composite(s, (pad + (int(22 * scale) if dot else 0), int((h - s.size[1]) / 2)))
    if alpha < 1:
        box.putalpha(box.getchannel("A").point(lambda v: int(v * alpha)))
    f.alpha_composite(box, (int(cx - w / 2), int(cy - h / 2)))
    return (cx - w / 2, cy - h / 2, w, h)


def scene4(t, dur):
    """IN THE APP — camera tour over the real dashboard."""
    f = Image.new("RGBA", (W, H), GREEN_DEPTH + (255,))
    f.alpha_composite(gfx.vgrad_layer(W, H, (20, 74, 57), (5, 24, 19)))
    pattern_over(f, 14)

    P = clamp(t / dur, 0, 1)
    e = ease(P)
    keys = [
        (0.00, (540, 1010, 0.80)),
        (0.10, (540, 1000, 0.84)),
        (0.26, (770, 950, 1.10)),
        (0.42, (430, 960, 1.34)),
        (0.58, (840, 940, 1.70)),
        (0.74, (470, 1050, 1.60)),
        (0.88, (880, 1090, 1.44)),
        (1.00, (545, 905, 1.24)),
    ]
    cx, cy, sc = keyframe(P, keys)
    sc *= 1 + 0.012 * math.sin(t * 0.9)

    box = app_card(f, cx, cy, sc, rot=lerp(-3.2, 2.2, e))
    bx, by, bw, bh = box
    k = bw / 1440.0

    def pt(px, py):
        return (bx + px * k, by + py * (bh / 1000.0))

    # ---- persistent label at the top
    labels = [(0.0, "واجهة وحدة، كلشي فيها"), (4.3, "نسبة التوازن"), (6.8, "صلاتك"),
              (9.0, "سلسلة الأيام")]
    for i, (t0, txt) in enumerate(labels):
        t1 = labels[i + 1][0] if i + 1 < len(labels) else dur + 1
        if t0 <= t < t1:
            fade = clamp((t - t0) / 0.35, 0, 1) * clamp((t1 - t) / 0.3, 0, 1)
            chip(f, txt, 540, 250, alpha=fade)

    # ---- live ring (percentage climbs)
    t_ring = clamp((t - 4.3) / 2.4, 0, 1)
    if t_ring > 0:
        rc = pt(1102, 350)
        rad = 56 * k
        arc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(arc)
        d.ellipse([rc[0] - rad, rc[1] - rad, rc[0] + rad, rc[1] + rad], fill=(11, 48, 36, 255))
        end = -90 + 360 * lerp(0.28, 0.66, ease(t_ring))
        d.arc([rc[0] - rad, rc[1] - rad, rc[0] + rad, rc[1] + rad], -90, end,
              fill=GOLD + (255,), width=max(2, int(4 * k)))
        f.alpha_composite(arc)
        pct = int(round(lerp(28, 66, ease(t_ring))))
        s = spr_lat(f"{pct}%", int(30 * k / 0.72), WHITE, SERIF)
        put(f, s, rc[0], rc[1] - 2 * k)
        s2 = spr_lat("Daily balance", int(10 * k), (175, 192, 180), LAT)
        put(f, s2, rc[0], rc[1] + 22 * k)

    # ---- streak chip
    if t > 9.3:
        n = 3 if t < 10.0 else 4
        pulse = 1 + 0.12 * math.exp(-max(0.0, t - 10.0) * 7)
        chip(f, f"{n} أيام متتالية", 540, 1665, alpha=clamp((t - 9.3) / 0.4, 0, 1),
             scale=pulse if t >= 10.0 else 1.0)

    # ---- closing line
    if t > 10.4:
        s = spr_ar("بلا لوم. بلا ضغط.", 54, GOLD_L)
        put(f, s, 540, 1795, alpha=clamp((t - 10.4) / 0.45, 0, 1))

    return finish(f, 90, 14)


def scene5(t, dur):
    """FIVE MINUTES + the monthly competition (cream editorial beat)."""
    f = Image.new("RGBA", (W, H), CREAM + (255,))
    d = ImageDraw.Draw(f)
    d.rectangle([0, 0, W, 10], fill=GREEN)
    d.rectangle([0, H - 10, W, H], fill=GREEN)
    pattern_over(f, 6)

    if t < 4.9:
        # ---------- minutes beat ----------
        p5 = clamp((t - 0.1) / 0.65, 0, 1)
        s = spr_lat("5", 430, GREEN, LAT_BLK)
        put(f, s, 430, 760, scale=1 + 0.10 * (1 - ease_out(p5)), alpha=p5)
        s = spr_ar("دقايق", 118, GREEN)
        put(f, s, 730, 700, alpha=clamp((t - 0.5) / 0.5, 0, 1))
        s = spr_ar("فالنهار", 82, GOLD_D)
        put(f, s, 720, 810, alpha=clamp((t - 0.75) / 0.5, 0, 1))

        # five anchors filling
        pdd = clamp((t - 1.4) / 1.7, 0, 1)
        for i in range(5):
            x = 250 + i * 145
            filled = pdd * 5 > i + 0.2
            col = GREEN if filled else (216, 208, 186)
            d.ellipse([x - 26, 1030 - 26, x + 26, 1030 + 26], fill=col)
            if filled:
                d.line([(x - 10, 1030), (x - 2, 1039), (x + 11, 1021)], fill=CREAM, width=6)

        s = spr_ar("و نتا شايف راسك كتقدّم.", 62, INK)
        reveal(f, s, 540, 1220, clamp((t - 2.4) / 0.55, 0, 1), dy=34)
        s = spr_ar("خمس دقايق. بصح.", 44, (126, 138, 124))
        put(f, s, 540, 1330, alpha=clamp((t - 3.2) / 0.55, 0, 1))

        # soft card with the three anchors
        pc = clamp((t - 3.5) / 0.55, 0, 1)
        if pc > 0:
            card = Image.new("RGBA", (880, 250), (0, 0, 0, 0))
            dc = ImageDraw.Draw(card)
            dc.rounded_rectangle([0, 0, 879, 249], radius=28, fill=(255, 253, 247, 255),
                                 outline=(228, 220, 198, 255), width=2)
            items = ["أذكار الصباح", "ورد القرآن", "صلاة فـوقت"]
            for i, it in enumerate(items):
                yy = 42 + i * 72
                dc.ellipse([36, yy - 9, 54, yy + 9], fill=GREEN + (255,))
                dc.line([(40, yy), (45, yy + 6), (52, yy - 7)], fill=CREAM, width=3)
                t_ = spr_ar(it, 38, INK)
                card.alpha_composite(t_, (86, int(yy - t_.size[1] / 2)))
                dc.ellipse([806, yy - 6, 818, yy + 6], fill=(198, 190, 168, 255))
            put(f, card, 540, 1540, scale=1 + 0.06 * (1 - ease_out(pc)), alpha=pc)
        return finish(f, 50, 10)

    # ---------- competition beat ----------
    tt = t - 4.9
    f = Image.new("RGBA", (W, H), CREAM + (255,))
    d = ImageDraw.Draw(f)
    d.rectangle([0, 0, W, 10], fill=GREEN)
    d.rectangle([0, H - 10, W, H], fill=GREEN)
    pattern_over(f, 6)

    s = spr_ar("و كل شهر…", 50, (128, 140, 126))
    put(f, s, 540, 470, alpha=clamp(tt / 0.28, 0, 1))
    s = spr_ar("منافسة", 124, GREEN)
    put(f, s, 540, 600, alpha=clamp((tt - 0.12) / 0.3, 0, 1),
        scale=1 + 0.06 * (1 - ease_out(clamp(tt / 0.7, 0, 1))))
    s = spr_ar("شهر مجاني ديال ميزان برو", 60, INK)
    put(f, s, 540, 740, alpha=clamp((tt - 0.55) / 0.4, 0, 1))

    # gold ticket card
    pk = clamp((tt - 0.95) / 0.5, 0, 1)
    if pk > 0:
        card = Image.new("RGBA", (860, 330), (0, 0, 0, 0))
        dc = ImageDraw.Draw(card)
        dc.rounded_rectangle([0, 0, 859, 329], radius=36, fill=GREEN + (255,))
        dc.rounded_rectangle([16, 16, 843, 313], radius=26, outline=GOLD + (170,), width=3)
        dc.ellipse([760, 240, 800, 280], fill=GOLD + (60,))
        gfx.crescent(card, 430, 118, 58, color=GOLD)
        lab = spr_lat("MIZAN PRO", 42, GOLD_L, SERIF, tracking=5)
        card.alpha_composite(lab, (int(430 - lab.size[0] / 2), 205))
        put(f, card, 540, 1010, scale=1 + 0.10 * (1 - ease_out(pk)), alpha=pk)

    s = spr_ar("كون أول واحد فاللائحة.", 50, INK)
    put(f, s, 540, 1275, alpha=clamp((tt - 1.75) / 0.45, 0, 1))

    # gold sparkles (deterministic)
    if tt > 0.95:
        rng = np.random.default_rng(11)
        for i in range(22):
            ang = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(160, 430)
            delay = rng.uniform(0, 0.2)
            tq = clamp((tt - 0.95 - delay) / 1.4, 0, 1)
            if tq <= 0:
                continue
            x = 540 + math.cos(ang) * sp * ease_out(tq) * 1.3
            y = 1010 + math.sin(ang) * sp * ease_out(tq) * 0.8 + 240 * tq * tq
            a = 1 - tq ** 1.6
            r = rng.uniform(7, 16) * (0.7 + 0.5 * (1 - tq))
            col = GOLD if i % 3 else GOLD_D
            star = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ds = ImageDraw.Draw(star)
            ds.polygon([(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y),
                        (x + r * 0.22, y + r * 0.22), (x, y + r),
                        (x - r * 0.22, y + r * 0.22), (x - r, y),
                        (x - r * 0.22, y - r * 0.22)], fill=col + (int(235 * a),))
            f.alpha_composite(star)

    return finish(f, 50, 10)


def scene6(t, dur):
    """CTA — download / open the site."""
    p = clamp(t / dur, 0, 1)
    f = base_bg(bg("b3_morning_smile.png"), dark=0.30,
                zoom=lerp(1.22, 1.06, ease(p)), ox=0.0, oy=lerp(0.02, 0.0, ease(p)))
    green_wash(f, 120)
    f.alpha_composite(gfx.scrim(W, H, from_top=True, h_frac=0.5, strength=225))
    f.alpha_composite(gfx.scrim(W, H, from_top=False, h_frac=0.62, strength=240))
    pattern_over(f, 12)
    cx = 540

    # logo lockup
    pl = clamp(t / 0.6, 0, 1)
    gfx.crescent(f, cx, 430, 52, color=GOLD)
    s = spr_lat("MIZAN TRACKER", 66, WHITE, SERIF, tracking=7)
    put(f, s, cx, 530, alpha=pl, scale=1 + 0.06 * (1 - ease_out(pl)))
    s = spr_ar("توازنك اليومي، خطوة بخطوة", 38, GOLD_L)
    put(f, s, cx, 600, alpha=clamp((t - 0.35) / 0.5, 0, 1))

    # three value chips
    vals = ["صلاتك", "أذكارك", "وردك القرآني"]
    for i, v in enumerate(vals):
        pa = clamp((t - (0.8 + i * 0.16)) / 0.45, 0, 1)
        chip(f, v, cx - 250 + i * 250, 905, alpha=pa, scale=0.86)

    # url card
    pu = clamp((t - 1.45) / 0.6, 0, 1)
    if pu > 0:
        card = Image.new("RGBA", (900, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, 899, 199], radius=34, fill=CREAM + (255,))
        d.rounded_rectangle([0, 0, 899, 199], radius=34, outline=GOLD + (200,), width=3)
        u = spr_lat("mizantracker.online", 70, GREEN, LAT_BLK)
        card.alpha_composite(u, (int((900 - u.size[0]) / 2), 40))
        sub = spr_ar("دخل دابا · مجاني", 34, GOLD_D)
        card.alpha_composite(sub, (int((900 - sub.size[0]) / 2), 128))
        sc = 1 + 0.10 * (1 - ease_out(pu))
        put(f, card, cx, 1095, scale=sc, alpha=pu)

    # arrow pointing down, pulsing
    pa = clamp((t - 2.3) / 0.5, 0, 1)
    if pa > 0:
        bounce = 14 * math.sin((t - 2.3) * 4.0) if t > 2.3 else 0
        d = ImageDraw.Draw(f)
        ay = 1250 + bounce
        d.line([(cx, ay), (cx, ay + 54)], fill=GOLD + (int(230 * pa),), width=7)
        d.line([(cx - 24, ay + 30), (cx, ay + 56)], fill=GOLD + (int(230 * pa),), width=7)
        d.line([(cx + 24, ay + 30), (cx, ay + 56)], fill=GOLD + (int(230 * pa),), width=7)

    # handle
    ph = clamp((t - 2.7) / 0.6, 0, 1)
    s = spr_lat("@mizan.tracker", 40, WHITE, LAT_BOLD, tracking=2)
    put(f, s, cx, 1800, alpha=ph * 0.92)

    # fade out at the very end
    fo = clamp((t - (dur - 0.9)) / 0.9, 0, 1)
    if fo > 0:
        f.alpha_composite(Image.new("RGBA", (W, H), (4, 14, 11, int(255 * fo * 0.85))))

    return finish(f, 110, 15)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


def build_plan():
    vo, total = vo_plan()
    # scene boundaries: cut just before the next VO line
    bounds = [0.0]
    for i in range(1, len(vo)):
        bounds.append(round(vo[i]["start"] - 0.30, 3))
    bounds.append(round(total, 3))
    return vo, bounds


def cut_punch(im, tau, strength=0.045, dur=0.26):
    """Slight scale-down punch right after a hard cut."""
    p = clamp(tau / dur, 0, 1)
    if p >= 1:
        return im
    z = 1 + strength * (1 - ease_out(p))
    big = im.resize((int(round(W * z)), int(round(H * z))), Image.BILINEAR)
    x = (big.size[0] - W) // 2
    y = (big.size[1] - H) // 2
    return big.crop((x, y, x + W, y + H))


def render_frame(t, vo, bounds):
    for i in range(len(SCENES)):
        a, b = bounds[i], bounds[i + 1]
        if a <= t < b:
            im = SCENES[i](t - a, b - a)
            if i > 0:
                im = cut_punch(im, t - a)
            return im.convert("RGB")
    return SCENES[-1](0.01, 1.0).convert("RGB")


def main():
    out_dir = os.path.join(ROOT, "out")
    os.makedirs(out_dir, exist_ok=True)
    vo, bounds = build_plan()
    total = bounds[-1]
    print(json.dumps({"bounds": bounds, "total": total}, indent=1))
    n = int(round(total * FPS))

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw_path = os.path.join(out_dir, "video_raw.mp4")
    cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", raw_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    only = os.environ.get("MZ_STILLS")
    if only:
        for spec in only.split(","):
            tt = float(spec)
            im = render_frame(tt, vo, bounds)
            p = os.path.join(out_dir, f"still_{tt:05.2f}.png")
            im.save(p)
            print("still", p)
        proc.stdin.close()
        proc.wait()
        return

    for i in range(n):
        t = i / FPS
        im = render_frame(t, vo, bounds)
        proc.stdin.write(im.tobytes())
        if i % 60 == 0:
            print(f"frame {i}/{n}  ({t:.2f}s)", flush=True)
    proc.stdin.close()
    proc.wait()
    print("raw video done:", raw_path)
    json.dump({"bounds": bounds, "total": total}, open(os.path.join(out_dir, "plan.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
