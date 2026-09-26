#!/usr/bin/env python3
"""
Pre-flight gate that catches the single most common skill violation:
C code that mutates the visual geometry of an EEZ Studio-exported widget,
making EEZ Studio's canvas a LIE about what the device will render.

This is the patten that's bitten the user multiple times across this skill's
lifetime — the agent moves a widget in the .eez-project, forgets to update
a C-side `lv_obj_set_pos(objects.X, ...)` call, the canvas shows the new
position, the device shows the stale C position, and the user discovers
the divergence only after flashing.

Run this BEFORE declaring any C work done. Exit 0 if clean. Exit 1 + a
report on every match if not. Treat any match the same way you'd treat
`rm -rf /` slipping into a script: STOP and reconsider before continuing.

Usage:
    python3 verify_no_canvas_divergence.py <project_root>

The project root should be the directory containing `main/` (or wherever
the EEZ Studio C export lives — `main/ui/screens.c` etc.). The script
scans every .c and .cpp file under main/ that is NOT inside main/ui/
(the auto-generated export is by-definition allowed to mutate geometry
because it's writing the initial state from the .eez-project).
"""

import os
import re
import sys
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────
# Forbidden patterns — C calls that change a widget's visible geometry.
# Every one of these makes EEZ Studio's canvas diverge from the device
# when applied to an `objects.<widget>` symbol. None of them belongs in
# hand-written C; all of these effects MUST come from the .eez-project.
# ────────────────────────────────────────────────────────────────────────
FORBIDDEN_GEOMETRY_FNS = [
    # Position
    "lv_obj_set_pos", "lv_obj_set_x", "lv_obj_set_y",
    "lv_obj_align", "lv_obj_align_to", "lv_obj_set_align",
    "lv_obj_center",
    # Size
    "lv_obj_set_size", "lv_obj_set_width", "lv_obj_set_height",
    "lv_obj_set_content_width", "lv_obj_set_content_height",
    # Z-order (changes which widget covers which on canvas vs device)
    "lv_obj_move_foreground", "lv_obj_move_background",
    "lv_obj_move_to_index", "lv_obj_swap",
    # Style geometry overrides — same effect, written via style API
    "lv_obj_set_style_align",
    "lv_obj_set_style_min_width", "lv_obj_set_style_max_width",
    "lv_obj_set_style_min_height", "lv_obj_set_style_max_height",
    "lv_obj_set_style_width", "lv_obj_set_style_height",
    "lv_obj_set_style_x", "lv_obj_set_style_y",
    "lv_obj_set_style_translate_x", "lv_obj_set_style_translate_y",
    "lv_obj_set_style_transform_angle", "lv_obj_set_style_transform_zoom",
]

# Explicitly-allowed C calls that touch `objects.<widget>` — these change
# invisible runtime state or content, not geometry. Listed so the rule has
# a positive counterexample, not just a forbidden list.
ALLOWED_INVISIBLE_FNS = {
    # Content
    "lv_label_set_text", "lv_label_set_text_fmt", "lv_label_set_long_mode",
    "lv_textarea_set_text", "lv_textarea_set_placeholder_text",
    "lv_textarea_set_password_mode", "lv_textarea_set_one_line",
    "lv_textarea_get_text",
    "lv_img_set_src", "lv_image_set_src",
    "lv_keyboard_set_textarea", "lv_keyboard_set_mode",
    "lv_dropdown_set_options", "lv_dropdown_set_selected",
    "lv_roller_set_options", "lv_roller_set_selected",
    "lv_slider_set_value", "lv_bar_set_value", "lv_arc_set_value",
    "lv_switch_*",
    "lv_obj_set_user_data",
    # State (LV_STATE_*: CHECKED, DISABLED, FOCUSED, …)
    "lv_obj_add_state", "lv_obj_clear_state", "lv_obj_has_state",
    # Flags that don't affect visible geometry
    "lv_obj_add_flag", "lv_obj_clear_flag", "lv_obj_has_flag",
    # Events
    "lv_obj_add_event_cb", "lv_obj_remove_event_cb",
    # Hit area only (invisible — does not affect canvas rendering)
    "lv_obj_set_ext_click_area",
    # Scroll programmatically (transient)
    "lv_obj_scroll_to", "lv_obj_scroll_to_x", "lv_obj_scroll_to_y",
    "lv_obj_scroll_by", "lv_obj_scroll_to_view",
    # Screen load
    "lv_scr_load", "lv_disp_load_scr", "lv_screen_load",
}


def is_comment_or_string(line, pos):
    """Quick heuristic: skip matches inside // comments or "..." strings."""
    pre = line[:pos]
    # Inline // comment
    if "//" in pre:
        idx = pre.index("//")
        before = pre[:idx]
        if before.count('"') % 2 == 0:
            return True
    # Inside an even-quoted string
    if pre.count('"') % 2 == 1:
        return True
    return False


def scan(project_root: Path):
    main_dir = project_root / "main"
    if not main_dir.is_dir():
        print(f"ERROR: {main_dir} not found — pass the project root that contains main/")
        return 2

    targets = []
    for path in main_dir.rglob("*.c"):
        # Skip the EEZ Studio export — it's allowed to write geometry
        # because it's reconstructing the .eez-project intent.
        rel = path.relative_to(main_dir)
        if rel.parts[0] == "ui":
            continue
        targets.append(path)
    for path in main_dir.rglob("*.cpp"):
        rel = path.relative_to(main_dir)
        if rel.parts[0] == "ui":
            continue
        targets.append(path)

    if not targets:
        print(f"No C/C++ files found under {main_dir} (excluding main/ui/).")
        return 0

    # Build a single regex that matches any forbidden fn name immediately
    # followed by `(`, with `objects.` somewhere in the SAME logical call.
    fn_pattern = re.compile(
        r"\b(?P<fn>" + "|".join(re.escape(f) for f in FORBIDDEN_GEOMETRY_FNS) + r")\s*\(",
    )

    issues = []  # (path, line_no, line_text, fn_name)

    for path in targets:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"WARN: could not read {path}: {e}")
            continue

        lines = text.splitlines()
        # Multi-line calls are common — assemble a "logical line" that
        # extends past `)` so `objects.X` arguments on the next line are
        # caught.
        i = 0
        while i < len(lines):
            line = lines[i]
            for m in fn_pattern.finditer(line):
                if is_comment_or_string(line, m.start()):
                    continue
                # Look ahead up to 6 lines for the matching `)` and
                # check whether `objects.` appears anywhere in between.
                buf = line[m.start():]
                open_count = buf.count("(") - buf.count(")")
                j = i + 1
                while open_count > 0 and j < len(lines) and j - i < 6:
                    buf += " " + lines[j]
                    open_count += lines[j].count("(") - lines[j].count(")")
                    j += 1
                if "objects." in buf:
                    issues.append((path, i + 1, line.rstrip(), m.group("fn")))
            i += 1

    if not issues:
        print(f"OK: scanned {len(targets)} file(s) under {main_dir}, no canvas-device divergence found.")
        return 0

    rel_root = str(project_root)
    print(f"\n!!! CANVAS-DEVICE DIVERGENCE — {len(issues)} forbidden call(s) found !!!\n")
    print("Every entry below mutates a widget's VISIBLE geometry from C. That makes")
    print("EEZ Studio's canvas a LIE — the user sees one layout in the design")
    print("tool and a different one on the device. Resolve each one by:")
    print("  (a) deleting the C call and pinning the same geometry in the")
    print("      widget's localStyles in the .eez-project (align / min_width /")
    print("      max_width / min_height / max_height — see skill Trap 13), or")
    print("  (b) removing the C call entirely if the .eez-project already")
    print("      authors the correct geometry.")
    print()
    for path, ln, text, fn in issues:
        rel = os.path.relpath(path, rel_root)
        print(f"  {rel}:{ln}: {fn}(... objects.X ...)")
        print(f"      {text.strip()[:140]}")
    print()
    print("Hint: legit C calls on objects.<widget> that change INVISIBLE state")
    print("(content, runtime state, events, hit area) are fine — see the")
    print("ALLOWED_INVISIBLE_FNS list at the top of this script for examples.")
    return 1


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    return scan(Path(argv[1]).resolve())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
