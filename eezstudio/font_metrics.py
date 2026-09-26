#!/usr/bin/env python3
"""LVGL font metric helper for label alignment scripts.

The agent needs per-glyph ink position (top, bottom, mid within the line)
to visually center labels across mixed fonts — FontAwesome icons,
Montserrat text, custom Roboto-Mono digit subsets, etc. Each font has
different line metrics and each glyph has different ink position within
its line. The only authoritative source is the generated `ui_font_*.c`
file itself; PIL is reliable only for full-charset Montserrat (the
LVGL built-in).

This module provides:
  - LvglFont: parses one `ui_font_*.c`; exposes line_height, base_line,
    per-glyph descriptors, and codepoint→glyph mapping via cmap.
  - ink_range_for(font, char): (top, bot) within the line for a single char.
  - text_ink_range(font, text): union (top, bot) for the rendered string.
  - text_adv_w(font, text): total horizontal advance in pixels.
  - mont_ink_range(size, text): PIL-based ink bbox for LVGL built-in
    Montserrat. SAFE because LVGL's built-in Montserrat uses the same
    full-charset line metrics PIL sees.

USAGE (in a project's tmp/align_*.py script):

    import os, sys
    sys.path.insert(0, os.path.expanduser("~/.claude/skills/eezstudio"))
    from font_metrics import LvglFont, text_ink_range, text_adv_w, mont_ink_range

    rm48 = LvglFont("main/ui/ui_font_roboto_mono_48.c")
    top, bot = text_ink_range(rm48, "85")
    ink_mid = (top + bot) / 2
    label_top = row_y_center - ink_mid       # ink-centered placement

    pair_w = text_adv_w(rm48, "85") + 4 + mont_text_w(22, "%")
"""

import os, re
from PIL import ImageFont

# ---------- LVGL ui_font_*.c parser ----------

_DESC_RE = re.compile(
    r"\.bitmap_index\s*=\s*\d+,\s*"
    r"\.adv_w\s*=\s*(\d+),\s*"
    r"\.box_w\s*=\s*(\d+),\s*"
    r"\.box_h\s*=\s*(\d+),\s*"
    r"\.ofs_x\s*=\s*(-?\d+),\s*"
    r"\.ofs_y\s*=\s*(-?\d+)"
)

_CMAP_HEADER_RE = re.compile(
    r"\.range_start\s*=\s*(\d+),\s*"
    r"\.range_length\s*=\s*(\d+),\s*"
    r"\.glyph_id_start\s*=\s*(\d+)"
)

_UL_RE = re.compile(
    r"static const uint16_t unicode_list_(\d+)\[\]\s*=\s*\{([^}]+)\}"
)


class LvglFont:
    """Parsed view of a single ui_font_*.c file."""

    def __init__(self, path):
        txt = open(path).read()
        self.path = path
        self.line_height = int(re.search(r"\.line_height\s*=\s*(\d+)", txt).group(1))
        self.base_line = int(re.search(r"\.base_line\s*=\s*(\d+)", txt).group(1))
        # Each glyph descriptor — index matches the LVGL glyph_id
        self.descs = [
            {"adv_w": int(m[0]), "box_w": int(m[1]), "box_h": int(m[2]),
             "ofs_x": int(m[3]), "ofs_y": int(m[4])}
            for m in _DESC_RE.findall(txt)
        ]
        # Stitch cmaps with their unicode_list arrays
        headers = list(_CMAP_HEADER_RE.finditer(txt))
        lists = {int(m.group(1)): [int(v.strip(), 0)
                                   for v in m.group(2).split(",") if v.strip()]
                 for m in _UL_RE.finditer(txt)}
        self.cmaps = []
        for i, h in enumerate(headers):
            self.cmaps.append({
                "range_start": int(h.group(1)),
                "range_length": int(h.group(2)),
                "glyph_id_start": int(h.group(3)),
                "unicode_list": lists.get(i, []),
            })

    def glyph_id(self, codepoint):
        """Return the glyph descriptor index for codepoint, or None."""
        for cm in self.cmaps:
            if cm["unicode_list"]:
                offset = codepoint - cm["range_start"]
                if offset in cm["unicode_list"]:
                    return cm["glyph_id_start"] + cm["unicode_list"].index(offset)
            else:
                if cm["range_start"] <= codepoint < cm["range_start"] + cm["range_length"]:
                    return cm["glyph_id_start"] + (codepoint - cm["range_start"])
        return None

    def ink_range(self, char):
        """(ink_top, ink_bot) within the line for a single character, or None."""
        gid = self.glyph_id(ord(char))
        if gid is None or gid >= len(self.descs):
            return None
        d = self.descs[gid]
        if d["box_h"] == 0:
            return None
        top = self.line_height - self.base_line - d["ofs_y"] - d["box_h"]
        bot = self.line_height - self.base_line - d["ofs_y"]
        return top, bot

    def adv_w_px(self, char):
        """Advance width in pixels for a single character (rounded)."""
        gid = self.glyph_id(ord(char))
        if gid is None or gid >= len(self.descs):
            return 0
        return self.descs[gid]["adv_w"] / 16.0


def text_ink_range(font, text):
    """Union ink bbox (top, bot) for the rendered string."""
    parts = [font.ink_range(c) for c in text]
    parts = [p for p in parts if p is not None]
    if not parts:
        # Fall back to centered line (works for whitespace-only strings)
        mid = (font.line_height - font.base_line) // 2
        return mid - 1, mid + 1
    return min(p[0] for p in parts), max(p[1] for p in parts)


def text_ink_mid(font, text):
    """Convenience: (ink_top + ink_bot) / 2 for the string."""
    top, bot = text_ink_range(font, text)
    return (top + bot) / 2.0


def text_adv_w(font, text):
    """Total horizontal advance in pixels for the string (sum, rounded)."""
    return int(round(sum(font.adv_w_px(c) for c in text)))


# ---------- LVGL built-in Montserrat — PIL is safe here ----------

_MONT_TTF = os.path.join(
    os.environ.get("FONT_DIR", os.path.expanduser("~/.local/share/fonts")),
    "Montserrat-Medium.ttf",
)
_mont_pil_cache = {}

def _mont_pil(size):
    if size not in _mont_pil_cache:
        _mont_pil_cache[size] = ImageFont.truetype(_MONT_TTF, size)
    return _mont_pil_cache[size]


def mont_ink_range(size, text):
    """PIL ink (y0, y1) for LVGL built-in MONTSERRAT_<size> rendering `text`.
    SAFE: LVGL's lv_font_montserrat_<size> uses the same TTF and full
    charset, so its line metrics match PIL's. NOT safe for subsetted
    custom fonts (use LvglFont)."""
    f = _mont_pil(size)
    x0, y0, x1, y1 = f.getbbox(text)
    return y0, y1


def mont_ink_mid(size, text):
    y0, y1 = mont_ink_range(size, text)
    return (y0 + y1) / 2.0


def mont_text_w(size, text):
    f = _mont_pil(size)
    x0, y0, x1, y1 = f.getbbox(text)
    return x1 - x0


# ---------- LVGL line_height for any font, including Montserrat built-ins ----------

LVGL_FONT_DIR_HINTS = [
    os.path.expanduser(
        "~/.cache/Espressif/ComponentManager/"
        "service_d92d8f1e/lvgl__lvgl_8.4.0_d7c1ac03/src/font"
    ),
]


def lvgl_line_height(font_name, project_ui_dir=None):
    """Return LVGL line_height for a font name as used in `text_font`.
    Looks up in project's main/ui/ first for custom fonts, then in the
    LVGL component cache for built-in Montserrat."""
    if font_name.startswith("MONTSERRAT_"):
        sz = int(font_name.rsplit("_", 1)[1])
        for d in LVGL_FONT_DIR_HINTS:
            p = f"{d}/lv_font_montserrat_{sz}.c"
            if os.path.exists(p):
                return _read_line_height(p)
        # Fallback: rough heuristic — LVGL Montserrat line_height ≈ size * 1.1
        return int(round(sz * 1.1))
    if project_ui_dir:
        p = f"{project_ui_dir}/ui_font_{font_name}.c"
        if os.path.exists(p):
            return _read_line_height(p)
    return None


def _read_line_height(path):
    return int(re.search(r"\.line_height\s*=\s*(\d+)", open(path).read()).group(1))
