"""Small graphics toolkit for the Mizan reel (Pillow/numpy)."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.environ.get("MZ_FONTS", os.path.join(HERE, "..", "assets", "fonts"))

FILES = {
    "serif": "Playfair-Bold.ttf",
    "serifm": "Playfair-Med.ttf",
    "sans": "Inter.ttf",
    "sansb": "Inter-Bold.ttf",
    "sansblk": "Inter-Black.ttf",
    "ar": "Amiri-Arabic.ttf",
    "arg": "Cairo-Arabic-Bold.ttf",
    "arl": "Cairo-Arabic.ttf",
    "arlat": "Cairo-Latin-Bold.ttf",
}

GREEN = (14, 59, 46)
GREEN_DEEP = (8, 33, 26)
GREEN_L = (23, 80, 63)
CREAM = (244, 240, 229)
CREAM_W = (250, 247, 238)
GOLD = (224, 186, 86)
GOLD_D = (201, 162, 39)
GOLD_L = (240, 199, 94)
INK = (18, 39, 31)
MUTED = (150, 168, 158)

_fcache = {}


def font(name, size):
    key = (name, size)
    if key not in _fcache:
        _fcache[key] = ImageFont.truetype(os.path.join(FONTS, FILES[name]), int(size))
    return _fcache[key]


def ar(s):
    return get_display(arabic_reshaper.reshape(s))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease(p):
    p = clamp(p, 0.0, 1.0)
    return 3 * p * p - 2 * p * p * p


def ease_out(p):
    p = clamp(p, 0.0, 1.0)
    return 1 - (1 - p) ** 3


def lerp(a, b, p):
    return a + (b - a) * p


def keyframe(p, keys):
    """keys: list of (pos, value_tuple)."""
    if p <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys) - 1):
        p0, v0 = keys[i]
        p1, v1 = keys[i + 1]
        if p0 <= p <= p1:
            k = ease((p - p0) / max(1e-6, p1 - p0))
            return tuple(lerp(a, b, k) for a, b in zip(v0, v1))
    return keys[-1][1]


def text_w(d, s, fnt, tracking=0.0):
    if tracking:
        return sum(d.textlength(c, font=fnt) for c in s) + tracking * (len(s) - 1)
    return d.textlength(s, font=fnt)


def text(d, xy, s, fnt, fill, anchor="la", tracking=0.0, alpha=255, shadow=None):
    if not s or alpha <= 0:
        return
    x, y = xy
    if tracking:
        w = text_w(d, s, fnt, tracking)
        if anchor[0] == "m":
            x -= w / 2
        elif anchor[0] == "r":
            x -= w
        for ch in s:
            if shadow:
                d.text((x + shadow[0], y + shadow[1]), ch, font=fnt,
                       fill=tuple(shadow[2]) + (int(alpha * shadow[3]),), anchor="l" + anchor[1])
            d.text((x, y), ch, font=fnt, fill=tuple(fill) + (alpha,), anchor="l" + anchor[1])
            x += d.textlength(ch, font=fnt) + tracking
        return
    if shadow:
        d.text((x + shadow[0], y + shadow[1]), s, font=fnt,
               fill=tuple(shadow[2]) + (int(alpha * shadow[3]),), anchor=anchor)
    d.text((x, y), s, font=fnt, fill=tuple(fill) + (alpha,), anchor=anchor)


def rrect(im, box, r, fill=None, outline=None, width=1):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)
    im.alpha_composite(layer)


def soft_shadow(im, box, r, blur=28, alpha=110, offset=(0, 18)):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]],
                        radius=r, fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    im.alpha_composite(layer)


def crescent(im, cx, cy, r, color=GOLD_L, disc=None):
    """Gold crescent + star, drawn as a mask so it stays crisp."""
    d = int(2.4 * r)
    mask = Image.new("L", (d, d), 0)
    md = ImageDraw.Draw(mask)
    k = d / 2
    md.ellipse([k - r, k - r, k + r, k + r], fill=255)
    ox = r * 0.52
    md.ellipse([k - r + ox, k - r - ox * 0.12, k + r + ox, k + r - ox * 0.12], fill=0)
    if disc:
        dd = ImageDraw.Draw(im)
        dd.ellipse([cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2], fill=disc[:3] + (255,))
    col = Image.new("RGBA", (d, d), tuple(color) + (255,))
    im.alpha_composite(col, (int(cx - d / 2), int(cy - d / 2))) if False else None
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    layer.paste(col, (int(cx - d / 2), int(cy - d / 2)), mask)
    # star
    sd = ImageDraw.Draw(layer)
    sd.ellipse([cx + r * 0.42, cy - r * 0.72, cx + r * 0.66, cy - r * 0.48], fill=tuple(color) + (255,))
    im.alpha_composite(layer)


def _pattern_tex(w, h, tile=120, color=(255, 255, 255), alpha=9):
    """Faint eight-point star lattice."""
    t = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    d = ImageDraw.Draw(t)
    cxp = cyp = tile / 2
    R = tile * 0.42
    for rot in (0, 45):
        pts = []
        for i in range(4):
            a = np.radians(rot + i * 90)
            pts.append((cxp + R * np.cos(a), cyp + R * np.sin(a)))
        d.polygon(pts, outline=tuple(color) + (alpha,))
    for x in (0, tile):
        for y in (0, tile):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=tuple(color) + (alpha + 6,))
    tex = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for yy in range(0, h, tile):
        for xx in range(0, w, tile):
            tex.paste(t, (xx, yy))
    return tex


_PAT = {}


def pattern(w, h, alpha=9):
    key = (w, h, alpha)
    if key not in _PAT:
        _PAT[key] = _pattern_tex(w, h, alpha=alpha)
    return _PAT[key]


def vignette(w, h, strength=110):
    key = ("vig", w, h, strength)
    if key in _PAT:
        return _PAT[key]
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - w / 2) / (w / 2)
    dy = (yy - h / 2) / (h / 2)
    r = np.sqrt(dx ** 2 + dy ** 2) / 1.414
    a = np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6 * strength
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, 3] = a.astype(np.uint8)
    out = Image.fromarray(img, "RGBA")
    _PAT[key] = out
    return out


def grain(w, h, seed=7):
    key = ("grain", w, h)
    if key in _PAT:
        return _PAT[key]
    rng = np.random.default_rng(seed)
    n = rng.normal(128, 26, (h, w)).clip(0, 255).astype(np.uint8)
    g = np.dstack([n, n, n, np.full((h, w), 26, np.uint8)])
    out = Image.fromarray(g, "RGBA")
    _PAT[key] = out
    return out


def scrim(w, h, from_top=True, h_frac=0.45, strength=190):
    key = ("scrim", w, h, from_top, round(h_frac, 2), strength)
    if key in _PAT:
        return _PAT[key]
    hh = int(h * h_frac)
    ramp = (np.linspace(1, 0, hh) ** 1.5 * strength).astype(np.uint8)
    a = np.zeros((h, w), np.uint8)
    if from_top:
        a[:hh, :] = ramp[:, None]
    else:
        a[h - hh:, :] = ramp[::-1][:, None]
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = a
    out = Image.fromarray(img, "RGBA")
    _PAT[key] = out
    return out


def vgrad_layer(w, h, c1, c2, alpha1=255, alpha2=255):
    t = np.linspace(0, 1, h)[:, None]
    arr = np.zeros((h, w, 4), np.uint8)
    for i in range(3):
        arr[:, :, i] = (c1[i] * (1 - t) + c2[i] * t).astype(np.uint8)
    arr[:, :, 3] = (alpha1 * (1 - t) + alpha2 * t).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def cover(img, w, h, scale=1.0, ox=0.0, oy=0.0):
    """Cover-crop + optional zoom/offset (fractions)."""
    iw, ih = img.size
    s = max(w / iw, h / ih) * scale
    nw, nh = int(iw * s), int(ih * s)
    r = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - w) / 2 + ox * nw
    y = (nh - h) / 2 + oy * nh
    x = clamp(x, 0, nw - w)
    y = clamp(y, 0, nh - h)
    return r.crop((int(x), int(y), int(x) + w, int(y) + h))


def blurred(img, radius):
    return img.filter(ImageFilter.GaussianBlur(radius))
