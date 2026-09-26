# EEZ Studio `.eez-project` Schema Reference (LVGL projects)

Canonical schema reference for `.eez-project` files in `projectType: "LVGL"` mode, derived directly from the EEZ Studio source at `github.com/eez-open/studio` (clone it locally if you want to grep it). Cite source paths and line numbers when validating a claim — guesswork is what this document exists to stop.

**Scope:** LVGL projects only. The skill agent only authors LVGL `.eez-project` files; the EEZ-GUI / Dashboard / EEZ-GUI-Lite branches of the schema are out of scope here. Where a property is shared across project types but disabled-in-LVGL, that's called out.

---

## Table of contents

1. [Top-level project shape](#1-top-level-project-shape)
2. [Settings (`settings.general` and `settings.build`)](#2-settings)
3. [Page schema (`userPages[]` and `userWidgets[]`)](#3-page-schema-userpages-and-userwidgets)
4. [Per-widget reference](#4-per-widget-reference)
5. [Flag enumeration (`LV_OBJ_FLAG_*`)](#5-flag-enumeration)
6. [State enumeration (`LV_STATE_*`)](#6-state-enumeration)
7. [Part enumeration (`LV_PART_*`)](#7-part-enumeration)
8. [Style properties (`lvglPropertiesMap`)](#8-style-properties)
9. [Style cascade (useStyle, localStyles, defaultStyles)](#9-style-cascade)
10. [Color/theme schema (`colors[]`, `themes[]`, `themesVersion`)](#10-colortheme-schema)
11. [Font schema (`fonts[]`)](#11-font-schema)
12. [Event handler schema (`eventHandlers[]`)](#12-event-handler-schema)
13. [Action schema (`actions[]`)](#13-action-schema)
14. [Variable schema (`variables.*`)](#14-variable-schema)
15. [Bitmap schema (`bitmaps[]`)](#15-bitmap-schema)
16. [LVGL groups (`lvglGroups`)](#16-lvgl-groups)
17. [Code-generation pipeline (build placeholders)](#17-code-generation-pipeline)
18. [Validation checklist](#18-validation-checklist)

---

## 1. Top-level project shape

A `.eez-project` is a single JSON object. The root-level keys consumed by EEZ Studio (LVGL mode) are:

```json
{
  "settings": { "general": { ... }, "build": { ... } },
  "variables": { "globalVariables": [], "structures": [], "enums": [] },
  "actions": [],
  "userPages": [],
  "userWidgets": [],
  "fonts": [],
  "bitmaps": [],
  "colors": [],
  "themes": [],
  "themesVersion": 3,
  "lvglStyles": { "styles": [], "defaultStyles": {} },
  "lvglGroups": { "groups": [], "defaultGroupForEncoderInSimulator": "", "defaultGroupForKeyboardInSimulator": "" }
}
```

The authoritative list of root-level observable properties is at `https://github.com/eez-open/studio/blob/master/packages/project-editor/project/project.tsx#L1817-L1845` (the `makeObservable` block in `Project.makeEditable()`). The built-in (always-present) properties are declared at lines 1423-1447 (`builtinProjectProperties`).

| Key | Type | Required in LVGL projects | Source |
|---|---|---|---|
| `settings` | object | yes (mandatory) | project.tsx:1374-1380, 1425-1429 |
| `colors` | array of `Color` | yes (mandatory) | project.tsx:1431-1435 |
| `themes` | array of `Theme` | yes (mandatory) | project.tsx:1437-1441 |
| `themesVersion` | number | yes; defaulted to `1` in beforeLoadHook if missing | project.tsx:1443-1446, 1456-1460 |
| `variables` | object `{ globalVariables, structures, enums }` | yes (feature-mandatory) | variable.tsx:1683-1700, 1760 |
| `actions` | array of `Action` | yes (feature-mandatory) | action.tsx:411 (mandatory feature) |
| `userPages` | array of `Page` | yes; migration splits old `pages[]` into `userPages`/`userWidgets` | project.tsx:1557-1572 |
| `userWidgets` | array of `Page` (with `isUsedAsUserWidget: true`) | yes (may be empty) | project.tsx:1566-1569 |
| `fonts` | array of `Font` | yes (feature-mandatory) | font.tsx (mandatory feature) |
| `bitmaps` | array of `Bitmap` | yes (feature-mandatory) | bitmap.tsx:858 |
| `lvglStyles` | object `{ styles, defaultStyles }` | yes (feature-mandatory in LVGL projects) | style.tsx:884-892 (`mandatory: true`) |
| `lvglGroups` | object `{ groups, defaultGroupForEncoderInSimulator, defaultGroupForKeyboardInSimulator }` | yes; coerced to empty in `beforeLoadHook` if missing | project.tsx:1465-1471; groups.tsx:480 |
| `objID` | string (UUID) on every EezObject | **No — `objID` is in-memory only; do not author or hand-edit.** EEZ Studio assigns objIDs on load via `_objectsMap` (project.tsx:1847-1857). | — |

Properties that are valid for **non-LVGL** projects but are absent / forbidden in LVGL mode (migration deletes them — see project.tsx:1462-1463): `styles`, `texts`. Other non-LVGL keys (`scpi`, `instrumentCommands`, `shortcuts`, `micropython`, `extensionDefinitions`, `changes`, `readme`) are optional features that EEZ Studio will not strip but the LVGL agent should not author.

**`objID` handling.** Every `EezObject` in the project has an `objID` string that EEZ Studio assigns during load. Tools that hand-edit `.eez-project` should preserve existing `objID` values on existing widgets and let EEZ Studio mint new ones for added widgets (omit `objID` and EEZ Studio will fill it in). Hand-authored `objID`s **must** be unique across the entire project file; collisions will produce silent reference breakage in flow-supported projects.

---

## 2. Settings

### 2.1 `settings.general`

Declared in `project.tsx` around lines 820-1100 (the `class GeneralSettings` properties array). The keys relevant to LVGL projects:

| Key | Type | Notes | Source |
|---|---|---|---|
| `projectType` | enum string | **For LVGL projects, must be `"LVGL"`.** Other valid values: `"firmware"`, `"firmware-module"`, `"resource"`, `"applet"`, `"dashboard"`, `"lvgl"`, `"iext"`. (Lowercase `"lvgl"`/uppercase `"LVGL"` both work in source, but EEZ Studio writes `"LVGL"`.) | project.tsx:823 |
| `projectVersion` | enum string | `"v1"`, `"v2"`, `"v3"`. For LVGL projects you'll see `"v3"`. | project.tsx:863 |
| `lvglVersion` | enum string | `"8.3"`, `"9.0"`, `"9.1"`, etc. — the LVGL runtime ABI version. Determines which `LVGL_EVENTS_*` table is used, which `LVGL_FLAG_CODES_*` table is used, and which `LV_STYLE_*` codes are emitted. Also controls per-widget version branches (e.g. `Slider.tsx:170-184` and `Checkbox.tsx:64-83` switch `defaultFlags` based on this). | project.tsx:900 |
| `flowSupport` | boolean | `true` enables EEZ-Flow runtime; `false` is "no flows" mode (recommended for this codebase). When `false`, actions become bare `extern void action_<name>(lv_event_t *)` declarations and event handlers can only target `handlerType: "action"`. | project.tsx:1031 |
| `displayWidth` | number | Pixel width of the target panel. | project.tsx:974 |
| `displayHeight` | number | Pixel height of the target panel. | project.tsx:981 |
| `circularDisplay` | boolean | Round display flag. | project.tsx:988 |
| `displayBorderRadius` | number | Corner-radius for rounded screens. | project.tsx:994 |
| `darkTheme` | string (theme name) | Which theme name in `themes[]` is treated as the dark theme. | project.tsx:1000 |
| `colorBpp` / `bitmapColorFormat` | enums | Render bit depth and bitmap conversion format. | project.tsx:1006, 1019 |
| `embedBitmaps` | boolean | If true, bitmaps are emitted as C arrays inline; if false, they are stored as external binary files. | project.tsx:1071 |
| `embedFonts` | boolean | Same for fonts. | project.tsx:1077 |
| `cacheFonts` | boolean | LVGL font caching toggle. | project.tsx:1086 |
| `defaultStyleForUserWidgetInEditor` | string | Style name used to preview user widgets in the editor. | project.tsx:1095 |
| `masterProject` | string (path) | Optional; for project composition. | project.tsx:927 |
| `imports` | array | Imported sub-projects. | project.tsx:954 |
| `hiddenWidgetLines` | enum | Editor cosmetic. | project.tsx:1043 |
| `dimmedLinesOpacity` | number | Editor cosmetic. | project.tsx:1059 |
| `css` | string | Optional. CSS attached to the project. | project.tsx:969 |

Non-LVGL keys present in the same class but not relevant: `commandsProtocol`, `commandsDocFolder` (SCPI), `extensions`.

### 2.2 `settings.build`

Source: `project.tsx:290-410` (the `class Build` properties array). Keys:

| Key | Type | Source |
|---|---|---|
| `configurations` | array (string-named build configs) | project.tsx:293 |
| `files` | array of `BuildFile` (see below) | project.tsx:301 |
| `destinationFolder` | string (output directory, e.g. `"main/ui"`) | project.tsx:309 |
| `separateFolderForImagesAndFonts` | boolean | project.tsx:313 |
| `imageExportMode` | enum | project.tsx:320 |
| `fontExportMode` | enum | project.tsx:336 |
| `fileSystemPath` | string | project.tsx:352 |
| `lvglInclude` | string | Header to include at the top of generated `screens.c` (default `"lvgl.h"`); becomes `#include <…>` in generated output. | project.tsx:360; assets.ts:1775 |
| `screensLifetimeSupport` | boolean | Enables per-screen lifetime (`createAtStart`, `deleteOnScreenUnload`). | project.tsx:366 |
| `useDockerDesktop` | boolean | Build via Docker. | project.tsx:372 |
| `generateSourceCodeForEezFramework` | boolean | flow-only | project.tsx:379 |
| `compressFlowDefinition` | boolean | flow-only | project.tsx:389 |
| `executionQueueSize` | number | flow-only | project.tsx:398 |
| `expressionEvaluatorStackSize` | number | flow-only | project.tsx:406 |

Each entry in `settings.build.files[]` is a `BuildFile`:

| Key | Type | Source |
|---|---|---|
| `fileName` | string — output filename. May contain `<configuration>` placeholder; if present, the file is generated once per configuration. | project.tsx:199; build/build.ts:377-407 |
| `description` | string | project.tsx:204 |
| `template` | string — file contents with `${eez-studio <PLACEHOLDER>}` markers interpolated at build time. The available `<PLACEHOLDER>` values are listed in [Section 17](#17-code-generation-pipeline). Regex used: `/\/\/\$\{eez-studio (\w*)\s*(\w*)\}/g` (build/build.ts:246). | project.tsx:208 |

---

## 3. Page schema (`userPages[]` and `userWidgets[]`)

Both arrays contain `Page` objects. The distinction is the `isUsedAsUserWidget` flag (and the historical `isUsedAsCustomWidget`); migration splits the legacy single `pages[]` array into these two arrays based on that flag (project.tsx:1557-1572).

### 3.1 Page fields

Declared at `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/page/page.tsx#L346-L512`.

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Becomes the screen identifier in `screens.c` (PascalCase → `lowercase_with_underscores`). Globally unique across `userPages` + `userWidgets`. |
| `description` | string | optional | |
| `left`, `top`, `width`, `height` | number | required | LVGL projects: these are auto-filled from `displayWidth`/`displayHeight` for full-screen pages; for user widgets, they control the editor canvas size. |
| `isUsedAsUserWidget` | boolean | yes when used as a widget instance container | When `true`, the page is callable as a `LVGLUserWidgetWidget`. |
| `createAtStart` | boolean | optional, defaults to `true` | Only meaningful when `settings.build.screensLifetimeSupport` is true. |
| `deleteOnScreenUnload` | boolean | optional, defaults to `false` | Flow-support only. |
| `closePageIfTouchedOutside` | boolean | LVGL: disabled (forbidden) | |
| `usedIn`, `style`, `scaleToFit`, `dataContextOverrides`, `portrait` | various | LVGL: all disabled/forbidden | |
| `id` | number | LVGL: disabled (forbidden) | |
| `components` | array of components (widgets, flow components) | yes | Children — for LVGL, the first/only widget is an `LVGLScreenWidget`. |

### 3.2 The page-root `LVGLScreenWidget`

The single widget at the root of every page's `components[]` array is an `LVGLScreenWidget` (`type: "LVGLScreenWidget"`). Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/widgets/Screen.tsx`.

```json
{
  "type": "LVGLScreenWidget",
  "left": 0, "top": 0,
  "width": <displayWidth>, "height": <displayHeight>,
  "leftUnit": "px", "topUnit": "px", "widthUnit": "px", "heightUnit": "px",
  "clickableFlag": true,
  "clickableFlagType": "literal",
  "hiddenFlag": false,
  "hiddenFlagType": "literal",
  "checkedState": false,
  "checkedStateType": "literal",
  "disabledState": false,
  "disabledStateType": "literal",
  "widgetFlags": "",
  "states": "",
  "flagScrollbarMode": "",
  "flagScrollDirection": "",
  "scrollSnapX": "",
  "scrollSnapY": "",
  "useStyle": "",
  "localStyles": { "definition": {} },
  "group": "",
  "groupIndex": 0,
  "eventHandlers": [],
  "children": [...]
}
```

`defaultFlags` for `LVGLScreenWidget` (Screen.tsx:46-47):
```
CLICKABLE|PRESS_LOCK|CLICK_FOCUSABLE|GESTURE_BUBBLE|SNAPPABLE|SCROLLABLE|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER
```

**Required keys (the JSON must contain these or EEZ Studio silently drops the page from the canvas):** all of `left/top/width/height`, all four `…Unit` keys, all four reactive-flag/state pairs (`hiddenFlag` + `hiddenFlagType`, `clickableFlag` + `clickableFlagType`, `checkedState` + `checkedStateType`, `disabledState` + `disabledStateType`), `widgetFlags`, `states`, `useStyle`, `localStyles`, `children`, `eventHandlers`. The `beforeLoadHook` at Base.tsx:1063-1200 will *initialize* missing `…Unit`, missing `widgetFlags`, missing reactive-flag `…Type` keys, and `states` — but `localStyles` and `children` must be present.

**FORBIDDEN on `LVGLScreenWidget` (overrides authored Page geometry):** `identifier` (the page's `name` is the identifier — see Base.tsx:636). The screen widget is `isSelectable: false` and `isMoveable: false` (Screen.tsx:55-56). The `setRect`/`left`/`top`/`width`/`height` properties are wired to read from the parent Page, not to be authored on the screen widget itself (Base.tsx:651, 671, 691, 712).

### 3.3 Child widgets on a page

Each entry in `components[].children[]` is one of the widget types listed in [Section 4](#4-per-widget-reference). All widgets share the base `LVGLWidget` schema declared at `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/widgets/Base.tsx#L559-L1061`. The common keys (Base.tsx:629-1061):

| Key | Type | Notes |
|---|---|---|
| `type` | string — the class name (e.g. `"LVGLLabelWidget"`) | |
| `identifier` | string | The Name in the Property panel. Becomes a key in the generated `objects` struct (`codeIdentifier` is the underscored lowercase rewrite, see Base.tsx:602-614). |
| `left`, `top`, `width`, `height` | number | Geometry in pixels (or percent if `…Unit` says so). |
| `leftUnit`, `topUnit` | `"px"` \| `"%"` | |
| `widthUnit`, `heightUnit` | `"px"` \| `"%"` \| `"content"` | `"content"` sizes to children (e.g. Label uses this by default). |
| `hiddenFlag` | boolean \| string-expression | The `HIDDEN` flag, lifted out for ergonomics. |
| `hiddenFlagType` | `"literal"` \| `"expression"` | Required (defaulted to `"literal"`). |
| `clickableFlag` | boolean \| string-expression | The `CLICKABLE` flag, lifted out. |
| `clickableFlagType` | `"literal"` \| `"expression"` | Required. |
| `checkedState` | boolean \| string-expression | The `CHECKED` state, lifted out. |
| `checkedStateType` | `"literal"` \| `"expression"` | Required. |
| `disabledState` | boolean \| string-expression | The `DISABLED` state, lifted out. |
| `disabledStateType` | `"literal"` \| `"expression"` | Required. |
| `widgetFlags` | string — pipe-separated `LV_OBJ_FLAG_*` names *without* the prefix (see [Section 5](#5-flag-enumeration)) | The "non-reactive" flags (everything except `HIDDEN`/`CLICKABLE`). Example: `"PRESS_LOCK\|CLICK_FOCUSABLE\|SCROLLABLE"`. Empty string = no extra flags. |
| `states` | string — pipe-separated state names (see [Section 6](#6-state-enumeration)) | Always includes non-reactive states only (`CHECKED` and `DISABLED` are lifted out into the reactive fields). Empty string = default state only. |
| `flagScrollbarMode` | `""` \| `"off"` \| `"on"` \| `"active"` \| `"auto"` | Emitted as `lv_obj_set_scrollbar_mode(...)`. |
| `flagScrollDirection` | `""` \| `"none"` \| `"top"` \| `"left"` \| `"bottom"` \| `"right"` \| `"hor"` \| `"ver"` \| `"all"` | Emitted as `lv_obj_set_scroll_dir(...)`. |
| `scrollSnapX`, `scrollSnapY` | `""` \| `"none"` \| `"start"` \| `"end"` \| `"center"` | |
| `useStyle` | string — name of an entry in `lvglStyles.styles` whose `forWidgetType` equals this widget's `type` (Base.tsx:903-912). | Empty string `""` = no project style; uses the default style if `lvglStyles.defaultStyles[type]` is set. |
| `localStyles` | `LVGLStylesDefinition` object — `{ definition: { <part>: { <state>: { <prop>: <value> } } } }` (style-definition.tsx:54-97). | Must always be present, may be `{ "definition": {} }`. |
| `group` | string — name of an entry in `lvglGroups.groups` | Empty string = no group. |
| `groupIndex` | number | Defaulted to 0 (Base.tsx:1197-1199). |
| `eventHandlers` | array of `EventHandler` (see [Section 12](#12-event-handler-schema)) | Optional but conventional empty `[]`. |
| `children` | array of child widgets (only on container-capable widgets; harmless empty array on leaf widgets) | |

**Schema invariants the load path enforces** (Base.tsx:1063-1200):
- If `widgetFlags` is missing: defaulted to `""` after migrating any legacy `flags` field.
- If any `…Unit` is missing: defaulted to `"px"`.
- If `states` is missing: defaulted to `""`.
- If `groupIndex` is missing: defaulted to `0`.
- Legacy `flags`/`states` fields are migrated into the reactive split (`hiddenFlag`/`clickableFlag` and `checkedState`/`disabledState`) and removed.

### 3.4 The `LVGLUserWidgetWidget` instance

When you place a user widget on a page, the JSON object is `type: "LVGLUserWidgetWidget"`. Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/widgets/UserWidget.tsx#L103-L227`.

**Required widget-specific keys** beyond the Base schema:

| Key | Type | Required | Notes |
|---|---|---|---|
| `userWidgetPageName` | string — name of an entry in `userWidgets[]` | **yes** | Reports a missing-property error if blank (UserWidget.tsx:191). |
| `userPropertyValues` | object — key/value map of user-property name → expression/literal value | **yes when the referenced user widget defines user properties** | See `userPropertyValuesProperty` in `flow/user-property.tsx`. |

`defaultFlags` (UserWidget.tsx:180-181):
```
CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE
```

EEZ Studio runs a cycle-detection check (`isCycleDetected`, UserWidget.tsx:255-301): a user widget that ultimately includes itself produces an error.

---

## 4. Per-widget reference

The per-widget table below covers every concrete widget class found under `https://github.com/eez-open/studio/tree/master/packages/project-editor/lvgl/widgets/`. For each widget:

- **Class** is the TypeScript class name, which is exactly the value of the JSON `type` field.
- **Source** is the file under `packages/project-editor/lvgl/widgets/` and the line of the `export class` declaration.
- **`defaultFlags`** is the flag string the LVGL constructor (`lv_<thing>_create`) sets by default — the export diff compares the widget's `widgetFlags` against this string and emits `lv_obj_clear_flag` / `lv_obj_add_flag` for the deltas. (Reactive flags `HIDDEN` and `CLICKABLE` are managed via the lifted `hiddenFlag`/`clickableFlag` fields.)
- **`parts`** is the set of `LV_PART_*` values that are valid in `localStyles.definition` and `useStyle` for this widget.
- **Widget-specific properties** beyond the Base schema, with defaults from each file's `defaultValue` block.
- **Runtime geometry override** call-outs — widgets whose constructor / `set_*` calls reset the authored `width`/`height` after creation are flagged. For those widgets you must pin the geometry via `localStyles.MAIN.DEFAULT` with all of `align: "DEFAULT"`, `min_width`, `max_width`, `min_height`, `max_height` (set equal to the desired pixel size). This is the "min_*/max_*/align pinning" the skill's SKILL.md references.

### 4.1 LVGLLabelWidget

- Class: `LVGLLabelWidget` — Label.tsx:23
- `defaultFlags`: `CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific properties:

| Key | Type | Default | Notes |
|---|---|---|---|
| `text` | string-or-expression | `"Text"` | The label content. |
| `textType` | `"literal"` \| `"translated-literal"` \| `"expression"` | `"literal"` | Required. |
| `previewValue` | string | `""` | Editor-only preview when `textType` ≠ literal. |
| `longMode` | `"WRAP"` \| `"DOT"` \| `"SCROLL"` \| `"SCROLL_CIRCULAR"` \| `"CLIP"` | `"WRAP"` | Maps to `LV_LABEL_LONG_*`. |
| `recolor` | boolean | `false` | Enable inline color codes (`#ff0000Text#`). |

- Default `width`/`height`: `80`/`32`, both with `…Unit: "content"`.

### 4.2 LVGLButtonWidget

- Class: `LVGLButtonWidget` — Button.tsx:16
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- No widget-specific properties — a button is a styled container; its text is added by a child `LVGLLabelWidget`.

### 4.3 LVGLSwitchWidget

- Class: `LVGLSwitchWidget` — Switch.tsx:13
- `defaultFlags`: `CHECKABLE|CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "INDICATOR", "KNOB"]`
- No widget-specific properties.
- Default size: `50×25`.

### 4.4 LVGLSliderWidget

- Class: `LVGLSliderWidget` — Slider.tsx:22
- `defaultFlags` (LVGL 9.x): `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SCROLL_WITH_ARROW|SNAPPABLE`
- `defaultFlags` (LVGL 8.x): `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "INDICATOR", "KNOB"]`
- Specific properties (Slider.tsx:23-34, 115-133):

| Key | Type | Default | Notes |
|---|---|---|---|
| `min`, `max` | number-or-expression | `0`, `100` | |
| `minType`, `maxType` | `"literal"` \| `"expression"` | `"literal"` | |
| `mode` | `"NORMAL"` \| `"SYMMETRICAL"` \| `"RANGE"` | `"NORMAL"` | |
| `value`, `valueType` | number-or-expression / type | `25`, `"literal"` | |
| `previewValue` | string | `25` | Editor only. |
| `valueLeft`, `valueLeftType` | number-or-expression / type | `0`, `"literal"` | Only used when `mode == "RANGE"`. |
| `previewValueLeft` | string | `0` | Editor only. |
| `enableAnimation` | boolean | `false` | |

### 4.5 LVGLArcWidget

- Class: `LVGLArcWidget` — Arc.tsx:37
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "INDICATOR", "KNOB"]`
- Specific properties include `rangeMin`, `rangeMax`, `value`, `bgStartAngle`, `bgEndAngle`, `startAngle`, `endAngle`, `mode` (`"NORMAL"` / `"SYMMETRICAL"` / `"REVERSE"`), `rotation`, `useAngle`, plus the corresponding `*Type` fields and editor-only `preview*` fields. Read Arc.tsx for the full list — it's the largest single-file widget definition outside Meter/Scale.

### 4.6 LVGLBarWidget

- Class: `LVGLBarWidget` — Bar.tsx:22
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "INDICATOR"]`
- Specific properties: `min`, `max`, `value`, `valueStart`, `mode` (`"NORMAL"` / `"SYMMETRICAL"` / `"RANGE"`), `enableAnimation`, plus `*Type` and `previewValue`/`previewValueStart`.

### 4.7 LVGLCheckboxWidget

- Class: `LVGLCheckboxWidget` — Checkbox.tsx:16
- `defaultFlags` (LVGL 9.x): `CHECKABLE|CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SCROLL_WITH_ARROW|SNAPPABLE`
- `defaultFlags` (LVGL 8.x): same minus `SCROLL_ON_FOCUS` (see Checkbox.tsx:71-80 for the version branch).
- `parts`: `["MAIN", "INDICATOR"]`
- Specific properties: `text`, `textType`. Default text `"Checkbox"`.

### 4.8 LVGLPanelWidget

- Class: `LVGLPanelWidget` — Panel.tsx:13
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "SCROLLBAR"]`
- No widget-specific properties. Generic container.

### 4.9 LVGLContainerWidget

- Class: `LVGLContainerWidget` — Container.tsx:36
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: not explicitly listed in the file's `lvgl` block (Container.tsx:115-) — defaults to `["MAIN"]` via inheritance. Verify by reading Container.tsx if you need parts beyond MAIN.
- Specific: `containerVersion` (internal migration marker).

### 4.10 LVGLImageWidget

- Class: `LVGLImageWidget` — Image.tsx:34
- `defaultFlags`: `ADV_HITTEST|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific properties:

| Key | Type | Notes |
|---|---|---|
| `image` | string — name of a bitmap in `bitmaps[]` | |
| `setPivot`, `pivotX`, `pivotY` | boolean / numbers | |
| `zoom` | number — fixed-point zoom factor (256 = 1.0×) | |
| `angle` | number — rotation in 0.1° units | |
| `innerAlign` | enum (`LV_IMAGE_ALIGN_*` values DEFAULT/TOP_LEFT/…/TILE) | LVGL 9 only — runtime override; see Image.tsx for details. |
| `sizeMode` | enum (`VIRTUAL`/`REAL`) | |
| `previewValue` | string | Editor only. |

### 4.11 LVGLImgbuttonWidget

- Class: `LVGLImgbuttonWidget` — Imgbutton.tsx:21
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific: `imageReleased`, `imagePressed`, `imageDisabled`, `imageCheckedReleased`, `imageCheckedPressed`, `imageCheckedDisabled` — all are bitmap-name references (`bitmaps[].name`).

### 4.12 LVGLKeyboardWidget

- Class: `LVGLKeyboardWidget` — Keyboard.tsx:29
- `defaultFlags`: `CLICKABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "ITEMS"]`
- Specific properties:

| Key | Type | Notes |
|---|---|---|
| `textarea` | string — `identifier` of a sibling `LVGLTextareaWidget` | |
| `mode` | `"TEXT_LOWER"` \| `"TEXT_UPPER"` \| `"SPECIAL"` \| `"NUMBER"` \| `"USER_1"`–`"USER_4"` | Default `"TEXT_LOWER"`. |

- **Runtime geometry override:** `lv_keyboard` resets its own `width`/`height` to a built-in default after `lv_keyboard_create()`. **Pin via** `localStyles.definition.MAIN.DEFAULT` with `align: "DEFAULT"`, `min_width`, `max_width`, `min_height`, `max_height` all equal to the desired pixel size. The default `localStyles` template at Keyboard.tsx:88-96 only sets `align: "DEFAULT"`; you must add the min/max entries explicitly.

### 4.13 LVGLDropdownWidget

- Class: `LVGLDropdownWidget` — Dropdown.tsx:36
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "SELECTED"]`
- Specific properties:

| Key | Type | Notes |
|---|---|---|
| `options` | newline-separated string (or expression) | Default `"Option 1\nOption 2\nOption 3"`. |
| `optionsType` | `"literal"` \| `"translated-literal"` \| `"expression"` | |
| `selected` | number-or-expression | Default `0`. |
| `selectedType` | type | |
| `direction` | `"top"` \| `"left"` \| `"bottom"` \| `"right"` | Default `"bottom"`. |

- **Runtime geometry note:** the popup list opens on click and is sized by LVGL — pin the **closed** dropdown's height/width via `localStyles.MAIN.DEFAULT.min_*`/`max_*`. Default `heightUnit` is `"content"`.

### 4.14 LVGLRollerWidget

- Class: `LVGLRollerWidget` — Roller.tsx:54
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_CHAIN_HOR|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "SELECTED"]`
- Specific properties: `options`, `optionsType`, `selected`, `selectedType`, `mode` (`"NORMAL"` / `"INFINITE"`).
- **Runtime geometry override:** Roller height is computed by LVGL from the visible row count × font line height — pin via `min_height` / `max_height` if you need exact pixel coverage.

### 4.15 LVGLTabviewWidget

- Class: `LVGLTabviewWidget` — Tabview.tsx:40
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific properties:

| Key | Type | Default | Notes |
|---|---|---|---|
| `tabviewPosition` | `"TOP"` \| `"BOTTOM"` \| `"LEFT"` \| `"RIGHT"` | `"TOP"` | |
| `tabviewSize` | number | `32` | Pixel height (or width) of the tab bar. |
| `selectedTab` | number-or-expression | `0` | |
| `selectedTabType` | type | `"literal"` | |

- Children: only `LVGLTabWidget` and `LVGLContainerWidget` (tab bar, tab content) — the `check` hook errors on anything else (Tabview.tsx:101-149).
- **Runtime geometry override:** Tabview computes its tab bar + content geometry from `tabviewPosition`/`tabviewSize`; pin the **tabview itself** via `min_*`/`max_*` if the authored size doesn't survive runtime construction.

### 4.16 LVGLTabWidget

- Class: `LVGLTabWidget` — Tab.tsx:28
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Only valid as a child of a `LVGLTabviewWidget` (or its content container).
- Specific: tab name property (read Tab.tsx for the exact field; usually `tabName`).

### 4.17 LVGLTextareaWidget

- Class: `LVGLTextareaWidget` — Textarea.tsx:20
- `defaultFlags` (LVGL 9.x): `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SNAPPABLE`
- `parts`: includes `MAIN`, `SCROLLBAR`, `SELECTED`, `CURSOR`, `TEXTAREA_PLACEHOLDER` (see Textarea.tsx:100-106).
- Specific:

| Key | Type | Notes |
|---|---|---|
| `placeholder` | string | |
| `oneLineMode` | boolean | |
| `passwordMode` | boolean | |
| `acceptedCharacters` | string | |
| `maxTextLength` | number | |

### 4.18 LVGLListWidget

- Class: `LVGLListWidget` — List.tsx:13
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "SCROLLBAR"]`
- No widget-specific properties.
- **Runtime geometry override:** `lv_list` sets internal padding and layout flags during creation. Pin via `localStyles.MAIN.DEFAULT.min_*`/`max_*`/`align`.

### 4.19 LVGLButtonMatrixWidget

- Class: `LVGLButtonMatrixWidget` — ButtonMatrix.tsx:219
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "ITEMS"]`
- Specific properties:

| Key | Type | Notes |
|---|---|---|
| `buttons` | array of `LVGLButtonMatrixButton` (`text`, `width`, `newLine`, plus the `ctrl*` flags below) | |
| `oneCheck` | boolean | |

Per-button `ctrl*` flags are the `LV_BUTTONMATRIX_CTRL_*` bits from lvgl-constants.ts:826-837 (`HIDDEN: 0x0010`, `NO_REPEAT: 0x0020`, `DISABLED: 0x0040`, `CHECKABLE: 0x0080`, `CHECKED: 0x0100`, `CLICK_TRIG: 0x0200`, `POPOVER: 0x0400`, `RECOLOR: 0x0800`, `CUSTOM_1: 0x4000`, `CUSTOM_2: 0x8000`).

- **Runtime geometry override:** ButtonMatrix lays out its buttons using internal width-fraction logic; pin via `localStyles.MAIN.DEFAULT.min_*`/`max_*`.

### 4.20 LVGLCalendarWidget

- Class: `LVGLCalendarWidget` — Calendar.tsx:28
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "ITEMS"]`
- Specific: `todayYear`, `todayMonth`, `todayDay`, `header` (enum for header type), `chineseMode` (boolean).

### 4.21 LVGLColorwheelWidget

- Class: `LVGLColorwheelWidget` — Colorwheel.tsx:18
- `defaultFlags`: `ADV_HITTEST|CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "KNOB"]`
- Specific: `mode` (`"HUE"`/`"SATURATION"`/`"VALUE"`), `fixedMode` (boolean), `knobRecolor` (boolean).

### 4.22 LVGLSpinboxWidget

- Class: `LVGLSpinboxWidget` — Spinbox.tsx:19
- `defaultFlags` (LVGL 9.x): `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_ON_FOCUS|SNAPPABLE`
- `parts`: `["MAIN", "SELECTED", "CURSOR"]`
- Specific: `digitCount`, `separatorPosition`, `min`, `max`, `rollover`.

### 4.23 LVGLSpinnerWidget

- Class: `LVGLSpinnerWidget` — Spinner.tsx:13
- `defaultFlags`: `CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "INDICATOR"]`
- No widget-specific properties (the spinner reads its speed/arc from `localStyles.INDICATOR.DEFAULT.arc_*`).

### 4.24 LVGLLedWidget

- Class: `LVGLLedWidget` — Led.tsx:21
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific: color, brightness — read Led.tsx for the exact names.

### 4.25 LVGLLineWidget

- Class: `LVGLLineWidget` — Line.tsx:28
- `defaultFlags`: `CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific: `points` (array of {x,y}), `invertY`, `needleLength`, `previewValue`.

### 4.26 LVGLCanvasWidget

- Class: `LVGLCanvasWidget` — Canvas.tsx:13
- `defaultFlags`: `ADV_HITTEST|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- No widget-specific properties — canvas content is drawn by C code.

### 4.27 LVGLChartWidget

- Class: `LVGLChartWidget` — Chart.tsx:13
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "ITEMS", "INDICATOR"]`
- Chart is largely C-driven; see Chart.tsx for whatever editor-time properties exist.

### 4.28 LVGLAnimationImageWidget

- Class: `LVGLAnimationImageWidget` — AnimationImage.tsx:161
- `defaultFlags`: `ADV_HITTEST|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific: `images` array of `{ image }` entries, `numImages`, `duration` (ms per frame), `repeatInfinite` (boolean), `repeat` (count).

### 4.29 LVGLQRCodeWidget

- Class: `LVGLQRCodeWidget` — QRCode.tsx:14
- `defaultFlags`: `CLICK_FOCUSABLE|SCROLLABLE|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_CHAIN|SCROLL_WITH_ARROW|SNAPPABLE|PRESS_LOCK|GESTURE_BUBBLE|ADV_HITTEST`
- `parts`: `["MAIN"]`
- Specific: `text` (string), `darkColor`, `lightColor` (color tokens or hex — but per skill rule use color tokens).

### 4.30 LVGLMeterWidget

- Class: `LVGLMeterWidget` — Meter.tsx:1255
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "TICKS", "INDICATOR", "ITEMS"]`
- Specific: complex `scales[]` array (each with `indicators[]`, plus nthMajor / majorTickWidth / label / labelGap). Read Meter.tsx for the full structure — it's 1500+ lines because each scale and each indicator type is its own EezObject class.

### 4.31 LVGLScaleWidget

- Class: `LVGLScaleWidget` — Scale.tsx:394
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN", "ITEMS", "INDICATOR"]`
- Specific: `scaleMode` (`HORIZONTAL_TOP`/`HORIZONTAL_BOTTOM`/`VERTICAL_LEFT`/`VERTICAL_RIGHT`/`ROUND_INNER`/`ROUND_OUTER`), `angleRange`, `totalTickCount`, `majorTickEvery`, `postDraw`, `drawTicksOnTop`, `showLabels`, `labelTexts`, plus main-line / arc / minor-tick / major-tick width/color/opacity/length properties. Read Scale.tsx for the full list.

### 4.32 LVGLSpanWidget

- Class: `LVGLSpanWidget` — Span.tsx:396
- `defaultFlags`: `CLICKABLE|CLICK_FOCUSABLE|GESTURE_BUBBLE|PRESS_LOCK|SCROLLABLE|SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER|SCROLL_ELASTIC|SCROLL_MOMENTUM|SCROLL_WITH_ARROW|SNAPPABLE`
- `parts`: `["MAIN"]`
- Specific: `mode` (`FIXED`/`EXPAND`/`BREAK`), `overflow` (`CLIP`/`ELLIPSIS`), `indent`, `maxLines`, `align`, `spans[]` array of style/text segments.

### 4.33 Other widgets

The remaining widget classes (each has the `defaultFlags` and `parts` already enumerated in the source walk earlier) are:

| Class | Source line | `parts` | `defaultFlags` shape |
|---|---|---|---|
| `LVGLMenuWidget` | Menu.tsx:13 | `["MAIN"]` | standard-container |
| `LVGLMessageBoxWidget` | MessageBox.tsx:13 | `["MAIN"]` | standard-container |
| `LVGLTableWidget` | Table.tsx:13 | `["MAIN","ITEMS","SCROLLBAR"]` | standard-container |
| `LVGLTileViewWidget` | TileView.tsx:13 | `["MAIN"]` | standard-container with `SCROLL_ONE` |
| `LVGLWindowWidget` | Window.tsx:13 | `["MAIN"]` | standard-container |
| `LVGLLottieWidget` | Lottie.tsx:13 | `["MAIN"]` | standard-container |

"standard-container" `defaultFlags` is the recurring string `CLICKABLE\|CLICK_FOCUSABLE\|GESTURE_BUBBLE\|PRESS_LOCK\|SCROLLABLE\|SCROLL_CHAIN_HOR\|SCROLL_CHAIN_VER\|SCROLL_ELASTIC\|SCROLL_MOMENTUM\|SCROLL_WITH_ARROW\|SNAPPABLE` — every widget with this exact set unless noted.

---

## 5. Flag enumeration

The bitmask values are at `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/lvgl-constants.ts#L205-L249`. Two tables — `LVGL_FLAG_CODES` (LVGL ≤ 9.0) and `LVGL_FLAG_CODES_90` (LVGL 9.0+, which moved `OVERFLOW_VISIBLE` from bit 19 to bit 20).

In `.eez-project` JSON, flag strings are pipe-separated **bare** names (no `LV_OBJ_FLAG_` prefix). The build pipeline prepends `LV_OBJ_FLAG_` when emitting C.

Valid names (every bit position in the tables):

| Name | Bit | Description (from source comments) |
|---|---|---|
| `HIDDEN` | 1 << 0 | Make the object hidden (lifted into `hiddenFlag`). |
| `CLICKABLE` | 1 << 1 | Receive input device events (lifted into `clickableFlag`). |
| `CLICK_FOCUSABLE` | 1 << 2 | Adds FOCUSED state when clicked. |
| `CHECKABLE` | 1 << 3 | Toggles CHECKED state on click. |
| `SCROLLABLE` | 1 << 4 | Make object scrollable. |
| `SCROLL_ELASTIC` | 1 << 5 | Allow elastic scroll. |
| `SCROLL_MOMENTUM` | 1 << 6 | Continue scroll after release. |
| `SCROLL_ONE` | 1 << 7 | Snap to one snappable child. |
| `SCROLL_CHAIN_HOR` | 1 << 8 | Propagate horizontal scroll to parent. |
| `SCROLL_CHAIN_VER` | 1 << 9 | Propagate vertical scroll to parent. |
| `SCROLL_ON_FOCUS` | 1 << 10 | Auto-scroll into view on focus. |
| `SCROLL_WITH_ARROW` | 1 << 11 | Arrow-key scroll for focused obj. |
| `SNAPPABLE` | 1 << 12 | Object can be snap target. |
| `PRESS_LOCK` | 1 << 13 | Stay pressed if pointer slides off. |
| `EVENT_BUBBLE` | 1 << 14 | Propagate events to parent. |
| `GESTURE_BUBBLE` | 1 << 15 | Propagate gestures to parent. |
| `ADV_HITTEST` | 1 << 16 | Use shape-aware hit test (rounded corners). |
| `IGNORE_LAYOUT` | 1 << 17 | Layouts skip this object. |
| `FLOATING` | 1 << 18 | Ignore parent scroll and layout. |
| `OVERFLOW_VISIBLE` | 1 << 19 (≤ LVGL 9.0) / 1 << 20 (LVGL 9.0+) | Children draw outside parent. |

Reactive flags `LVGL_REACTIVE_FLAGS` (lvgl-constants.ts:253-256): `HIDDEN`, `CLICKABLE` — these two are not allowed in `widgetFlags` (they're carried in `hiddenFlag`/`clickableFlag` instead). The migration hook strips them out (Base.tsx:1133).

Legacy `SCROLL_CHAIN` (single bit, no _HOR/_VER split) appears in old `defaultFlags` strings (`oldDefaultFlags`) and is migrated to `SCROLL_CHAIN_HOR|SCROLL_CHAIN_VER` automatically (Base.tsx:1155-1160). Don't author it in new JSON.

---

## 6. State enumeration

Two version-keyed tables in lvgl-constants.ts:260-296:

- `lvglStates` (LVGL ≤ 9.4.x) and
- `lvglStates_V9_5_0` (LVGL 9.5.0+; bit positions shifted).

The state names valid in `states` (pipe-separated, no prefix):

| Name | Code (pre-9.5) | Code (9.5+) | Use |
|---|---|---|---|
| `DEFAULT` | 0x0000 | 0x0000 | Implicit; can be omitted. |
| `CHECKED` | 0x0001 | 0x0004 | Lifted into `checkedState`. |
| `FOCUSED` | 0x0002 | 0x0008 | |
| `FOCUS_KEY` | 0x0004 | 0x0010 | |
| `EDITED` | 0x0008 | 0x0020 | |
| `HOVERED` | 0x0010 | 0x0040 | |
| `PRESSED` | 0x0020 | 0x0080 | |
| `SCROLLED` | 0x0040 | 0x0100 | |
| `DISABLED` | 0x0080 | 0x0200 | Lifted into `disabledState`. |
| `USER_1`–`USER_4` | 0x1000–0x8000 | 0x1000–0x8000 | Free for app use. |
| `ANY` | 0xFFFF | 0xFFFF | Selector-only; not a state to add. |

Reactive states `LVGL_REACTIVE_STATES`: `CHECKED`, `DISABLED` — not allowed in `states`.

**States valid as `localStyles` state keys** (lvgl-constants.ts:343-354):
```
DEFAULT, CHECKED, PRESSED, CHECKED|PRESSED, DISABLED, FOCUSED, FOCUS_KEY, EDITED, HOVERED, SCROLLED
```
The compound `CHECKED|PRESSED` is special-cased in build.ts to emit `CHECKED_PRESSED` as a C identifier (build.ts:799-812).

---

## 7. Part enumeration

Two version-keyed tables: `LVGL_PARTS_8` (lvgl-constants.ts:360-374) and `LVGL_PARTS_9` (376-389). The only difference: LVGL 8's `TICKS` was at `0x060000` and `CURSOR` was at `0x070000`; LVGL 9 dropped `TICKS` and moved `CURSOR` to `0x060000`.

Part names valid as keys in `localStyles.definition.<PART>`:

| Name | Code | Notes |
|---|---|---|
| `MAIN` | 0x000000 | Background-style rectangle — always valid. |
| `SCROLLBAR` | 0x010000 | Valid on container-type widgets (Screen, Panel, List, UserWidget, Table). |
| `INDICATOR` | 0x020000 | Bar/Slider/Switch/Arc/Checkbox/Spinner/Meter/Scale. |
| `KNOB` | 0x030000 | Slider/Switch/Arc/Colorwheel. |
| `SELECTED` | 0x040000 | Dropdown/Roller/Spinbox. |
| `ITEMS` | 0x050000 | ButtonMatrix/Calendar/Keyboard/Meter/Scale/Table. |
| `TICKS` | 0x060000 (LVGL 8) | Meter only. |
| `CURSOR` | 0x060000 (LVGL 9) / 0x070000 (LVGL 8) | Spinbox/Textarea. |
| `CUSTOM1` | 0x080000 | Custom widgets. |
| `TEXTAREA_PLACEHOLDER` | 0x080000 | Textarea only (alias of CUSTOM1). |
| `ANY` | 0x0F0000 | Selector-only. |

The list of valid parts **per widget type** is `lvgl.parts` declared in each widget's `classInfo` (Section 4 above). Authoring `localStyles.<PART>.…` for a part not in that widget's `parts` array is a silent no-op at runtime — the C export will still emit `lv_obj_set_style_<prop>(obj, val, LV_PART_<PART> | …)` but LVGL ignores it.

---

## 8. Style properties

Every property valid in `localStyles.<PART>.<STATE>.<prop>` (and in named `lvglStyles[].definition`) is keyed in `lvglPropertiesMap`, built at `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/style-catalog.tsx#L2819-L2827`. The property groups (style-catalog.tsx:2576-2803) are:

### 8.1 POSITION AND SIZE

| Property | Type | Notes |
|---|---|---|
| `align` | enum (`DEFAULT`, `TOP_LEFT`, `TOP_MID`, `TOP_RIGHT`, `LEFT_MID`, `CENTER`, `RIGHT_MID`, `BOTTOM_LEFT`, `BOTTOM_MID`, `BOTTOM_RIGHT`, `OUT_TOP_LEFT`, `OUT_TOP_MID`, `OUT_TOP_RIGHT`, …) | Emitted as `LV_ALIGN_*`. **Pin to `"DEFAULT"` when you want EEZ Studio's authored geometry to survive runtime-override widget construction.** |
| `width`, `height` | number or special | Usually emitted via `lv_obj_set_width`/`set_height`; setting this in `localStyles` is the override path for the authored Base `width`/`height`. |
| `length` | number | LVGL 9.x: used for square objects. |
| `min_width`, `max_width`, `min_height`, `max_height` | number | **The pin pair for runtime-override widgets.** Set both `min_*` and `max_*` to the same value to lock geometry. |
| `x`, `y` | number | Same role as `left`/`top` but applied via style. |
| `transform_width`, `transform_height` | number | Adds to the bounding box without affecting layout. |
| `translate_x`, `translate_y` | number | Post-layout shift. |
| `transform_zoom` (LVGL 8) | number | |
| `transform_scale_x`, `transform_scale_y` (LVGL 9) | number | 256 = 1.0×. |
| `transform_angle` (LVGL 8) / `transform_rotation` (LVGL 9) | number | 0.1° units. |
| `transform_pivot_x`, `transform_pivot_y` | number | |
| `transform_skew_x`, `transform_skew_y` (LVGL 9) | number | |

### 8.2 LAYOUT

| Property | Type | Notes |
|---|---|---|
| `layout` | `"NONE"`/`"FLEX"`/`"GRID"` | Setting `"GRID"` auto-adds empty `grid_row_dsc_array` and `grid_column_dsc_array` entries (style-definition.tsx:191-218). |
| `flex_flow` | enum (`ROW`, `COLUMN`, `ROW_WRAP`, `ROW_REVERSE`, `ROW_WRAP_REVERSE`, `COLUMN_WRAP`, `COLUMN_REVERSE`, `COLUMN_WRAP_REVERSE`) | |
| `flex_main_place`, `flex_cross_place`, `flex_track_place` | enum (`START`, `END`, `CENTER`, `SPACE_EVENLY`, `SPACE_AROUND`, `SPACE_BETWEEN`) | |
| `flex_grow` | number | |
| `grid_column_align`, `grid_row_align` | enum (`START`, `CENTER`, `END`, `STRETCH`, `SPACE_EVENLY`, `SPACE_AROUND`, `SPACE_BETWEEN`) | Migration prepends `SPACE_` to bare `EVENLY`/`AROUND`/`BETWEEN` (style-definition.tsx:107-125). |
| `grid_row_dsc_array`, `grid_column_dsc_array` | string — comma-separated track sizes (`"50,LV_GRID_FR(1),50"`) | |
| `grid_cell_column_pos`, `grid_cell_column_span` | number | |
| `grid_cell_row_pos`, `grid_cell_row_span` | number | |
| `grid_cell_x_align`, `grid_cell_y_align` | enum (same as grid_*_align) | |

### 8.3 PADDING

| `pad_top`, `pad_bottom`, `pad_left`, `pad_right`, `pad_radial`, `pad_row`, `pad_column` | number |

### 8.4 MARGIN

| `margin_top`, `margin_bottom`, `margin_left`, `margin_right` | number |

### 8.5 BACKGROUND

| Property | Type |
|---|---|
| `bg_color` | color (named token from `colors[]`) |
| `bg_opa` | 0–255 |
| `bg_grad_dir` | enum (`NONE`, `VER`, `HOR`) |
| `bg_grad_color` | color |
| `bg_grad_stop`, `bg_main_stop` | 0–255 |
| `bg_main_opa`, `bg_grad_opa` | 0–255 |
| `bg_dither_mode` | enum (LVGL 8) |
| `bg_img_src` | bitmap reference |
| `bg_img_opa` | 0–255 |
| `bg_img_recolor` | color |
| `bg_img_recolor_opa` | 0–255 |
| `bg_img_tiled` | boolean |

### 8.6 BORDER

| `border_color` | color |
| `border_opa` | 0–255 |
| `border_width` | number |
| `border_side` | enum (`NONE`, `TOP`, `BOTTOM`, `LEFT`, `RIGHT`, `INTERNAL`, `FULL`) |
| `border_post` | boolean |

### 8.7 OUTLINE

| `outline_width`, `outline_color`, `outline_opa`, `outline_pad` | number/color/number/number |

### 8.8 SHADOW

| `shadow_width`, `shadow_ofs_x`, `shadow_ofs_y`, `shadow_spread`, `shadow_color`, `shadow_opa` | number/number/number/number/color/number |

### 8.9 IMAGE

| `img_opa`, `img_recolor`, `img_recolor_opa` | number/color/number |

### 8.10 LINE

| `line_width`, `line_dash_width`, `line_dash_gap`, `line_rounded`, `line_color`, `line_opa` | number/number/number/boolean/color/number |

### 8.11 ARC

| `arc_width`, `arc_rounded`, `arc_color`, `arc_opa`, `arc_img_src` | number/boolean/color/number/bitmap |

### 8.12 TEXT

| `text_color` | color |
| `text_opa` | 0–255 |
| `text_font` | font name — must be either an uppercase LVGL built-in (`MONTSERRAT_14`, etc., from `BUILT_IN_FONTS`) or a lowercase custom font name from `fonts[]`. |
| `text_letter_space`, `text_line_space` | number |
| `text_decor` | enum (`NONE`, `UNDERLINE`, `STRIKETHROUGH`) |
| `text_align` | enum (`AUTO`, `LEFT`, `CENTER`, `RIGHT`) |

### 8.13 MISCELLANEOUS

| `radius` | number |
| `radial_offset` (LVGL 9.3+) | number |
| `clip_corner` | boolean |
| `opa` | 0–255 (object opacity) |
| `blend_mode` | enum (`NORMAL`, `ADDITIVE`, `SUBTRACTIVE`, `MULTIPLY`, `REPLACE`) |
| `base_dir` | enum (`LTR`, `RTL`, `AUTO`) |
| `anim` | reference |
| `anim_time` (LVGL 8) | number ms |
| `anim_duration` (LVGL 9) | number ms |
| `anim_speed` (LVGL 8) | number |

### 8.14 Version availability

For each property the per-LVGL-version style code is in `LVGL_STYLE_PROP_CODES` (lvgl-constants.ts:11-129). `undefined` for a given version means the property is **not available** in that LVGL version. Example: `length`, `radial_offset`, `pad_radial`, `margin_*`, `bg_main_opa`/`bg_grad_opa`, `transform_scale_*`, `transform_rotation`, `transform_skew_*` are all LVGL 9.x only. `transform_zoom`, `transform_angle`, `anim_time`, `anim_speed`, `bg_dither_mode` are LVGL 8.x only.

The `unusedProperties` list (style-catalog.tsx:2805-2817) is the set of properties EEZ Studio never surfaces in its UI: `width`, `height`, `x`, `y`, `bg_grad`, `color_filter_dsc`, `color_filter_opa`, `anim`, `transition`. Don't author these in `localStyles`.

---

## 9. Style cascade

Resolution order at runtime, highest priority first:

1. **`widget.localStyles.definition[part][state][prop]`** — per-widget instance override. Highest priority.
2. **The widget's named `useStyle` style** — the entry in `lvglStyles.styles[]` whose `name` matches `widget.useStyle` and whose `forWidgetType` matches the widget's `type`. Resolved by `findLvglStyle` (style.tsx:184). If the named style has a `parentStyle` chain (`childStyles[]` nesting), values cascade child → parent (style.tsx:344-365).
3. **`lvglStyles.defaultStyles[widget.type]`** — if no `useStyle` is set, EEZ Studio applies the default style for this widget type. Source: `LVGLStyles.defaultStyles` map (style.tsx:689-691).
4. **LVGL built-in defaults** — whatever `lv_<widget>_create()` produces. Fall-through.

**Implications for validation:**
- A `widget.useStyle` value MUST resolve to an entry in `lvglStyles.styles[]` (or a recursive descendant via `childStyles`) whose `forWidgetType` equals the widget's `type`. Mismatched `forWidgetType` is a silent no-op.
- A `widget.useStyle` of `""` means "no project style"; with a `defaultStyles[widget.type]` entry, the default still applies. To suppress all project styling, leave both empty.
- The same property at the same `<part>.<state>` in both `localStyles` and the named style is "redundant"; EEZ Studio's UI shows a count in the style list label (style.tsx:210-217).
- Cascade combines properties across the (`childStyle.definition` → `parentStyle.definition` → … → `defaultStyles[type]`) chain — a property defined only in the parent style is inherited by the child unless overridden.

The `LVGLStyle` schema:

| Key | Type | Notes |
|---|---|---|
| `name` | string | Globally unique across `lvglStyles.styles` + nested `childStyles`. |
| `forWidgetType` | string | One of the widget class names (see Section 4). EEZ Studio uses this to filter which widgets can pick this style. |
| `childStyles` | array of `LVGLStyle` | Nested styles for cascade. |
| `definition` | `LVGLStylesDefinition` (`{ definition: { <part>: { <state>: { <prop>: <value> } } } }`) | |

The `LVGLStyles` container:

| Key | Type | Notes |
|---|---|---|
| `styles` | array of `LVGLStyle` | The root-level styles. |
| `defaultStyles` | `{ [widgetType: string]: string }` | Map from widget class name to default style name. e.g. `{ "LVGLButtonWidget": "PrimaryButton" }`. |

---

## 10. Color/theme schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/style/theme.tsx`.

### 10.1 `Color` (entries in `colors[]`)

Defined at theme.tsx:314-365.

| Key | Type | Notes |
|---|---|---|
| `colorId` | string | Internal unique identifier — usually omitted; EEZ Studio fills it in. |
| `id` | number (optional) | Asset ID — LVGL projects don't use it. |
| `name` | string | The token name referenced from style properties (e.g. `"BackgroundPanel"`). Unique across `colors[]`. |

```json
{ "colors": [
    { "name": "ForegroundPrimary" },
    { "name": "BackgroundCanvas" },
    { "name": "AccentColor" }
] }
```

### 10.2 `Theme` (entries in `themes[]`)

Defined at theme.tsx:558-618.

| Key | Type | Notes |
|---|---|---|
| `name` | string | Theme name, unique across `themes[]`. |
| `colors` | array of hex strings — parallel to top-level `colors[]` | The value of each color token *in this theme*. |

```json
{ "themes": [
    { "name": "Default", "colors": ["#1a1a1a", "#fafafa", "#52a441"] },
    { "name": "Dark",    "colors": ["#fafafa", "#0a0a0a", "#52a441"] }
] }
```

### 10.3 Parallelism invariant

**Every theme's `colors[]` array MUST have the same length as the top-level `colors[]`.** Position `i` in `themes[t].colors` is the hex value for the token at position `i` in `colors[]`. A mismatch is a structural break — the project loads, but lookups by token name produce wrong colors or empty strings.

### 10.4 `themesVersion`

Number, starts at `1` for legacy projects (auto-set by `beforeLoadHook`, project.tsx:1456-1460). New projects typically write `themesVersion: 3` (matches the parsing logic in current EEZ Studio).

### 10.5 Color value forms accepted in style properties

A color *value* in a `localStyles` or `LVGLStyle.definition` can be:
- A **named token** — the `name` from `colors[]` (e.g. `"ForegroundPrimary"`). This is the only form the skill's no-hex rule permits.
- A `#RRGGBB` hex literal — supported by the build pipeline (build.ts:867-878, `ColorFormat.parse`) but **forbidden by the skill's authoring rule**.
- A `darken(<token-or-hex>, <amount>)` / `lighten(<token-or-hex>, <amount>)` filter — recognized by `ColorFormatType.DARKEN`/`LIGHTEN` (build.ts:830-859).

---

## 11. Font schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/font/font.tsx#L1527-L1700` (the `Font.classInfo.properties` array).

### 11.1 `Font` entry

| Key | Type | Notes |
|---|---|---|
| `name` | string | Unique. Naming convention determines code-gen: **uppercase → LVGL built-in `lv_font_*`**; **lowercase → custom `ui_font_*`** generated/embedded by EEZ Studio. |
| `description` | string | Optional. |
| `renderingEngine` | `"freetype"` \| `"opentype"` | Required; disabled in LVGL projects (forced to one value). |
| `source` | `FontSource` object — `{ filePath: string, size: number }` | Path is relative to the project file. |
| `embeddedFontFile` | string | Set when the font is bundled into the project file as base64. |
| `bpp` | `1` \| `2` \| `4` \| `8` | Bits per pixel for glyph rasterization. |
| `threshold` | number (0–255) | 1-bpp threshold. Default `128`. |
| `height` | number | Font line height (pixels). |
| `ascent`, `descent` | number | Font metrics. |
| `glyphs` | array of `Glyph` | Pre-rasterized glyphs — not used by LVGL projects (LVGL fonts use the `lvgl*` fields below). |
| `lvglGlyphs` | object | Holds `encodings[]` — the rasterized glyph subset for LVGL output. |
| `lvglRanges` | string | Comma-separated Unicode ranges to include (e.g. `"0x20-0x7F, 0xA0-0xFF"`). |
| `lvglSymbols` | string | Additional individual characters or LVGL symbol macro names (e.g. `"LV_SYMBOL_OK,LV_SYMBOL_CLOSE"`). |
| `screenOrientation` | enum (`"all"`/`"portrait"`/`"landscape"`) | V1 projects only; disabled for LVGL. |
| `alwaysBuild` | boolean | Disabled for LVGL. |

### 11.2 Built-in font names

The `BUILT_IN_FONTS` list (style-catalog.tsx, imported in style-definition.tsx:30) defines the uppercase font names recognized as LVGL built-ins. Typical members include `MONTSERRAT_8` through `MONTSERRAT_48`, `DEJAVU_16_PERSIAN_HEBREW`, `SIMSUN_16_CJK`, plus symbol fonts. (Exact list varies by LVGL version — read `BUILT_IN_FONTS` in style-catalog.tsx if you need the precise set.)

When `text_font` in a style references an uppercase name, the build emits `&lv_font_<name>` directly. When it references a lowercase name, the build emits `&ui_font_<name>` and expects a corresponding `fonts[].source.filePath` plus rasterized glyph data.

---

## 12. Event handler schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/flow/component.tsx#L2480-L2600`.

Each entry in `widget.eventHandlers[]` is an `EventHandler`:

| Key | Type | Notes |
|---|---|---|
| `eventName` | string | One of the keys from the LVGL events table for the current LVGL version (see below). Filtered by `getEventEnumItems` to events not yet handled. |
| `handlerType` | `"action"` \| `"flow"` | For `flowSupport: false` projects, must be `"action"` (the flow option is disabled — component.tsx:2519-2521). |
| `action` | string — name of an `actions[]` entry | Required when `handlerType: "action"`. |
| `userData` | number | LVGL-only field (component.tsx:2532-2535); defaulted to `0` on load. Passed as the `user_data` argument to the action handler. |

The legacy field `trigger` is migrated to `eventName` on load (component.tsx:2592-2595).

### 12.1 Valid `eventName` values

There are four version-keyed event tables in lvgl-constants.ts:398-679:

- `LVGL_EVENTS_V8` — LVGL 8.x.
- `LVGL_EVENTS_V9_2_2` — LVGL 9.0–9.2.x.
- `LVGL_EVENTS_V9_3_0` — LVGL 9.3.x.
- `LVGL_EVENTS_V9_5_0` — LVGL 9.5.x.

Common events present in **all** versions (use these for portability):

`PRESSED`, `PRESSING`, `PRESS_LOST`, `SHORT_CLICKED`, `LONG_PRESSED`, `LONG_PRESSED_REPEAT`, `CLICKED`, `RELEASED`, `SCROLL_BEGIN`, `SCROLL_END`, `SCROLL`, `GESTURE`, `KEY`, `FOCUSED`, `DEFOCUSED`, `LEAVE`, `HIT_TEST`, `COVER_CHECK`, `REFR_EXT_DRAW_SIZE`, `DRAW_MAIN_BEGIN`, `DRAW_MAIN`, `DRAW_MAIN_END`, `DRAW_POST_BEGIN`, `DRAW_POST`, `DRAW_POST_END`, `VALUE_CHANGED`, `INSERT`, `REFRESH`, `READY`, `CANCEL`, `DELETE`, `CHILD_CHANGED`, `CHILD_CREATED`, `CHILD_DELETED`, `SCREEN_UNLOAD_START`, `SCREEN_LOAD_START`, `SCREEN_LOADED`, `SCREEN_UNLOADED`, `SIZE_CHANGED`, `STYLE_CHANGED`, `LAYOUT_CHANGED`, `GET_SELF_SIZE`, `CHECKED`, `UNCHECKED`.

LVGL 9+ adds: `SCROLL_THROW_BEGIN`, `ROTARY`, `INDEV_RESET`, `HOVER_OVER`, `HOVER_LEAVE`, `DRAW_TASK_ADDED`, `INVALIDATE_AREA`, `RESOLUTION_CHANGED`, `COLOR_FORMAT_CHANGED`, `REFR_REQUEST`, `REFR_START`, `REFR_READY`, `RENDER_START`, `RENDER_READY`, `FLUSH_START`, `FLUSH_FINISH`, `FLUSH_WAIT_START`, `FLUSH_WAIT_FINISH`, `VSYNC`, `CREATE`.

LVGL 9.3+ adds: `SINGLE_CLICKED`, `DOUBLE_CLICKED`, `TRIPLE_CLICKED`.

LVGL 8 only: `DRAW_PART_BEGIN`, `DRAW_PART_END`.

The `CHECKED` and `UNCHECKED` codes are fixed across versions (`0x7E` and `0x7F`) — they're LVGL-Studio extensions.

---

## 13. Action schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/action/action.tsx#L196-L260` (Action class properties).

Each entry in `actions[]`:

| Key | Type | Notes |
|---|---|---|
| `id` | number (optional) | Asset ID — LVGL projects: unused (disabled). |
| `name` | string | Unique. Becomes the C identifier suffix: emitted as `action_<underscored_lowercase_name>` (build.ts:536-541). |
| `description` | string | Optional. |
| `implementationType` | `"native"` \| `"flow"` | For `flowSupport: false` projects, must be `"native"`. |
| `implementation` | string (multi-line) | Flow JSON (when `implementationType: "flow"`); empty/absent for native actions. |
| `nativeImplementationInfo` | object | Auto-populated by EEZ Studio when `implementationType: "native"`. |
| `usedIn` | array of build configuration names | Optional restriction. |

For `flowSupport: false` projects, each `actions[].name` becomes a forward declaration in the generated `actions.h`:
```c
extern void action_<name>(lv_event_t *e);
```
The agent's `main/actions.c` provides the body of each declared action.

---

## 14. Variable schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/variable/variable.tsx#L1683-L1700`.

The `variables` root key has three sub-arrays:

| Key | Type |
|---|---|
| `globalVariables` | array of `Variable` |
| `structures` | array of `Structure` |
| `enums` | array of `Enum` |

### 14.1 `Variable` (entries in `globalVariables[]`)

Properties (variable.tsx:375-515):

| Key | Type | Notes |
|---|---|---|
| `id` | number (optional) | LVGL: disabled. |
| `name` | string | Unique across variables and user-properties. C identifier: `get_var_<underscored_lowercase>` / `set_var_<underscored_lowercase>` (build.ts:544-557). |
| `description` | string | Optional. |
| `type` | string | One of: `"integer"`, `"float"`, `"double"`, `"boolean"`, `"string"`, `"array:<basetype>"`, `"struct:<StructName>"`, `"enum:<EnumName>"`, `"object:<TypeName>"`. |
| `defaultValue` | string | Default value expression; constant. |
| `size` | number | Used only by EEZ-Flow-Lite for `string` and `array:*` types. LVGL: disabled. |
| `native` | boolean | When `true` (flow projects only), the variable is provided by user C code (`get_var_<name>`/`set_var_<name>`). LVGL with `flowSupport: false`: all variables are native by default. |
| `nativeImplementationInfo` | object | Computed; describes the C-side getter/setter signatures EEZ Studio expects. |
| `persistent` | boolean | LVGL: disabled (forbidden). |
| `defaultValueList` | string | LVGL/flow: disabled. |
| `usedIn` | array of build-config names | LVGL: disabled. |

### 14.2 `Structure` (entries in `structures[]`)

| Key | Type |
|---|---|
| `name` | string |
| `fields` | array of `{ name, type }` |

### 14.3 `Enum` (entries in `enums[]`)

| Key | Type |
|---|---|
| `name` | string |
| `members` | array of `{ name, value }` |

---

## 15. Bitmap schema

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/features/bitmap/bitmap.tsx#L154-L258`.

Each entry in `bitmaps[]`:

| Key | Type | Notes |
|---|---|---|
| `id` | number (optional) | LVGL: disabled. |
| `name` | string | Unique. Referenced from `LVGLImageWidget.image`, `Imgbutton.image*`, etc. |
| `description` | string | |
| `image` | string — base64-encoded PNG (or path when not embedded) | The image data. |
| `bpp` | `8` \| `16` \| `24` \| `32` \| LVGL-specific values | Bits per pixel. |
| `lvglBinaryOutputFormat` | enum (LVGL color format — `LV_COLOR_FORMAT_*` values) | |
| `lvglDither` | boolean | |
| `style` | string | Non-LVGL only (disabled in LVGL projects). |
| `alwaysBuild` | boolean | |

---

## 16. LVGL groups

Source: `https://github.com/eez-open/studio/blob/master/packages/project-editor/lvgl/groups.tsx#L200-L315`.

The top-level `lvglGroups` object:

| Key | Type | Notes |
|---|---|---|
| `groups` | array of `LVGLGroup` | Each `LVGLGroup` has a `name` (string, unique). |
| `defaultGroupForEncoderInSimulator` | string | Optional; name of one of the groups. |
| `defaultGroupForKeyboardInSimulator` | string | Optional; name of one of the groups. |

Widgets reference a group via the Base properties `group` (group name) and `groupIndex` (integer order within the group). At runtime EEZ Studio emits a `SCREEN_LOAD_START` event handler that calls `lv_group_remove_all_objs` + `lv_group_add_obj` for every widget bound to the group (Screen.tsx:85-112).

---

## 17. Code-generation pipeline

The export step (`File → Build` or Ctrl+B) runs the pipeline at `https://github.com/eez-open/studio/blob/master/packages/project-editor/build/build.ts#L230-L244` (`buildProject`), which delegates to `buildAssets` in `build/assets.ts`. Each entry in `settings.build.files[]` is then template-substituted with `${eez-studio <PLACEHOLDER>}` markers (regex at build.ts:246).

### 17.1 Template placeholders

LVGL-specific placeholders, produced by `buildAssets()` at `build/assets.ts:1773-1903`:

| Placeholder | Content | Conventional output file |
|---|---|---|
| `${eez-studio LVGL_INCLUDE}` | `#include <lvgl.h>` (or whatever `settings.build.lvglInclude` says) | top of `screens.c`, etc. |
| `${eez-studio LVGL_SCREENS_DECL}` | `extern lv_obj_t *<screen>_obj;` for each page; `objects` struct declaration. | `screens.h` |
| `${eez-studio LVGL_SCREENS_DECL_EXT}` | Extended screen declarations including user widgets. | `screens.h` |
| `${eez-studio LVGL_SCREENS_DEF}` | `create_screen_<name>()` / `tick_screen_<name>()` function bodies. | `screens.c` |
| `${eez-studio LVGL_SCREENS_DEF_EXT}` | Extended screen definitions (user-widget create/tick functions). | `screens.c` |
| `${eez-studio LVGL_STYLES_DECL}` | `lv_style_t` declarations for each named style/state/part combination. | `styles.h` |
| `${eez-studio LVGL_STYLES_DEF}` | `init_style_<name>_<part>_<state>()` function bodies. | `styles.c` |
| `${eez-studio LVGL_IMAGES_DECL}` | `extern const lv_img_dsc_t img_<name>;` per bitmap. | `images.h` |
| `${eez-studio LVGL_IMAGES_DEF}` | `images[]` array — array of bitmap descriptor pointers indexed by ID. | `images.c` |
| `${eez-studio LVGL_FONTS_DECL}` | `extern lv_font_t ui_font_<name>;` per custom font. | `fonts.h` (or wherever your build file references it) |
| `${eez-studio LVGL_ACTIONS_DECL}` | `extern void action_<name>(lv_event_t *e);` per action — **flow-disabled projects use this; the C user must supply the body in `actions.c`.** | `actions.h` |
| `${eez-studio LVGL_ACTIONS_ARRAY_DEF}` | `ActionExecFunc actions[]` — array of action function pointers indexed by action ID. | `actions.c` (flow-supported only) |
| `${eez-studio LVGL_VARS_DECL}` | `extern <type> get_var_<name>(void);` / `set_var_<name>(<type>);` per global variable. | `vars.h` |
| `${eez-studio LVGL_NATIVE_VARS_TABLE_DEF}` | `native_var_t native_vars[]` — table mapping variable ID to getter/setter. | `vars.c` (flow-supported only) |
| `${eez-studio LVGL_LOAD_FIRST_SCREEN}` | `loadScreen(SCREEN_ID_<first>);` call. | `ui.c` |
| `${eez-studio EEZ_FOR_LVGL_CHECK}` | Build-time `#error` directives that fail compile if LVGL config doesn't match project settings. | `ui.c` |

Asset-data placeholders (used by flow-supported projects only):

| Placeholder | Content |
|---|---|
| `${eez-studio GUI_ASSETS_DECL}` | Forward declaration of the compressed asset blob. |
| `${eez-studio GUI_ASSETS_DECL_COMPRESSED}` | Compressed-data declaration. |
| `${eez-studio GUI_ASSETS_DEF}` | The actual byte array. |
| `${eez-studio GUI_ASSETS_DEF_COMPRESSED}` | Compressed byte array. |
| `${eez-studio GUI_ASSETS_DATA}` / `GUI_ASSETS_DATA_MAP}` | Binary blob (when the template is absent and EEZ Studio writes to a `.res` file). |

`${eez-studio GUI_PAGES_ENUM}` (build/assets.ts:1939-1955) — emits a `enum PagesEnum { PAGE_ID_NONE=0, PAGE_ID_<NAME>=1, ... }`.

### 17.2 Naming conventions in generated code

Per build.ts:526-557:

- Screen create/delete/tick functions: `create_screen_<id>` / `delete_screen_<id>` / `tick_screen_<id>` for normal pages; `create_user_widget_<id>` / `tick_user_widget_<id>` for user-widget pages. `<id>` is the page name converted to `lowercase_with_underscores`.
- Action functions: `action_<name>` (`<name>` lowercased with underscores).
- Variable getter/setter functions: `get_var_<name>` / `set_var_<name>`.
- Style init functions: `init_style_<styleName>_<part>_<state>` (build.ts:786-802). State `CHECKED|PRESSED` becomes `CHECKED_PRESSED`.
- Style getter functions: `get_style_<styleName>_<part>_<state>`.
- Group variable accessor: `groups.<groupName>`.
- Widget accessor in `objects` struct: `objects.<codeIdentifier>` — `codeIdentifier` is the widget's `identifier` converted to `lowercase_with_underscores` (Base.tsx:602-614).

### 17.3 Conventional output files

For the standard EEZ-Studio-LVGL build, `settings.build.files[]` lists six template files that consume the placeholders above:

| File | Placeholders used |
|---|---|
| `screens.h` | `LVGL_SCREENS_DECL`, `LVGL_SCREENS_DECL_EXT`, `LVGL_INCLUDE` |
| `screens.c` | `LVGL_SCREENS_DEF`, `LVGL_SCREENS_DEF_EXT`, `LVGL_INCLUDE` |
| `styles.h` | `LVGL_STYLES_DECL`, `LVGL_INCLUDE` |
| `styles.c` | `LVGL_STYLES_DEF`, `LVGL_INCLUDE` |
| `images.h` | `LVGL_IMAGES_DECL`, `LVGL_INCLUDE` |
| `images.c` | `LVGL_IMAGES_DEF`, `LVGL_INCLUDE` |
| `actions.h` | `LVGL_ACTIONS_DECL`, `LVGL_INCLUDE` |
| `vars.h` | `LVGL_VARS_DECL`, `LVGL_INCLUDE` |
| `ui.h` | `LVGL_FONTS_DECL`, `LVGL_INCLUDE` |
| `ui.c` | `LVGL_LOAD_FIRST_SCREEN`, `EEZ_FOR_LVGL_CHECK`, `LVGL_INCLUDE` |

This is the conventional layout for a flow-disabled LVGL project. Templates can be customized via `settings.build.files`; the placeholders above are the contract.

---

## 18. Validation checklist

A concrete, mechanical checklist a script can run against a candidate `.eez-project` JSON.

### 18.1 Top-level

- [ ] `settings.general.projectType === "LVGL"`.
- [ ] `settings.general.lvglVersion` is set (e.g. `"9.1"`).
- [ ] `settings.general.flowSupport` is boolean.
- [ ] `settings.general.displayWidth` and `displayHeight` are positive integers.
- [ ] `settings.build.destinationFolder` is a string.
- [ ] `settings.build.files` is an array; every entry has `fileName` (string) and `template` (string).
- [ ] `themesVersion` is present (number).
- [ ] `colors` is an array. Each entry has `name` (string, unique).
- [ ] `themes` is an array. Each entry has `name` (string, unique) and `colors` (array of hex strings).
- [ ] **For every theme `t`, `themes[t].colors.length === colors.length`** (the parallel-array invariant).
- [ ] `variables` is an object with `globalVariables` (array), `structures` (array), `enums` (array).
- [ ] `actions` is an array.
- [ ] `userPages` is an array; every entry has `name` (unique within `userPages`+`userWidgets`), `width`, `height`, `components` (array).
- [ ] `userWidgets` is an array; every entry has `isUsedAsUserWidget: true`.
- [ ] `fonts` is an array.
- [ ] `bitmaps` is an array.
- [ ] `lvglStyles` is an object with `styles` (array) and `defaultStyles` (object).
- [ ] `lvglGroups` is an object with `groups` (array).

### 18.2 Per-page

- [ ] `page.components[0].type === "LVGLScreenWidget"`.
- [ ] The screen widget does **not** have an `identifier` field (the Page's `name` is the identifier).
- [ ] The screen widget has all of: `left`, `top`, `width`, `height`, `leftUnit`, `topUnit`, `widthUnit`, `heightUnit`, `widgetFlags`, `states`, `hiddenFlag`, `hiddenFlagType`, `clickableFlag`, `clickableFlagType`, `checkedState`, `checkedStateType`, `disabledState`, `disabledStateType`, `useStyle`, `localStyles`, `children`.
- [ ] `localStyles` has the shape `{ "definition": { ... } }` (may be `{}` definition).

### 18.3 Per-widget (every entry in `children[]`)

- [ ] `type` is one of the known LVGLClass names (Section 4).
- [ ] `identifier` is set (or empty string when not addressed from code; common for decorative widgets).
- [ ] All of `left`, `top`, `width`, `height`, `leftUnit`, `topUnit`, `widthUnit`, `heightUnit` are present.
- [ ] All four reactive-flag pairs are present (`hiddenFlag`+`hiddenFlagType`, `clickableFlag`+`clickableFlagType`, `checkedState`+`checkedStateType`, `disabledState`+`disabledStateType`).
- [ ] `widgetFlags` is a string (possibly empty). When non-empty, each `|`-separated token is one of the flag names in Section 5 — and NOT `HIDDEN` or `CLICKABLE` (reactive flags).
- [ ] `states` is a string (possibly empty). When non-empty, each `|`-separated token is one of the non-reactive state names in Section 6 — and NOT `CHECKED` or `DISABLED`.
- [ ] `useStyle` is a string. When non-empty, the name resolves to an entry in `lvglStyles.styles` (or a descendant via `childStyles`) whose `forWidgetType` equals `widget.type`.
- [ ] `localStyles` is present and has shape `{ "definition": { ... } }`.
- [ ] For every `localStyles.definition[<PART>]`, `<PART>` is one of the part names in Section 7 AND is in this widget's `lvgl.parts` list (Section 4).
- [ ] For every `localStyles.definition[<PART>][<STATE>]`, `<STATE>` is in `LVGL_STYLE_STATES` (Section 6: `DEFAULT`, `CHECKED`, `PRESSED`, `CHECKED|PRESSED`, `DISABLED`, `FOCUSED`, `FOCUS_KEY`, `EDITED`, `HOVERED`, `SCROLLED`).
- [ ] For every `localStyles.definition[<PART>][<STATE>][<prop>]`, `<prop>` is a key of `lvglPropertiesMap` (Section 8) AND is defined for the project's `lvglVersion` (i.e. `LVGL_STYLE_PROP_CODES[<prop>][<lvglVersion>]` is not `undefined`).
- [ ] For color-typed style properties (`bg_color`, `text_color`, `border_color`, `arc_color`, `line_color`, `shadow_color`, `outline_color`, `bg_grad_color`, `bg_img_recolor`, `img_recolor`), the value is the `name` of a token in `colors[]` (per the skill's no-hex rule).
- [ ] For `text_font`, the value is either an uppercase built-in font name (matches one of `BUILT_IN_FONTS`) OR the `name` of a `fonts[]` entry.
- [ ] For `bg_img_src`, `arc_img_src`, `mainArcImageSrc`, etc. (bitmap references), the value is the `name` of a `bitmaps[]` entry.
- [ ] `group` is empty OR resolves to an entry in `lvglGroups.groups`. `groupIndex` is a non-negative integer.
- [ ] `eventHandlers` is an array. Each entry has:
  - `eventName` is one of the keys from the `LVGL_EVENTS_V*` table matching the project's `lvglVersion`.
  - `handlerType` is `"action"` when `settings.general.flowSupport === false`; may be `"flow"` only when `flowSupport === true`.
  - When `handlerType === "action"`, `action` is the `name` of an `actions[]` entry.
  - `userData` is an integer.
- [ ] When `type === "LVGLUserWidgetWidget"`: `userWidgetPageName` is the `name` of a `userWidgets[]` entry whose `isUsedAsUserWidget === true`. If the referenced page declares user-properties, `userPropertyValues` must map each property name to a value.
- [ ] **Runtime-override widgets — geometry pinning check.** For `LVGLKeyboardWidget`, `LVGLListWidget`, `LVGLButtonMatrixWidget`, `LVGLDropdownWidget`, `LVGLRollerWidget`, `LVGLTabviewWidget`: `localStyles.definition.MAIN.DEFAULT` should contain all of `align: "DEFAULT"`, `min_width`, `max_width`, `min_height`, `max_height` (the min/max pairs set equal to the desired pixel dimensions) — otherwise the runtime widget will not match the editor canvas's authored geometry.

### 18.4 Named-reference integrity

- [ ] Every `widget.useStyle` resolves to a style whose `forWidgetType` matches the widget's `type`.
- [ ] Every `eventHandler.action` resolves to an `actions[].name`.
- [ ] Every `userWidgetPageName` resolves to a `userWidgets[].name`.
- [ ] Every font reference (`text_font` in any style) resolves to a built-in font OR a `fonts[].name`.
- [ ] Every color reference (any `*_color` in any style) resolves to a `colors[].name`.
- [ ] Every bitmap reference (`image`, `imageReleased`, etc., `bg_img_src`) resolves to a `bitmaps[].name`.
- [ ] Every `lvglStyles.defaultStyles[type]` value resolves to a style whose `forWidgetType === type`.
- [ ] Every variable reference in expression-typed widget properties resolves to a `variables.globalVariables[].name`.
- [ ] No two `userPages[].name` collide; no two `userWidgets[].name` collide; no collision across the two arrays.
- [ ] No two top-level objects (across colors, themes, styles, fonts, bitmaps, actions, variables, groups) share a name within their own collection.

---

**Source-walk dates:** This reference was assembled against a `studio-master` snapshot (the `master` branch of `github.com/eez-open/studio`). Line numbers and source paths in this document refer to that exact tree — re-verify against `github.com/eez-open/studio` `HEAD` before relying on a specific line number for a long-lived change.

Any property or behavior not documented above is **UNVERIFIED** — read the file referenced in that section before authoring against it.
