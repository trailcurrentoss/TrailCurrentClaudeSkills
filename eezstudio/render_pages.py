#!/usr/bin/env python3
"""
Heavyweight Phase-2 render-and-read verifier for EEZ Studio LVGL projects.

Usage:
    python3 render_pages.py path/to/Project.eez-project [PageName ...]

Renders one PNG per requested page (or all pages if none specified) into
./tmp/preview/<PageName>.png using PIL with the project's actual TTF fonts.

What it catches:
  * Widgets overlapping (rectangles drawn with semi-transparent fills).
  * Text clipped at widget edges (text width measured with the real font).
  * Children extending past their parent's content area (pad_all + border).
  * lv_keyboard / lv_buttonmatrix widgets that have RUNTIME-OVERRIDDEN
    geometry — flagged in red with an annotation so the agent knows to
    verify the C-side `fix_keyboard(kb, x, y, w, h)` pin.

What it doesn't catch:
  * LVGL-engine sub-pixel rendering differences (typically <2 px).
  * Theme-specific style cascades beyond useStyle + localStyles MAIN.DEFAULT.
  * Arc/slider/spinner indicators (drawn as flat rectangles).

This is the renderer the eezstudio skill's Gate 2 ("Render-and-Read after
any .eez-project write") points to. Copy this file into the project's
`tmp/` directory before first use; the agent should keep it in sync with
the project's font list.
"""

import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- Widget types whose geometry is overridden by LVGL at runtime ---------
RUNTIME_OVERRIDDEN = {
    "LVGLKeyboardWidget",       # Trap 13 — needs C-side fix_keyboard(x,y,w,h)
    "LVGLButtonMatrixWidget",   # internal matrix layout
    "LVGLDropdownWidget",       # popup geometry is internal
    "LVGLRollerWidget",
    "LVGLListWidget",           # internal layout
    "LVGLTabviewWidget",        # tab strip + content stack
}

# ---- LVGL built-in Montserrat sizes; mapped to a fallback TTF on disk ------
LVGL_MONTSERRAT_FALLBACK_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]

def find_fallback_ttf():
    for p in LVGL_MONTSERRAT_FALLBACK_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("No fallback TTF found. Install ttf-dejavu or edit "
                     "LVGL_MONTSERRAT_FALLBACK_CANDIDATES.")

# ---- Font loader ----------------------------------------------------------
class FontCache:
    def __init__(self, project_dir, fonts_array):
        self.project_dir = project_dir
        self.fallback = find_fallback_ttf()
        self.fonts = {}
        for f in fonts_array:
            src = f.get("source", {})
            path = src.get("filePath", "")
            size = src.get("size", 14)
            if not path:
                continue
            abs_path = (project_dir / path).resolve()
            if not abs_path.exists():
                print(f"  font {f['name']}: source {abs_path} not found, "
                      f"using fallback")
                self.fonts[f["name"]] = (self.fallback, size)
            else:
                self.fonts[f["name"]] = (str(abs_path), size)

    def get(self, font_name):
        # Built-in Montserrat: UPPERCASE name with size
        m = re.match(r"^MONTSERRAT_(\d+)$", font_name or "")
        if m:
            return self._load_pil(self.fallback, int(m.group(1)))
        if font_name in self.fonts:
            path, size = self.fonts[font_name]
            return self._load_pil(path, size)
        return self._load_pil(self.fallback, 14)

    def _load_pil(self, path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

# ---- Theme + style resolution ---------------------------------------------
def build_color_lookup(project):
    color_names = [c["name"] for c in project.get("colors", [])]
    themes = project.get("themes", [])
    theme = themes[0] if themes else {"colors": []}
    return dict(zip(color_names, theme.get("colors", [])))

def resolve_color(spec, color_lookup, default="#FFFFFF"):
    if not spec:
        return default
    if spec.startswith("#"):
        return spec
    return color_lookup.get(spec, default)

def merge_style(base, override):
    """Shallow-merge two style-definition dicts (MAIN.DEFAULT only)."""
    if not override:
        return base
    out = dict(base or {})
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_style(out[k], v)
        else:
            out[k] = v
    return out

def effective_style(widget, styles_by_name, default_styles):
    """Resolve widget's MAIN.DEFAULT effective style by walking
    useStyle -> defaultStyles[widget_type] -> localStyles."""
    style_name = widget.get("useStyle")
    if not style_name:
        style_name = default_styles.get(widget.get("type"))
    base = {}
    if style_name and style_name in styles_by_name:
        s = styles_by_name[style_name]
        defn = s.get("definition", {}).get("definition", {})
        base = defn.get("MAIN", {}).get("DEFAULT", {})
    local = (widget.get("localStyles") or {}).get("definition", {})
    if isinstance(local, dict):
        base = merge_style(base, local.get("MAIN", {}).get("DEFAULT", {}))
    return base

# ---- Renderer -------------------------------------------------------------
def render_page(page, project, font_cache, color_lookup, out_path):
    root = page["components"][0]
    W = root.get("width", 800)
    H = root.get("height", 480)

    styles_by_name = {s["name"]: s for s in project.get("lvglStyles", {}).get("styles", [])}
    default_styles = project.get("lvglStyles", {}).get("defaultStyles", {})

    img = Image.new("RGBA", (W, H), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    overflow_msgs = []
    runtime_overrides = []

    def render_widget(w, parent_abs_x, parent_abs_y,
                      parent_content_w, parent_content_h,
                      parent_inset, parent_scrollable, path):
        style = effective_style(w, styles_by_name, default_styles)
        x = w.get("left", 0) + parent_inset
        y = w.get("top", 0) + parent_inset
        ww = w.get("width", 0)
        hh = w.get("height", 0)
        wtype = w.get("type", "")
        ident = w.get("identifier", "")

        abs_x = parent_abs_x + x
        abs_y = parent_abs_y + y

        # Overflow check against parent's CONTENT rect — skipped if the parent
        # is SCROLLABLE (children overflowing the viewport is intentional in
        # a scroll container; the user pans to reveal them).
        right = x + ww
        bottom = y + hh
        if not parent_scrollable and (
                right > parent_content_w + parent_inset or
                bottom > parent_content_h + parent_inset):
            overflow_msgs.append(
                f"  OVERFLOW: {path}/{ident or wtype} ({right}x{bottom}) "
                f"> parent content ({parent_content_w}x{parent_content_h})")

        bg = resolve_color(style.get("bg_color"), color_lookup, "#FFFFFF")
        bg_opa = int(style.get("bg_opa", 255))
        border_w = int(style.get("border_width", 0))
        border_c = resolve_color(style.get("border_color"), color_lookup, "#888888")
        radius = int(style.get("radius", 0))

        if bg_opa > 0:
            try:
                r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                draw.rounded_rectangle([abs_x, abs_y, abs_x + ww, abs_y + hh],
                                       radius=radius,
                                       fill=(r, g, b, bg_opa))
            except Exception:
                pass
        if border_w > 0:
            try:
                r, g, b = int(border_c[1:3], 16), int(border_c[3:5], 16), int(border_c[5:7], 16)
                draw.rounded_rectangle([abs_x, abs_y, abs_x + ww, abs_y + hh],
                                       radius=radius,
                                       outline=(r, g, b, 255),
                                       width=border_w)
            except Exception:
                pass

        # Runtime-overridden widgets: detect whether the style pins
        # align + min/max to match the authored size. If yes, the canvas
        # and runtime will honor (x, y, w, h) — render without warning.
        # If no, flag with a red overlay so the agent fixes the style.
        if wtype in RUNTIME_OVERRIDDEN:
            has_align = style.get("align") in ("TOP_LEFT", "TOP_MID", "TOP_RIGHT",
                                                "LEFT_MID", "CENTER", "RIGHT_MID",
                                                "BOTTOM_LEFT", "BOTTOM_MID", "BOTTOM_RIGHT")
            min_w = style.get("min_width")
            max_w = style.get("max_width")
            min_h = style.get("min_height")
            max_h = style.get("max_height")
            size_pinned = (min_w == ww and max_w == ww and
                           min_h == hh and max_h == hh)
            if has_align and size_pinned:
                # Properly pinned via style — canvas/runtime will honor coords.
                draw.rectangle([abs_x, abs_y, abs_x + ww, abs_y + hh],
                               outline=(40, 140, 40, 200), width=1)
                tag_font = font_cache.get("MONTSERRAT_12")
                draw.text((abs_x + 4, abs_y + 4),
                          f"pinned ({wtype})", fill=(40, 140, 40, 255),
                          font=tag_font)
            else:
                draw.rectangle([abs_x, abs_y, abs_x + ww, abs_y + hh],
                               outline=(220, 30, 30, 200), width=2)
                missing = []
                if not has_align: missing.append("align")
                if min_w != ww:   missing.append(f"min_width={ww}")
                if max_w != ww:   missing.append(f"max_width={ww}")
                if min_h != hh:   missing.append(f"min_height={hh}")
                if max_h != hh:   missing.append(f"max_height={hh}")
                warn = f"NOT PINNED ({wtype}) — add to localStyles: {', '.join(missing)}"
                tag_font = font_cache.get("MONTSERRAT_12")
                draw.text((abs_x + 4, abs_y + 4), warn,
                          fill=(220, 30, 30, 255), font=tag_font)
                runtime_overrides.append(
                    f"  {path}/{ident}: {wtype} at ({x},{y},{ww},{hh}) — "
                    f"missing style pin: {', '.join(missing)}")

        # Text content
        if wtype == "LVGLLabelWidget":
            text = w.get("text", "")
            text_color = resolve_color(style.get("text_color"), color_lookup, "#000000")
            font_name = style.get("text_font", "MONTSERRAT_14")
            pil_font = font_cache.get(font_name)
            try:
                tc = (int(text_color[1:3], 16), int(text_color[3:5], 16),
                      int(text_color[5:7], 16), 255)
            except Exception:
                tc = (0, 0, 0, 255)
            text_align = style.get("text_align", "LEFT")
            pad = int(style.get("pad_left", 0))
            tx = abs_x + pad
            ty = abs_y
            try:
                text_w = int(pil_font.getlength(text))
            except Exception:
                text_w = 0
            if text_align == "CENTER":
                tx = abs_x + max(0, (ww - text_w) // 2)
            elif text_align == "RIGHT":
                tx = abs_x + ww - text_w - pad
            draw.text((tx, ty), text, fill=tc, font=pil_font)
            if text_w > ww - 4:
                overflow_msgs.append(
                    f"  TEXT_CLIP: {path}/{ident}: '{text}' "
                    f"text_w={text_w} > widget_w={ww}-4")

        # Recurse into children
        pad_all = int(style.get("pad_all", 0))
        pt = int(style.get("pad_top",    pad_all))
        pb = int(style.get("pad_bottom", pad_all))
        pl = int(style.get("pad_left",   pad_all))
        pr = int(style.get("pad_right",  pad_all))
        inset = max(pt, pb, pl, pr) + border_w
        content_w = ww - 2 * inset
        content_h = hh - 2 * inset
        my_scrollable = "SCROLLABLE" in (w.get("widgetFlags") or "")
        for c in w.get("children", []) or []:
            render_widget(c, abs_x, abs_y, content_w, content_h, inset,
                          my_scrollable,
                          path + "/" + (ident or wtype))

    render_widget(root, 0, 0, W, H, 0, False, page["name"])

    # Watermark with checks
    img.save(out_path)
    return overflow_msgs, runtime_overrides

# ---- Driver ---------------------------------------------------------------
def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2

    project_path = Path(argv[1]).resolve()
    if not project_path.exists():
        print(f"Project not found: {project_path}")
        return 1
    project_dir = project_path.parent

    with open(project_path) as f:
        project = json.load(f)

    pages = project.get("userPages", [])
    requested = set(argv[2:])
    if requested:
        pages = [p for p in pages if p["name"] in requested]
        missing = requested - {p["name"] for p in pages}
        if missing:
            print(f"WARNING: pages not found: {sorted(missing)}")

    out_dir = project_dir / "tmp" / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    font_cache = FontCache(project_dir, project.get("fonts", []))
    color_lookup = build_color_lookup(project)

    all_overflows = []
    all_runtime = []
    for page in pages:
        out = out_dir / f"{page['name']}.png"
        print(f"Rendering {page['name']} -> {out}")
        over, runtime = render_page(page, project, font_cache, color_lookup, out)
        all_overflows.extend(over)
        all_runtime.extend(runtime)

    print()
    print(f"Rendered {len(pages)} page(s) into {out_dir}")
    if all_overflows:
        print(f"\n{len(all_overflows)} OVERFLOW / TEXT_CLIP issue(s):")
        for m in all_overflows:
            print(m)
    else:
        print("No overflow issues detected.")
    if all_runtime:
        print(f"\n{len(all_runtime)} RUNTIME-OVERRIDDEN widget(s) — verify C pin:")
        for m in all_runtime:
            print(m)
    print()
    print("Next: Read each PNG with the Read tool. Confirm visually that")
    print("  * No widgets overlap (red-bordered runtime ones are expected to)")
    print("  * No text is clipped")
    print("  * Keyboards show 4 visible rows in their authored y-range")
    print("  * The page matches the worksheet from Gate 1")
    return 0 if not all_overflows else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
