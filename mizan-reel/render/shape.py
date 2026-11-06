"""HarfBuzz shaping + FreeType raster fill for Arabic (and Latin) text.

Pillow's own layout uses a basic shaping engine and our Cairo subset only holds
presentation forms for single letters, so Arabic is shaped here and drawn as
per-glyph images on an alpha mask: correct joins, RTL order, and kerning.
"""
import os
import numpy as np
from PIL import Image, ImageFont, ImageDraw
import uharfbuzz as hb

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.environ.get("MZ_FONTS", os.path.join(HERE, "..", "assets", "fonts"))

_cache = {}
_faces = {}


def _blob_face(path):
    if path in _faces:
        return _faces[path]
    data = open(path, "rb").read()
    face = hb.Face(data)
    font = hb.Font(face)
    _faces[path] = (font, data)
    return _faces[path]


def shape(text, font_path, size, rtl=None):
    """Return list of (glyph_id, x_offset, y_offset, x_advance) in pixels."""
    key = (text, font_path, size)
    if key in _cache:
        return _cache[key]
    font, data = _blob_face(font_path)
    upem = font.face.upem
    scale = size / upem
    hb_font = hb.Font(hb.Face(data))
    hb_font.scale = (int(size * 64), int(size * 64))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    if rtl is True:
        buf.direction = "rtl"
    elif rtl is False:
        buf.direction = "ltr"
    hb.shape(hb_font, buf, {})
    out = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((info.codepoint, pos.x_offset / 64.0, pos.y_offset / 64.0, pos.x_advance / 64.0))
    _cache[key] = out
    return out


def glyph_img(font_path, gid, size):
    """Render one glyph (GID) as an L mask at the right size."""
    key = (font_path, gid, size)
    if key in _cache:
        return _cache[key]
    font, data = _blob_face(font_path)
    upem = font.face.upem
    # temp font file for FreeType glyph loading
    from PIL import ImageFont as IF
    ft = IF.truetype(font_path, int(round(size)))
    try:
        mask, off = ft.getmask2(bytes([0]), mode="L")  # placeholder
    except Exception:
        mask, off = None, None
    _cache[key] = (ft,)
    raise RuntimeError("use freetype path")


class Shaper:
    """Rasterise shaped runs into RGBA images."""

    def __init__(self):
        import freetype
        self.freetype = freetype
        self._faces = {}
        self._glyphs = {}
        self.measurers = {}

    def _face(self, path):
        if path not in self._faces:
            f = self.freetype.Face(path)
            f.set_pixel_sizes(0, 200)  # render big, scale later
            self._faces[path] = f
        return self._faces[path]

    def render(self, text, font_path, size, color=(255, 255, 255), tracking=0.0,
               supersample=1.0):
        """Return (RGBA image, advance_width)."""
        sz = size * supersample
        glyphs = shape(text, font_path, sz)
        face = self._face(font_path)
        face.set_pixel_sizes(0, int(round(sz)))
        imgs = []
        pen = 0.0
        minx = 1e9
        miny = 1e9
        maxx = -1e9
        maxy = -1e9
        for gid, xo, yo, xa in glyphs:
            key = (font_path, gid, int(round(sz)))
            if key not in self._glyphs:
                face.load_glyph(gid, self.freetype.FT_LOAD_RENDER)
                bmp = face.glyph.bitmap
                w, h = bmp.width, bmp.rows
                if w and h:
                    arr = np.array(bmp.buffer, dtype=np.uint8).reshape(h, bmp.pitch)[:, :w]
                    g = Image.fromarray(arr.copy(), mode="L")
                else:
                    g = Image.new("L", (1, 1), 0)
                self._glyphs[key] = (g, face.glyph.bitmap_left, face.glyph.bitmap_top,
                                     face.glyph.advance.x / 64.0)
            g, left, top, adv = self._glyphs[key]
            gx = pen + xo + left
            gy = -yo - top
            imgs.append((g, gx, gy))
            minx = min(minx, gx)
            miny = min(miny, gy)
            maxx = max(maxx, gx + g.size[0])
            maxy = max(maxy, gy + g.size[1])
            pen += xa + tracking * supersample
        if not imgs or maxx <= minx:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0.0, 0.0
        pad = 3
        W = int(np.ceil(maxx - minx)) + pad * 2
        H = int(np.ceil(maxy - miny)) + pad * 2
        mask = Image.new("L", (W, H), 0)
        for g, gx, gy in imgs:
            mask.paste(g, (int(round(gx - minx)) + pad, int(round(gy - miny)) + pad),
                       g)
        out = Image.new("RGBA", (W, H), tuple(color) + (0,))
        out.putalpha(mask)
        adv = pen / supersample
        return out, adv, (minx / supersample, miny / supersample)


_SH = None


def shaper():
    global _SH
    if _SH is None:
        _SH = Shaper()
    return _SH


def draw(im, text, font_path, size, xy, color=(255, 255, 255), anchor="la",
         alpha=255, tracking=0.0, box=None):
    """Draw shaped text on an RGBA image. Returns (x0,y0,x1,y1)."""
    sh = shaper()
    img, adv, _ = sh.render(text, font_path, size, color, tracking=tracking)
    w, h = img.size
    x, y = xy
    if 'm' in anchor:
        if anchor[0] == "m":
            x -= w / 2
        elif anchor[0] == "r":
            x -= w
    if anchor[1] == "m":
        y -= h / 2
    elif anchor[1] in ("s", "b"):
        y -= h
    if alpha < 255:
        a = img.getchannel("A").point(lambda v: int(v * alpha / 255))
        img.putalpha(a)
    if box is not None:
        # hard clip inside box (x0,y0,x1,y1)
        bx0, by0, bx1, by1 = [int(v) for v in box]
        cx0, cy0 = int(round(x)), int(round(y))
        sub = img.crop((max(0, bx0 - cx0), max(0, by0 - cy0),
                        min(w, bx1 - cx0), min(h, by1 - cy0)))
        im.alpha_composite(sub, (max(cx0, bx0), max(cy0, by0)))
        return (cx0, cy0, cx0 + w, cy0 + h)
    im.alpha_composite(img, (int(round(x)), int(round(y))))
    return (x, y, x + w, y + h)


def measure(text, font_path, size, tracking=0.0):
    sh = shaper()
    img, adv, _ = sh.render(text, font_path, size, (255, 255, 255), tracking=tracking)
    return img.size[0]


AR_RANGE = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
            (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]


def _is_ar(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in AR_RANGE)


def _runs(text):
    """Split into (is_arabic, substring) runs."""
    out = []
    cur = ""
    cur_ar = None
    for ch in text:
        a = _is_ar(ch)
        if cur_ar is None or a == cur_ar:
            cur += ch
            cur_ar = a
        else:
            out.append((cur_ar, cur))
            cur, cur_ar = ch, a
    if cur:
        out.append((cur_ar, cur))
    return out


def render_rtl(text, ar_font, lat_font, size, color=(255, 255, 255), tracking=0.0):
    """Render a (mostly Arabic) string mixing Arabic and Latin/punctuation fonts.

    Returns an RGBA sprite laid out right-to-left.
    """
    sh = shaper()
    parts = []
    for is_ar, seg in _runs(text):
        f = ar_font if is_ar else lat_font
        img, adv, _ = sh.render(seg, f, size, color, tracking=tracking)
        parts.append(img)
    W = sum(p.size[0] for p in parts)
    H = max(p.size[1] for p in parts)
    out = Image.new("RGBA", (max(1, W), max(1, H)), tuple(color) + (0,))
    x = W
    for p in parts:
        x -= p.size[0]
        out.alpha_composite(p, (x, H - p.size[1]))
    return out


def draw_rtl(im, text, xy, size, color=(255, 255, 255), anchor="ma",
             alpha=255, tracking=0.0,
             ar_font=None, lat_font=None):
    ar_font = ar_font or os.path.join(FONTS, "Cairo-Arabic-Bold.ttf")
    lat_font = lat_font or os.path.join(FONTS, "Inter-Bold.ttf")
    img = render_rtl(text, ar_font, lat_font, size, color, tracking)
    w, h = img.size
    x, y = xy
    if anchor[0] == "m":
        x -= w / 2
    elif anchor[0] == "r":
        x -= w
    if anchor[1] == "m":
        y -= h / 2
    elif anchor[1] in ("s", "b"):
        y -= h
    if alpha < 255:
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha / 255)))
    im.alpha_composite(img, (int(round(x)), int(round(y))))
    return (x, y, x + w, y + h)


def measure_rtl(text, size, tracking=0.0, ar_font=None, lat_font=None):
    ar_font = ar_font or os.path.join(FONTS, "Cairo-Arabic-Bold.ttf")
    lat_font = lat_font or os.path.join(FONTS, "Inter-Bold.ttf")
    return render_rtl(text, ar_font, lat_font, size, tracking=tracking).size
