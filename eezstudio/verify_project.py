#!/usr/bin/env python3
"""
Project-wide reference verifier for EEZ Studio .eez-project files.

Usage:
    python3 verify_project.py path/to/Project.eez-project

Reports every dangling or incomplete named reference. Exit code 0 if clean,
1 if any issue is found.

What it catches:

  * Widgets that useStyle a style that doesn't exist.
  * Styles that exist but have no definition (or no MAIN.DEFAULT block).
  * Styles whose MAIN.DEFAULT references a color name not in the project's
    colors[] array.
  * Styles whose MAIN.DEFAULT references a font name not in fonts[] (and not
    a built-in MONTSERRAT_<size>).
  * localStyles on individual widgets with the same color/font reference
    problems.
  * Themes whose color count doesn't match colors[] (would break per-theme
    resolution).
  * Themes where any hex value is malformed (must be #RRGGBB or #RRGGBBAA).
  * Event handlers referencing actions not declared in actions[].
  * LVGLUserWidgetWidget instances referencing a userWidgetPageName that
    isn't a userWidget.
  * Bitmaps referenced by LVGLImageWidget that aren't in bitmaps[].
  * Built-in LVGL fonts referenced as text_font (MONTSERRAT_<n>) where <n>
    isn't a sane size (8..48).

Why it matters: an agent recommending `useStyle: X` in a spec is making a
claim about how the canvas will render. If X has no definition, the
canvas falls back to LVGL defaults (often a blue rounded button or similar
unstyled look) — which is NEVER what the spec intended and is NEVER in the
user's named palette. This verifier catches the problem before the spec
goes out.

Run this verifier:
  * Before recommending `useStyle: <name>` in a spec (Gate 4).
  * Before declaring any GUI work complete.
  * Whenever the user reports a visual surprise on the canvas.

The script is read-only — it never modifies the .eez-project.
"""

import json
import re
import sys
from pathlib import Path

VALID_MONTSERRAT_SIZES = {8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32,
                          34, 36, 38, 40, 42, 44, 46, 48}

# Style property names that take a color reference. These must be a name from
# colors[]; hex is forbidden by the skill's "no hex in styles" rule.
COLOR_PROPS = {
    "bg_color", "bg_grad_color",
    "text_color",
    "border_color",
    "shadow_color",
    "arc_color",
    "line_color",
    "outline_color",
    "img_recolor",
}

# Style property names that take a font reference.
FONT_PROPS = {"text_font"}


def all_widgets(project):
    """Yield every widget node across userPages and userWidgets."""
    def walk(n):
        if isinstance(n, dict):
            if n.get("type"):
                yield n
            for v in n.values():
                yield from walk(v)
        elif isinstance(n, list):
            for x in n:
                yield from walk(x)
    for p in project.get("userPages", []):
        yield from walk(p["components"][0])
    for p in project.get("userWidgets", []):
        yield from walk(p["components"][0])


def style_main_default(style_obj):
    """Return the MAIN.DEFAULT dict of a style definition, or {} if absent."""
    if not style_obj:
        return {}
    defn = style_obj.get("definition", {})
    inner = defn.get("definition", defn)
    if not isinstance(inner, dict):
        return {}
    main = inner.get("MAIN", {})
    return main.get("DEFAULT", {}) if isinstance(main, dict) else {}


def is_hex(s):
    return isinstance(s, str) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", s))


def check_style_props(style_defn, color_names, font_names, location, issues):
    """Walk MAIN/CHECKED/etc parts of a style and flag bad color/font refs."""
    if not isinstance(style_defn, dict):
        return
    for part, states in style_defn.items():
        if not isinstance(states, dict):
            continue
        for state, props in states.items():
            if not isinstance(props, dict):
                continue
            for k, v in props.items():
                if k in COLOR_PROPS:
                    if is_hex(v):
                        issues.append(
                            f"{location} [{part}.{state}] HEX color in style: "
                            f"{k}={v!r} — forbidden, must use a token from colors[]")
                    elif isinstance(v, str) and v and v not in color_names:
                        issues.append(
                            f"{location} [{part}.{state}] UNKNOWN color reference: "
                            f"{k}={v!r} — not in colors[]")
                elif k in FONT_PROPS:
                    if not isinstance(v, str) or not v:
                        continue
                    m = re.fullmatch(r"MONTSERRAT_(\d+)", v)
                    if m:
                        if int(m.group(1)) not in VALID_MONTSERRAT_SIZES:
                            issues.append(
                                f"{location} [{part}.{state}] INVALID built-in font size: "
                                f"{k}={v!r} (valid: MONTSERRAT_8..48 in fixed steps)")
                    elif v not in font_names:
                        issues.append(
                            f"{location} [{part}.{state}] UNKNOWN font reference: "
                            f"{k}={v!r} — not in fonts[] and not a built-in MONTSERRAT_<n>")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[1]).resolve()
    if not path.exists():
        print(f"Project not found: {path}")
        return 1
    with open(path) as f:
        project = json.load(f)

    color_names = {c["name"] for c in project.get("colors", []) if "name" in c}
    font_names = {f["name"] for f in project.get("fonts", []) if "name" in f}
    action_names = {a["name"] for a in project.get("actions", []) if "name" in a}
    user_widget_names = {w["name"] for w in project.get("userWidgets", []) if "name" in w}
    bitmap_names = {b["name"] for b in project.get("bitmaps", []) if "name" in b}
    styles = project.get("lvglStyles", {}).get("styles", [])
    style_by_name = {s["name"]: s for s in styles if "name" in s}
    style_names = set(style_by_name.keys()) | {"default"}

    issues = []

    # --- Themes must have the same color count as colors[] ----------------
    n_colors = len(color_names)
    for theme in project.get("themes", []):
        tname = theme.get("name", "<unnamed>")
        theme_colors = theme.get("colors", [])
        if len(theme_colors) != n_colors:
            issues.append(
                f"theme {tname!r}: has {len(theme_colors)} color entries "
                f"but colors[] defines {n_colors} tokens (mismatched arrays "
                f"— token resolution will be off-by-one)")
        for i, hexv in enumerate(theme_colors):
            if not is_hex(hexv):
                issues.append(
                    f"theme {tname!r} entry {i}: malformed hex {hexv!r} "
                    f"(expected #RRGGBB or #RRGGBBAA)")

    # --- Named project styles: must have a definition + valid refs --------
    # Valid LVGL style part names — the keys we expect inside `definition.definition`.
    STYLE_PARTS = {"MAIN", "INDICATOR", "KNOB", "ITEMS", "SCROLLBAR",
                   "SELECTED", "CURSOR", "TICKS", "PAGE", "HEADER",
                   "HEADER_DATE"}
    for s in styles:
        sname = s.get("name", "<unnamed>")
        defn = s.get("definition")
        if not defn or not isinstance(defn, dict):
            issues.append(f"style {sname!r}: NO DEFINITION (renders as LVGL default — "
                          f"e.g. blue rounded button if applied to a button)")
            continue
        inner = defn.get("definition")
        if not isinstance(inner, dict) or not inner:
            issues.append(f"style {sname!r}: EMPTY DEFINITION (only objID, no MAIN/INDICATOR/etc. — "
                          f"falls through to LVGL widget defaults like blue rounded buttons)")
            continue
        # Reject styles whose inner has no recognized style-part keys at all
        # (e.g. someone wrote keys directly without a MAIN wrapper).
        if not any(k in STYLE_PARTS for k in inner.keys()):
            issues.append(f"style {sname!r}: definition has no recognized style parts "
                          f"({sorted(inner.keys())}; expected one of {sorted(STYLE_PARTS)})")
            continue
        check_style_props(inner, color_names, font_names,
                          f"style {sname!r}", issues)

    # --- Every widget's useStyle + localStyles + bitmap + action refs -----
    bitmaps_referenced = set()
    for w in all_widgets(project):
        ident = w.get("identifier") or "<anon>"
        wtype = w.get("type", "")
        loc = f"widget {wtype}/{ident}"

        # useStyle
        use = w.get("useStyle")
        if use and use not in style_names:
            issues.append(f"{loc}: useStyle {use!r} — not in lvglStyles.styles[]")
        # Inner style.useStyle (the rare case)
        inner_use = (w.get("style") or {}).get("useStyle")
        if inner_use and inner_use != "default" and inner_use not in style_names:
            issues.append(f"{loc}: style.useStyle {inner_use!r} — not in lvglStyles.styles[]")

        # localStyles
        local = (w.get("localStyles") or {}).get("definition")
        if isinstance(local, dict):
            check_style_props(local, color_names, font_names, loc, issues)

        # Event handlers → actions
        for e in w.get("eventHandlers", []) or []:
            a = e.get("action")
            if a and a not in action_names:
                issues.append(f"{loc}: eventHandler action {a!r} — not declared in actions[]")

        # User widget instance → userWidget
        if wtype == "LVGLUserWidgetWidget":
            uname = w.get("userWidgetPageName")
            if uname and uname not in user_widget_names:
                issues.append(f"{loc}: userWidgetPageName {uname!r} — not in userWidgets[]")

        # Image widget → bitmap
        if wtype == "LVGLImageWidget":
            img = w.get("image")
            if img:
                bitmaps_referenced.add(img)
                if img not in bitmap_names:
                    issues.append(f"{loc}: image {img!r} — not in bitmaps[]")

    # --- Report -----------------------------------------------------------
    if not issues:
        print(f"OK: {path.name} — no dangling or incomplete references found")
        print(f"  colors: {len(color_names)}  fonts: {len(font_names)}  "
              f"styles: {len(style_by_name)}  actions: {len(action_names)}  "
              f"userWidgets: {len(user_widget_names)}  bitmaps: {len(bitmap_names)}")
        return 0

    # Group issues by severity-ish: missing definitions first, then unknowns.
    print(f"FOUND {len(issues)} issue(s) in {path.name}:\n")
    for i in issues:
        print(f"  - {i}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
