---
name: freecad
description: Create, modify, inspect, and export FreeCAD 3D CAD models and CAM (Path) jobs by driving a running FreeCAD instance through the `freecad` MCP server. Use whenever a task touches a `.FCStd` file, a PartDesign body/sketch/pad/pocket, a datum plane, an `App::Link` assembly, a spreadsheet-driven parametric model, a STEP/STL/DXF/glTF export, or a CAM job, toolpath, dressup, or posted G-code. Build with PartDesign, never Part booleans; keep every `execute_code` call under ~2 s, because it runs on FreeCAD's GUI thread and a slow call freezes the user's application. Covers the failure modes that present as something else entirely: a modal dialog deadlocking every later call, a blank screenshot caused by a hidden Body Tip, several documents bound to one file so fixes appear to revert, ghost sketches drawn once per link, spreadsheets that drive nothing, pockets that silently cut air, CAM jobs built at the App layer that are inert in the GUI, and modelled dogbones that never survive the toolpath offset.
---

# FreeCAD Automation

Create and modify 3D CAD models, generate exports, and automate FreeCAD operations. Always use the PartDesign workbench for building models — never Part booleans.

## Instructions

You are automating FreeCAD operations. This skill targets **FreeCAD 1.1 or later**.

**Never hardcode the path to the FreeCAD binary.** Resolve it in this order:

1. **Ask the user** where FreeCAD is installed, and offer to save the answer to a
   gitignored local config file.
2. **Accept it as a parameter** when prompting is impossible (CI, cron, non-interactive
   shell).
3. **Read `$FREECAD_BIN`** from the environment.
4. **Fail with a message naming all three.** Never fall back to a default that happens
   to be one developer's install.

Which install the user has matters. A snap or flatpak FreeCAD is **sandboxed** and
cannot read `/tmp` or paths outside the user's home; an AppImage or distro package can.
Confirm before relying on any file path in an export or import.

### MCP Server (Primary Method — ALWAYS try first)

The `freecad` MCP server is configured globally. **Always use MCP tools first.** If the MCP connection fails, **ask the user to start FreeCAD and enable the MCP server** (TrailCurrent Logo workbench → MCP Server button, port 12785) before falling back to headless scripting.

Key MCP tools:
- `execute_code` — Run arbitrary Python in FreeCAD (most powerful)
- `list_documents` / `get_document_info` — Inspect open documents
- `get_object_properties` / `set_object_property` — Read/write object data
- `capture_screenshot` — See the current 3D view (save as PNG, then read the file)
- `fit_view` — Fit camera to all objects
- `add_object` / `remove_object` — Create/delete objects
- `export_object` — Export to STEP/STL/BREP/glTF
- `import_file` — Import external CAD files

The MCP server runs on port 12785 (XML-RPC). The `execute_code` tool runs code on FreeCAD's main thread with these modules pre-imported: `FreeCAD`/`App`, `FreeCADGui`/`Gui`, `Part`, `Mesh`, `Draft`, `Sketcher`, `PartDesign`, `Import`, `BOPTools`.

### Headless Scripting (Fallback ONLY)

Only use headless scripting if the user explicitly says FreeCAD is unavailable or requests a script-based approach:

```bash
# Run a Python script headlessly
"$FREECAD_BIN" -c "exec(open('/tmp/script.py').read())"

# Run inline Python
"$FREECAD_BIN" -c "import FreeCAD; print(FreeCAD.Version())"
```

Note: Headless mode has no GUI — `FreeCADGui`/`Gui` is unavailable, so no screenshots or selection queries.

### MCP XML-RPC Direct Access

When MCP tools are not registered in the session but the server is running, you can call the server directly via Python `xmlrpc.client`. The method name is `execute` (not `execute_code`):

```python
import xmlrpc.client
s = xmlrpc.client.ServerProxy('http://localhost:12785')
result = s.execute("print('hello from FreeCAD')")
print(result)  # {'stdout': 'hello from FreeCAD\n'}
```

Check if the server is up: `curl -s --max-time 2 http://localhost:12785` (returns 501 HTML if running).

Ask the server what it exposes instead of guessing:

```python
s.system.listMethods()          # ['execute', 'ping', 'screenshot', ...]
s.system.methodHelp('screenshot')
```

**`execute()` takes a timeout — pass it instead of chunking.** The default is 60 s,
and hitting it looks like a hang, which tempts you into splitting a job into
artificial pieces. It is a parameter, not a limit:

```python
s.execute(code, 300)            # slow boolean ops, big recomputes, batch pads
```

Set the client socket timeout higher too, or `xmlrpc.client` gives up first:

```python
socket.setdefaulttimeout(320)
```

Long booleans (`Shape.common`, `distToShape`) across dozens of solids and
multi-body PartDesign builds routinely exceed 60 s. Raise the timeout; do not
split the work and do not silently drop coverage to fit.

---

## MCP Failure Modes — read before diagnosing "the MCP is broken"

These cost real hours. Each looks like a different problem than it is. **Fix the
cause; do not work around it** — a workaround here gets re-derived by the next agent
at full cost, which is the whole reason this section exists.

### 0. "FreeCAD is not responding / Force Quit" → YOU froze it with a long `execute_code`

**This is the most common way an agent breaks the user's session, and it keeps
happening.** `execute_code` runs on FreeCAD's **GUI thread**. Anything slow you send
freezes the entire application — the window stops repainting and the desktop offers
the user a *Wait / Force Quit* dialog. From the agent side nothing looks wrong: the
call eventually returns a correct answer. The user, meanwhile, has been staring at a
dead window and may well have killed it, losing unsaved work.

Operations measured on this project that are long enough to trigger it:

| call | cost |
|---|---|
| `Mesh.Mesh.getSegmentsOfType("Cylinder", …)` on a 108 k-facet mesh | **30 s** |
| `getPlanarSegments` on the same mesh | seconds to tens of seconds |
| any Python `for` loop over >10 k facets / vertices | seconds, scales badly |
| `Shape.common` / `distToShape` across many solids | tens of seconds |
| whole-document `recompute()` on a large assembly | tens of seconds |

**Rules:**

- **Keep every `execute_code` call under ~2 s.** If you cannot bound the runtime,
  do not send it.
- **Do not send bulk analysis loops to FreeCAD at all.** Mesh statistics, feature
  extraction, hole-finding, point-cloud fitting and n² interference sweeps are batch
  work; they do not need the GUI and must not run on its thread. Run them in a
  separate process against the source file, or use the scoped MCP tools.
- Prefer the convenience tools (`measure`, `sketch_info`, `get_object_properties`,
  `spreadsheet_get`, `get_errors`) — they are individually cheap by construction.
- Scope recomputes: `doc.recompute([obj1, obj2])`, never bare `doc.recompute()` on a
  big document.
- **A slow call is not "working" — it is a frozen application.** If the user reports
  the not-responding dialog, stop sending code, confirm the app is alive with a
  trivial call such as `list_documents`, and apologise for the freeze rather than
  retrying the same heavy call.

Note this is the opposite failure mode to §1 below: there, a dialog blocks *you*;
here, *you* block the user.

### 1. Every call times out → a modal dialog is blocking the main thread

`execute()` marshals code onto FreeCAD's GUI thread. Any modal dialog raised by
library code spins a nested event loop *on that thread*, so every later call returns
`Execution timed out after 60s` forever. You cannot click it and you cannot dismiss
it over the MCP, because dismissing it needs the thread it is blocking.

The classic trigger is `importDXF` asking permission to download its helper
libraries. **Never set `dxfUseLegacyImporter=True`** — FreeCAD 1.x has a built-in
importer and the legacy path prompts.

Servers from **v2.5.3** guard this automatically: `QMessageBox.*` and
`QDialog/QFileDialog/QInputDialog/QProgressDialog.exec` are stubbed while MCP code
runs, and whatever was suppressed comes back in a `dialogs` key. If you see that key,
**an operation silently took a default branch** — treat it as a warning, not noise.

If you are on an older server and it is already wedged, the only recovery is the user
clicking the dialog. Say so plainly and ask; do not screenshot the desktop and
improvise.

### 2. Blank screenshot → almost always visibility, not the renderer

`saveImage()` works. Before blaming the offscreen framebuffer or the GPU, check what
is actually visible. **In PartDesign the Body's `Tip` feature is what renders**, not
the Body:

```python
body.ViewObject.Visibility = True          # NOT sufficient on its own
body.Tip.ViewObject.Visibility = True      # this is what draws
```

An `App::Link` renders nothing when its source Body's Tip is hidden, and hiding an
`Assembly`/`App::Part` container hides every child link. Turning off `pad_*` objects
blanks the whole model.

`screenshot()` (v2.5.3+) checks the image and warns instead of returning an empty
PNG. Trust that warning — it is usually right and you are usually wrong.

### 2b. "My fix keeps reverting" → several documents are bound to ONE file

FreeCAD will happily hold multiple open documents pointing at the same `.FCStd`. The
Report view announces it, and it is easy to scroll past:

```
Physical path: .../lr4_table_clean.FCStd
  Document: lr4_table_clean (lr4_clean): .../lr4_table_clean.FCStd
  Document: lr4_table_clean (lr4_v2):   .../lr4_table_clean.FCStd
  Document: lr4_table_clean (lr4_v3):   .../lr4_table_clean.FCStd
```

`App.ActiveDocument` and `App.getDocument(name)` then resolve to whichever one FreeCAD
picked, which may not be the one the GUI is showing. You fix visibility in `lr4_v2`, the
user is looking at `lr4_clean`, and your change appears not to have happened. Save from
one and it overwrites the other's version of the file.

Symptom to recognise: **the same fix "coming back" two or three times**, with the user
insisting they did not undo it. Before blaming undo or the user, check:

```python
for d in App.listDocuments().values():
    print(d.Name, d.Label, d.FileName)     # more than one row for a path == this bug
```

`list_documents` shows the same thing. Resolve it by closing the duplicates before
doing any more work; there is no way to merge them.

### 3. Plugin edits have no effect → you edited the wrong copy

The repo working copy and the installed plugin are **different directories**. The
running server loads from FreeCAD's Mod folder. Verify before concluding a fix failed:

```bash
diff -q <repo>/mcp/rpc_server.py "$(ls -d ~/.local/share/FreeCAD/v*/Mod/*LogoFreeCADPlugin)/mcp/rpc_server.py"
```

FreeCAD 1.0+ uses a **versioned** user path — `~/.local/share/FreeCAD/v1-1/Mod`, not
`~/.local/share/FreeCAD/Mod`. Anything looking only at the unversioned path silently
misses a 1.x install.

Reloading a changed module needs a **FreeCAD restart**; toggling the workbench or the
MCP Server button is not enough.

### 4. Exporting DXF — two obvious routes are traps

- `importDXF.export()` needs a helper library it will **prompt to download**.
  That prompt is the deadlock in §1. Never call it.
- `TechDraw.writeDXFView()` ships with FreeCAD and looks like the safe answer.
  Verified on FreeCAD 1.1: it writes a **4 KB file containing zero entities**,
  for sketches *and* for solids. It reports no error.

Use the `export_dxf` MCP tool (v2.5.6+), which writes LINE entities straight
from shape edges, discretising curves. No library, 1:1 geometry, and it counts
the entities before reporting success.

The general lesson: **a file existing is not an export.** Check entity count and
extents, never `os.path.getsize() > 0`.

Two API details that bite when writing geometry out by hand:

- `Edge.discretize()` takes **`Deflection`**, not `Deviation`. `Deviation` raises
  `Part.OCCError: Wrong arguments`. Wrapped in a bare `except` that falls back to
  edge endpoints, this is invisible on straight lines and silently exports every
  arc as **a single chord**. Verify with a known circle: radius 10 at
  `Deflection=0.05` gives 33 points, not 2.
- `DocumentObject` has **no `isError()`** method. Use `obj.isValid()` and
  `obj.State` (a list, e.g. `['Up-to-date']`, `['Touched']`, `['Invalid']`).
  Calling `isError()` raises `AttributeError` on PartDesign features.

### 5. Bump `<version>` in `package.xml` on every plugin change

The FreeCAD Addon Manager compares versions and **ignores anything not newer**, so an
un-bumped fix will not install no matter how many times it is pushed. Semver: patch
for fixes, minor for features. Version only ever goes up. This applies to any edit
under the plugin, including the MCP server that lives inside it.

The Addon Manager pulls from the **GitHub remote**, not the local working copy — a fix
must be committed and pushed before it can be installed that way.

---

## Assemblies of `App::Link` instances — the four traps

The correct structure is: one Body per unique part, instanced into an
`Assembly::AssemblyObject` with `App::Link`. Everything below is what goes wrong with
that structure, and every item cost a full round trip with the user on the LR4 torsion
table (7 bodies, 33 links).

### 1. Ghost sketches and planes — a Body's internals are drawn by EVERY link

An `App::Link` renders the linked Body's children according to **the children's own
visibility**, read from the source. The Body's own `Visibility` is overridden per-link;
its children's is not, and there is no per-instance override.

So one sketch left visible inside `B_CROSS` is drawn 12 times, once at each rib. The
user sees translucent panels standing in every cell and blue outlines threading through
the model, and reasonably concludes the assembly contains junk parts.

**Diagnose in one step — hide the assembly container.** If the 3D view goes *completely
empty*, the ghosts were coming through the links, not from loose geometry parked at the
origin. Do this before theorising; it takes one call and it is decisive.

**The canonical state for every Body** is: Tip visible, every other feature hidden,
every sketch hidden, every Origin child hidden. Audit all of them at once:

```python
for b in [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]:
    shown = [f.Name for f in b.Group
             if f.TypeId.startswith("PartDesign::") and f.ViewObject.Visibility]
    sk  = [f.Name for f in b.Group
           if f.TypeId == "Sketcher::SketchObject" and f.ViewObject.Visibility]
    org = [c.Name for c in b.Origin.OutList if c.ViewObject.Visibility]
    ok = shown == [b.Tip.Name] and not sk and not org
```

**When listing "what is visible", do NOT filter out `App::Origin` / `App::Plane` /
`App::Line` / `App::Point`.** Skipping them as noise is how the big translucent panel
goes unexplained for several rounds — origin planes are exactly what a large light-blue
sheet in the viewport is.

### 2. Space in the 3D view hides the MASTER, blanking every instance

3D-view selection resolves to a **path**, and Space acts on its **last element**:

```python
Gui.Selection.getSelectionEx('', 0)[0].SubElementNames
# ('A_YSPAR_04B.dogbones_LONG_B.',)   <- link . master Tip feature
```

Pressing Space there hides `dogbones_LONG_B` — the Tip of the shared Body — so all 8
links to it go blank at once while `Visibility` on every link still reads `True`. The
tree highlights the link (head of the path), so it looks like the link was selected.

Symptom to recognise: *"I hid one rib and a whole group disappeared."* Confirm with
`hidden links: none` plus a Tip at `False`. The fix is to toggle the **link**:

```python
doc.getObject("A_YSPAR_04B").ViewObject.Visibility = False   # hides exactly one
```

For the user: click the link in the **Model tree**, not in the 3D view, then Space.

**There is no document-side fix. Do not offer one.** All of the following were tested on
FreeCAD 1.1 with `Gui.Selection.addSelection(...)` + `Gui.runCommand("Std_ToggleVisibility")`,
and every one still hid the master:

| configuration tried | result |
|---|---|
| link → Body, same document | master hidden |
| link → Body in a **separate saved document**, real `Assembly::AssemblyObject` | master hidden |
| `LinkClaimChild = True` | master hidden |
| link **array** (`ElementCount=3`, `ShowElement=True`) | master hidden, `VisibilityList` untouched |
| `Std_HideSelection`, `ksuToolsVisibilityToggle` instead of `Std_ToggleVisibility` | master hidden |
| one-level path `"A_XRIB_05."` (what a **tree** click produces) | **link only — correct** |

Only the path depth matters. Rebuilding the bodies does not change it either — a
freshly rebuilt body whose Tip is a `LinearPattern` behaves identically to an old one.

So: joints do **not** fix it, moving masters to a parts file does **not** fix it, and
rebuilding does **not** fix it. Say that plainly. Suggesting a restructure "which is
probably why you haven't hit this before" is a guess, and on this model it was wrong —
run the two-line probe above before claiming any structure change will help.

Same trap in reverse: to hide a skin, hide `A_BOT_SKIN` (the link), never `pad_BOT_SKIN`
(the master Tip).

### 3. Transact view-state fixes, and SAVE them

A visibility cleanup that is not saved is not a fix. A `Ctrl+Z`, File → Revert, or
reload brings every ghost straight back, the user reports the same bug again, and you
burn another round re-diagnosing something you already solved. This happened **three
times** in one session.

```python
doc.openTransaction("Clean body display state")   # one undo step, not 65
...
doc.commitTransaction()
```

Without the transaction the user's undo unpicks the cleanup *partially*, mixing it with
their own edits — which is how a hidden `dogbones_LONG_B` ended up interleaved with the
sketch fix and looked like a new failure.

Leaving work unsaved "so the user can back out" is the wrong default here. Back it up
(`cp x.FCStd x.backup.FCStd`), apply, save, and say what you saved.

### 4. An empty `JointGroup` is not an assembly

`Assembly::AssemblyObject` happily contains an `Assembly::JointGroup` with zero joints,
and every part positioned by a hardcoded `Placement`. It looks assembled and is not.

```python
len(doc.getObject("Joints").Group)        # 0  -> nothing is constrained
[o for o in doc.Objects if "Ground" in o.TypeId]   # [] -> nothing grounded
doc.getObject("A_XRIB_01").ExpressionEngine        # [] -> placement is a typed number
```

Check all three before reporting an assembly as built.

---

## Scripted builds leave the document dirty — add a tidy-up pass

`doc.addObject("Sketcher::SketchObject", ...)` creates the sketch **visible**, and each
`PartDesign::Body` gets an Origin whose planes and axes are visible too. Hand-modelling
in the GUI hides these for you; scripting does not. A generated document therefore ships
with every profile sketch and origin plane switched on — invisible to the author, who is
looking at a single body, and glaring the moment those bodies are instanced.

**End every build script with:**

```python
for o in doc.Objects:
    if o.TypeId in ("Sketcher::SketchObject", "App::Origin", "App::Plane",
                    "App::Line", "App::Point"):
        o.ViewObject.Visibility = False
for b in [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]:
    for f in b.Group:
        if f.TypeId.startswith("PartDesign::"):
            f.ViewObject.Visibility = (f is b.Tip)
```

Fixing the generated file without fixing the generator means it comes back on the next
rebuild. Fix both.

---

## "Parametric" needs checking, not assuming

A document can contain a beautifully aliased `Spreadsheet` that **drives nothing**. On
the LR4 table the sheet had `thickness`, `rib_height`, `core_w`… and every sketch was a
polyline of absolute coordinates held together by `Coincident` constraints alone:

```python
sk.Constraints          # 60 x Coincident, zero dimensional
sk.FullyConstrained     # False
sk.ExpressionEngine     # []
link.ExpressionEngine   # []  -- placements are typed numbers too
```

Changing `thickness` moved nothing. Three cheap checks that catch this:

| check | means |
|---|---|
| `sk.FullyConstrained` is `False` | geometry is floating, not driven |
| `sk.ExpressionEngine == []` | no constraint is bound to the sheet |
| `link.ExpressionEngine == []` | assembly placement is a hardcoded number |

The real test is still the one further down this file: change one cell, `recompute()`,
confirm geometry moved.

**Verify derived formulas against measured geometry before building on them.** Reading
`Radius : 3.175, Position : (20.2339, 39.0299, 0)` out of the existing dogbone sketch
gave `dog_off = cutter_r * (1 - 1/sqrt(2))` = 0.9299359697, matching the modelled
0.9299 exactly — proof the formula was right, obtained without trusting any arithmetic
of mine.

### MCP tool gap: there is no sketch-constraint tool

`sketch_add_polyline` adds **coincident constraints only**. `set_expression` binds an
*existing* constraint but cannot create one. So dimensional constraints — the thing that
actually makes a sketch parametric — require `execute_code` or the GUI. Say this to the
user rather than quietly producing a sketch that looks parametric and is not.

What *is* achievable with the convenience tools alone: grid/repetition parametrics via
`partdesign_pattern` with `Occurrences` and `Length` bound by `set_expression` to sheet
aliases.

### Three silent failures when building a slotted part

All three report success. All three were caught by **one volume comparison** against the
uncut blank, and by nothing else — `get_errors()` said "document is clean" throughout.

**A pocket from a sketch on the pad's base plane cuts into thin air.** Sketch on
`XY_Plane`, pad `0 → +Z`; a Pocket from that same sketch defaults to `-Z`, away from the
material. It removes **nothing**, raises no error, and `valid: True`. Cut both ways
instead — but use the *current* property, not the deprecated one:

```python
p.SideType = "Symmetric"        # enum: 'One side', 'Two sides', 'Symmetric'
```

**`Midplane` is deprecated in FreeCAD 1.1** and is now an alias for `SideType` on
`FeatureExtrude`. Setting it works, but every recompute logs a deprecation warning, and
the shim maps an explicit `Midplane=False` to `SideType='One side'` — the setting that
cuts nothing. After the mapping the two disagree (`Midplane=False` while
`SideType='Symmetric'`); **`SideType` is authoritative**, so read that, not `Midplane`,
when checking whether a cut is configured correctly.

The MCP's `partdesign_feature` sets `midplane` explicitly on every call, so it always
trips this. Create the pocket with the tool, then set `SideType` directly afterwards.

**`partdesign_pattern` appends the pattern at the END of the Body and does not move
`Tip`.** After patterning, `Tip` still points at whatever feature was current, so every
patterned instance silently drops out of the result shape. Symptom: the body looks
under-cut by exactly the patterned features. Always re-assert the Tip:

```python
b.Tip = doc.getObject("LinearPattern")   # last feature in the real chain
```

**A spreadsheet edit does not touch its dependents over the MCP.** `recompute` returns
`Recomputed 0 objects` and the model does not move, which reads as "the binding is
broken" when the binding is fine. Force it:

```python
for o in doc.Objects: o.touch()
doc.recompute()
```

The check that catches all of it, and the one to run after any slotted/pocketed build:

```python
blank = L * W * T                                   # the uncut stock
print("removed %.1f mm3" % (blank - b.Shape.Volume))
# and prove the cuts landed where intended, not merely that volume left:
for x in slot_centres:
    assert not sh.isInside(App.Vector(x, y_mid, t/2), 1e-6, True), "slot not cut"
for x in web_centres:
    assert sh.isInside(App.Vector(x, y_mid, t/2), 1e-6, True), "web missing"
```

`removed == 0.0` exactly, or a volume that equals `L*W*T` to the decimal, means no cut
happened. `isInside` at the intended centres is what distinguishes "material was
removed" from "material was removed **in the right places**".

---

## Use the MCP's convenience tools; reserve `execute_code` for real gaps

`execute_code` is a legitimate MCP tool, but reaching for it to poke around — dumping
object lists, reading properties, checking state — reads to the user as hacking rather
than working, especially when `get_object_properties`, `sketch_info`, `get_errors`,
`spreadsheet_get`, `set_visibility` and `list_documents` answer the same question.

Prefer, in order:

1. The dedicated tool (`set_visibility` handles Tip/Link/container traps for you, and
   takes a comma-separated list, so 65 toggles is 3 calls).
2. `execute_code` where **no tool exists** — Sketcher constraints, joint creation,
   multi-object audits.

Also: reading the project's build script with `grep`/`sed` when the live document can
answer the question is the same mistake. Ask the model, not the source.

Minor API note: `App.Document` has **no `.Modified`** attribute; checking it raises
`AttributeError`.

---

## CRITICAL: Confirm Orientation and Requirements BEFORE Building

**Never start building a CAD model without first confirming the coordinate orientation and key design decisions with the user.** This avoids costly rebuild cycles.

Before any model build:
1. **Navigate to FRONT view** (`Gui.activeDocument().activeView().viewFront()`) and confirm with the user what should be visible
2. **Confirm the coordinate system**: which plane is the main face, which axis is depth, which way is up
3. **Confirm design requirements**: wall thickness, open/closed faces, faceplate, mounting method, cable openings
4. **Only then start building**

FreeCAD standard orientation:
- **FRONT view** looks along **-Y** (XZ plane visible)
- **TOP view** looks along **-Z** (XY plane visible)
- **RIGHT view** looks along **-X** (YZ plane visible)

For a display/screen device oriented naturally (screen facing the user):
- Screen face on **XZ plane** at Y=0, facing **-Y** (toward FRONT)
- Depth along **+Y** (toward BACK)
- Width along **X**, height along **Z** (up)

---

## Verify with the model, not with your own arithmetic

You computed the numbers, so re-deriving them proves nothing. Ask FreeCAD what it
actually built. These MCP tools exist for it and are the fastest way to catch a
real defect:

| tool | catches |
|---|---|
| `measure(a, b)` | wrong size, gap where parts should mate, unintended overlap |
| `check_interference("*")` | parts occupying the same space anywhere in an assembly |
| `get_errors()` | features that failed to recompute — the tree holds broken features silently |
| `capture_screenshot` | geometry that is missing rather than merely misplaced |

In this project's build, measuring the assembly caught a part hanging 0.75"
past the table edge that every placement number said was correct, and an
interference sweep confirmed 108 egg-crate joints mated with 0 gap and 0
overlap. Neither was visible in the code.

Two habits that follow from it:

- **Assert the invariant, not the output.** "sum of parts == overall dimension"
  and "intersection volume == 0" survive a redesign; a hardcoded 66.125 does not.
- **Distrust your own success message.** Before reporting a step done, read back
  what landed: entity counts, bounding boxes, `get_errors()`. Several times in
  this project a step printed success while producing nothing — a blank
  screenshot, an empty DXF, a hidden assembly.

---

## CRITICAL: Parametric first — never bake numbers into the model

FreeCAD's API *is* Python, so scripting is not the problem. What matters is what
the script leaves behind:

- **Wrong:** compute values in Python and write literals into properties. The
  result is dead geometry that only the script's author can change.
- **Right:** use Python to build **native parametric objects** — a Spreadsheet of
  aliased inputs, properties bound by expression, sketch constraints, PartDesign
  patterns. The model then recomputes itself and the user drives it from the GUI.

Put every design input in a Spreadsheet with aliases, derive the rest with
spreadsheet formulas, and bind geometry to the aliases:

```python
sh = doc.addObject("Spreadsheet::Sheet", "Design")
sh.set("B4", "19.05 mm"); sh.setAlias("B4", "thickness")
sh.set("B5", "=thickness + slot_clear"); sh.setAlias("B5", "slot_w")   # derived
pad.setExpression("Length", "Design.thickness")                        # bound
doc.recompute()
```

`sh.set()` takes **strings only** — `sh.set("B4", 5)` raises `TypeError`. Use
`str(value)`. Quantities carry units (`"19.05 mm"`, `"3 in"`); formulas start
with `=` and reference other aliases by name.

Test it the way a user would: change one cell, `recompute()`, and confirm the
geometry moved. If nothing changed, the model is not parametric — it just looks
like it is.

Use the MCP tools `spreadsheet_set`, `spreadsheet_get`, `set_expression` and
`clear_expression` (v2.5.5+) rather than hand-rolling this through `execute_code`.

Repetition belongs to `PartDesign::LinearPattern` / `PolarPattern` / `Mirrored`,
not to a Python loop that creates N independent bodies — unless the parts really
are separately manufactured, in which case separate Bodies are correct.

---

## CRITICAL: Always Use PartDesign Workbench

**Never use Part workbench booleans** (`Part::Cut`, `Part::Fuse`, `Part::Box`, etc.) for building models. Always use the PartDesign workbench (`PartDesign::Body`, `Sketcher::SketchObject`, `PartDesign::Pad`, `PartDesign::Pocket`, etc.).

Why: PartDesign creates a proper parametric feature tree that users can easily edit. Part booleans create a tangled dependency graph that is fragile and hard to modify.

### PartDesign Feature Tree Pattern

Every model follows this structure:

```
PartDesign::Body
├── Sketcher::SketchObject  →  PartDesign::Pad      (base shape)
├── Sketcher::SketchObject  →  PartDesign::Pocket    (hollowing, cuts)
├── Sketcher::SketchObject  →  PartDesign::Pad       (additive features)
├── PartDesign::Plane        →  Sketch → Pocket      (side-face cuts via datum planes)
├── PartDesign::Mirrored                              (symmetry)
└── PartDesign::Fillet / Chamfer                      (edge treatment)
```

For multi-part designs (e.g., enclosure + cover), use **separate PartDesign::Body objects** in the same document.

---

## PartDesign Recipes

### Creating a Body and Base Pad

```python
doc = App.ActiveDocument or App.newDocument("MyModel")

body = doc.addObject("PartDesign::Body", "Enclosure")

# Sketch on XY origin plane
sk = doc.addObject("Sketcher::SketchObject", "sk_Base")
body.addObject(sk)
sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
sk.MapMode = "FlatFace"

# Draw a rectangle centered at origin
L, W = 100.0, 50.0
pts = [(-L/2, -W/2), (L/2, -W/2), (L/2, W/2), (-L/2, W/2)]
for i in range(4):
    x1, y1 = pts[i]
    x2, y2 = pts[(i+1) % 4]
    sk.addGeometry(Part.LineSegment(App.Vector(x1, y1, 0), App.Vector(x2, y2, 0)))
for i in range(4):
    sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i+1)%4, 1))

pad = doc.addObject("PartDesign::Pad", "BasePad")
body.addObject(pad)
pad.Profile = sk
pad.Length = 25.0
doc.recompute()
```

### Sketch Offset from Origin Plane

Attach sketches to origin planes (XY, XZ, YZ) with Z offset — never reference face names like "Face6" which are fragile and unpredictable.

```python
sk = doc.addObject("Sketcher::SketchObject", "sk_TopProfile")
body.addObject(sk)
sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
sk.MapMode = "FlatFace"
# Offset 25mm above XY plane
sk.AttachmentOffset = App.Placement(App.Vector(0, 0, 25), App.Rotation())
```

### Pocketing (Hollowing, Cuts)

```python
# Pocket sketch on XY_Plane at Z=25 cuts downward into solid
pocket = doc.addObject("PartDesign::Pocket", "HollowPocket")
body.addObject(pocket)
pocket.Profile = sk_hollow
pocket.Length = 23.0  # depth
doc.recompute()

# Through-all pocket
pocket.Type = 1  # 0 = Dimension, 1 = Through All
```

### Ring Profiles (Ledge, Gasket Groove)

Use two concentric rectangles in one sketch to create a ring pocket:

```python
sk = doc.addObject("Sketcher::SketchObject", "sk_Ledge")
body.addObject(sk)
sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
sk.MapMode = "FlatFace"
sk.AttachmentOffset = App.Placement(App.Vector(0, 0, H), App.Rotation())

# Outer rectangle (indices 0-3)
for i in range(4):
    sk.addGeometry(Part.LineSegment(...))  # outer points
for i in range(4):
    sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i+1)%4, 1))

# Inner rectangle (indices 4-7)
for i in range(4):
    sk.addGeometry(Part.LineSegment(...))  # inner points
for i in range(4):
    sk.addConstraint(Sketcher.Constraint("Coincident", i+4, 2, ((i+1)%4)+4, 1))
```

### Circles (Bosses, Holes)

```python
sk.addGeometry(Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), radius))
```

Multiple circles in one sketch → one Pad/Pocket creates all at once.

---

## Datum Planes for Side-Face Features

**This is the most error-prone area. Follow these rules exactly.**

Datum planes let you sketch on side faces without fragile face references. The critical lesson: **attachment offset local Z = the plane's normal direction**, not the world axis you might expect.

### Origin Plane Normals

| Plane | Normal Direction | To reach face at... | Offset |
|-------|-----------------|--------------------|---------|
| XZ_Plane | -Y (!) | Y = -25 | `App.Vector(0, 0, +25)` |
| XZ_Plane | -Y | Y = +25 | `App.Vector(0, 0, -25)` |
| YZ_Plane | -X (!) | X = -50 | `App.Vector(0, 0, +50)` |
| YZ_Plane | -X | X = +50 | `App.Vector(0, 0, -50)` |

**The sign is counterintuitive.** The XZ_Plane normal is -Y, so a positive local-Z offset moves in the -Y direction. Always verify with:

```python
dp = doc.addObject("PartDesign::Plane", "dp_Front")
body.addObject(dp)
dp.AttachmentSupport = [(doc.getObject("XZ_Plane"), "")]
dp.MapMode = "FlatFace"
dp.AttachmentOffset = App.Placement(App.Vector(0, 0, offset), App.Rotation())
doc.recompute()
print("Datum plane at:", dp.Placement.Base)  # Verify world position!
```

If the position is wrong, flip the offset sign.

### Sketch Coordinate Mapping on Datum Planes

| Datum plane derived from | Sketch local X | Sketch local Y |
|--------------------------|---------------|---------------|
| XZ_Plane | World X | World Z |
| YZ_Plane | World Y | World Z |

### Pocket Direction on Datum Planes

When a sketch is on the body's outer surface, the default pocket direction goes **outward** (away from material). You almost always need `Reversed = True` to cut inward:

```python
pocket = doc.addObject("PartDesign::Pocket", "SideVentPocket")
body.addObject(pocket)
pocket.Profile = sk_side
pocket.Length = wall_thickness + 0.1  # through the wall
pocket.Reversed = True  # CUT INWARD, not outward
doc.recompute()
```

### Complete Datum Plane Example (Side Vents)

```python
L, W, wall = 100.0, 50.0, 2.0

# Datum plane at front face (Y = -W/2, centered box)
dp_front = doc.addObject("PartDesign::Plane", "dp_Front")
body.addObject(dp_front)
dp_front.AttachmentSupport = [(doc.getObject("XZ_Plane"), "")]
dp_front.MapMode = "FlatFace"
dp_front.AttachmentOffset = App.Placement(App.Vector(0, 0, W/2), App.Rotation())
doc.recompute()
assert abs(dp_front.Placement.Base.y - (-W/2)) < 0.01, "Datum plane position wrong!"

# Sketch vent slots (local X = world X, local Y = world Z)
sk = doc.addObject("Sketcher::SketchObject", "sk_FrontVents")
body.addObject(sk)
sk.AttachmentSupport = [(dp_front, "")]
sk.MapMode = "FlatFace"

# Draw rectangles for each vent slot...
# (x positions along length, y positions = Z height on wall)

# Pocket inward through wall
pk = doc.addObject("PartDesign::Pocket", "FrontVentPocket")
body.addObject(pk)
pk.Profile = sk
pk.Length = wall + 0.1
pk.Reversed = True  # ALWAYS reverse for surface-mounted datum plane sketches
doc.recompute()

# Hide datum plane
dp_front.ViewObject.Visibility = False
```

---

## Mirrored Features (Symmetry)

Use `PartDesign::Mirrored` to replicate features across a plane. Requires the model to be **centered at the origin** so origin planes serve as mirror planes.

```python
mirror = doc.addObject("PartDesign::Mirrored", "MirrorFrontBack")
body.addObject(mirror)
mirror.Originals = [doc.getObject("FrontVentPocket")]  # note: Originals (plural), list
mirror.MirrorPlane = (doc.getObject("XZ_Plane"), [""])
doc.recompute()
```

| Mirror plane | Mirrors across |
|-------------|---------------|
| XZ_Plane | Front ↔ Back (Y axis) |
| YZ_Plane | Left ↔ Right (X axis) |
| XY_Plane | Top ↔ Bottom (Z axis) |

---

## Multi-Body Assemblies

Use separate bodies for parts that are manufactured separately (e.g., enclosure + cover):

```python
body_enclosure = doc.addObject("PartDesign::Body", "Enclosure")
# ... build enclosure features ...

body_cover = doc.addObject("PartDesign::Body", "Cover")
# ... build cover features ...

# Color them differently for visual distinction
body_cover.ViewObject.ShapeColor = (0.6, 0.7, 0.8)
```

Screw holes in both bodies must use the **same corner coordinates** so they align.

---

## Extracting Colored Sub-Faces for Blender (glTF Placement Gotcha)

When extracting specific colored faces from a Part::Feature (e.g., a logo inlay on a cover, or rubber grommets on a Deutsch connector) to import into Blender as a separate mesh with its own material, you MUST account for the source shape's Placement:

```python
src = doc.getObject("Part__Feature005")   # e.g., DTM4 connector base
faces = src.Shape.Faces                    # POSITIONED faces (src.Placement baked in)
dc = src.ViewObject.DiffuseColor
target_color = (1.0, 0.667, 0.498)
idx = [i for i, c in enumerate(dc) if tuple(round(x,3) for x in c[:3]) == target_color]

comp = Part.makeCompound([faces[i] for i in idx])

# ❌ WRONG — double transform, src.Placement is already baked into comp,
#           and applying link.Placement on top lands the shape at 2× the offset
bad = comp.transformed(link.Placement.toMatrix())

# ✅ RIGHT — un-apply src.Placement first, then apply link.Placement
local = comp.transformed(src.Placement.inverse().toMatrix())
world = local.transformed(link.Placement.toMatrix())

feat = doc.addObject("Part::Feature", "ExtractedFaces")
feat.Shape = world
feat.ViewObject.ShapeColor = target_color
doc.recompute()
ImportGui.export([feat], "/tmp/extract.glb")
doc.removeObject("ExtractedFaces")
```

**Why this matters:** `src.Shape` returns the shape with `src.Placement` already applied. Sources imported from STEP (especially Deutsch connectors) often have non-identity Placements. Symptoms of getting it wrong:
- Extracted mesh lands at Z = +170 mm or −167 mm instead of +11 mm
- The wrong-positioned mesh is often offscreen so you don't notice until the user complains
- Even worse if the source has a rotation — axes get swapped (e.g. local Y becomes world Z)

**Alternative (usually better):** Don't extract at all. If the containing object is already in Blender at the correct world position, add the target material as a second slot on the existing mesh and use the Blender side's `mesh.polygons[i].material_index` to reassign individual faces by their world-space bounding box. See the `/blender-automation` skill for the recipe.

**Blender cannot read `/tmp`** when installed as snap/flatpak. Always `cp` exported files somewhere under `$HOME` before Blender imports them.

---

## View Control (MCP only)

```python
# Standard views
Gui.activeDocument().activeView().viewIsometric()
Gui.activeDocument().activeView().viewFront()
Gui.activeDocument().activeView().viewTop()

# Fit all
Gui.SendMsgToActiveView("ViewFit")
```

---

## Common Operations

**Open and inspect a model:**
```python
doc = App.openDocument("model.FCStd")
for obj in doc.Objects:
    print(f"  {obj.Name} ({obj.TypeId})")
    if hasattr(obj, 'Shape') and obj.Shape and not obj.Shape.isNull():
        print(f"    Volume: {obj.Shape.Volume:.2f} mm³")
        print(f"    BoundBox: {obj.Shape.BoundBox}")
```

**Export to multiple formats:**
```python
import Part as _Part
import Mesh

# STEP (precision CAD exchange)
_Part.export([doc.getObject("Enclosure")], "output.step")

# STL (3D printing)
Mesh.export([doc.getObject("Enclosure")], "output.stl")
```

**Batch export all FCStd files to STEP:**
```python
import FreeCAD, Part, glob, os

input_dir = "Product/<ProductName>/CAD/"
output_dir = "Product/<ProductName>/CAD/exports/"
os.makedirs(output_dir, exist_ok=True)

for fcstd in glob.glob(os.path.join(input_dir, "*.FCStd")):
    name = os.path.splitext(os.path.basename(fcstd))[0]
    doc = FreeCAD.openDocument(fcstd)
    exportable = [obj for obj in doc.Objects if hasattr(obj, 'Shape')]
    if exportable:
        Part.export(exportable, os.path.join(output_dir, f"{name}.step"))
    FreeCAD.closeDocument(doc.Name)
```

---

## TrailCurrent-Specific Use Cases

- **Product enclosures**: 3D printable cases for ESP32 boards, sensor modules
- **Business cards**: 3D embossed business cards (existing .FCStd and .3mf in Print/BusinessCards/)
- **Mounting brackets**: PCB mounting plates, DIN rail adapters
- **Connector housings**: Custom connector shells for CAN bus, power
- **Trade show display parts**: Product holder stands, demo fixtures

## Example file placement convention (adapt to your own repo layout)

- Product-specific CAD files → `Product/<ProductName>/CAD/`
- 3D printable items → `Print/Packaging/` or `Print/BusinessCards/`
- Merch-related 3D files → `Merch/<Category>/Designs/`
- Mockup renders → `Brand/Graphics/Source/Mockups/`
- Exported STL/STEP for manufacturing → alongside the source .FCStd or in an `exports/` subfolder

---

## CAM (Path) workbench — the App-layer `Create()` builds an INERT job

**This is the single biggest trap in CAM scripting and it produces a job that
passes every check you think to run.** `integrityCheck()` returns `True`,
`Operations`/`Model`/`Stock`/`SetupSheet`/`Tools` all exist and are populated,
toolpaths generate, and posting from Python emits correct G-code. In the GUI the
same job is unusable: nothing nests under it, there is no tool list, the ops draw
no toolpath, and CAM → Post Process cannot drive it.

The cause is one line. **Tree nesting comes from `claimChildren`, which lives on
the ViewProvider, and the App-layer `Create()` never attaches one.** Compare
`Mod/CAM/Path/Main/Gui/Job.py`:

```python
obj = PathJob.Create("Job", base, template)          # App layer: no ViewProvider
obj.ViewObject.Proxy = ViewProvider(obj.ViewObject)  # <- the GUI layer adds this
obj.ViewObject.addExtension("Gui::ViewProviderGroupExtensionPython")
```

So in a GUI session **always build CAM through the `*.Gui.*` layer**:

```python
import Path.Main.Gui.Job as PathJobGui
job = PathJobGui.Create(parts, None, openTaskPanel=False)   # NOT Path.Main.Job.Create
```

`openTaskPanel` defaults to **True** and opens a modal task panel — over the MCP
that is the §1 deadlock, every later call times out forever. Always pass `False`.

Operations need the same treatment, and their ViewProvider needs the *command's*
resources object (`CommandPathOp.__init__` stores it as `self.res`):

```python
from Path.Op import Profile as PProfile
import Path.Op.Gui.Base as PathOpGui
import Path.Op.Gui.Profile as ProfileGui
op = PProfile.Create("OP_Name", parentJob=job)
op.ViewObject.Proxy = PathOpGui.ViewProvider(op.ViewObject, ProfileGui.Command.res)
```

The one-line probe that catches all of it before you build anything else:

```python
print(job.ViewObject.Proxy, op.ViewObject.Proxy)   # None, None == inert job
```

### Never share one ToolBit between two Jobs

`Tool/Gui/Controller.py` → `claimChildren` returns `[obj.Tool]`, and **the FreeCAD
tree can claim an object only once**. Point two jobs' tool controllers at the same
ToolBit and the bit appears under one job and vanishes from the other, taking the
tool list with it.

Each Job already creates its own default TC — `Main/Job.py`, in `__init__`:
`self.addToolController(PathToolController.Create())`. **Retune that one; do not
delete it and substitute your own.** Deleting a TC does *not* delete its ToolBit,
and a ToolBit carries a whole PartDesign Body (Origin, planes, sketch,
Revolution, PropertyBag). Two delete-and-replace cycles left **22 orphaned objects
at the tree root**.

```python
tc  = job.Tools.Group[0]        # the job's own default controller
bit = tc.Tool
bit.Diameter = "6.35 mm"; bit.Flutes = 2      # retune in place
```

ToolBit properties **do not stick before `attach_to_doc()`**. `ToolBit.from_shape_id()`
plus `set_diameter()`/`set_property()` silently yields a 5 mm 4-flute default. Set
them on the *document object* afterwards and read them back.

### Auditing the tree from Python

The tree is not `doc.Objects`. Resolve it, or you will not see the orphans:

```python
claimed = {}
for o in doc.Objects:
    kids = []
    vp = getattr(getattr(o, "ViewObject", None), "Proxy", None)
    if vp is not None and hasattr(vp, "claimChildren"):
        kids += [c.Name for c in vp.claimChildren() if c]
    if hasattr(o, "Group"):                 # DocumentObjectGroup AND PartDesign::Body
        kids += [c.Name for c in o.Group]
    if o.TypeId == "App::Origin":           # Origin owns its planes/axes in C++
        kids += [c.Name for c in o.OutList]
    for k in kids:
        claimed.setdefault(k, []).append(o.Name)
top   = [o.Name for o in doc.Objects if o.Name not in claimed]
multi = {k: v for k, v in claimed.items() if len(v) > 1}   # double-claimed == broken tree
```

Only Python `claimChildren` is visible this way — **PartDesign::Body claims its
children in C++**, so a naive version reports ~22 false orphans (the tool bits'
sketches, planes and origins). Include `hasattr(o, "Group")` before concluding
anything is loose.

### `post.export()` returns the G-code — it does not write the file

`job.PostProcessorOutputFile` is *not* honoured by the Python API; only the GUI
command writes it. `export()` hands back `[(name, gcode)]` and reports success
having written nothing.

```python
name, gcode = PP.PostProcessorFactory.get_post_processor(job, job.PostProcessor).export()[0]
open(path, "w").write(gcode)
```

Then verify the **file**, per this file's standing rule that existence is not an
export: line count, `G21` present and `G20` absent, feeds, min Z, and XY extents
against the machine envelope. A silently inch-mode or clamped-depth file looks
identical at the filesystem level.

**`--no-show-editor` in `PostProcessorArgs` cuts both ways.** You need it for
scripted posting — the G-code editor is modal and would wedge the MCP (§1). But it
also makes the user's **Post Process** button completely silent: no editor, no
dialog, no confirmation, just a file appearing. The user reasonably reports "it
didn't output anything." Hand the job over with the flag **removed** so clicking
Post shows the editor, and re-add it only while you are posting from Python.

When a user says posting produced nothing, check the file's own header before
theorising — the post stamps its own run time, which distinguishes their click
from your last write:

```
(Output Time:2026-09-06 16:22:09.089659)
```

### Assorted CAM API facts that cost a call each

| symptom | cause |
|---|---|
| `Property 'StepDown' not found` on SetupSheet | it is `StepDownExpression` (also `FinalDepthExpression`, `StartDepthExpression`) |
| feeds look 60× wrong | velocities store as **mm/s**; a chipload formula needs `feed * 60s / (rpm * flutes)` |
| spreadsheet edit moves nothing | `for o in doc.Objects: o.touch()` then `recompute()` — same trap as elsewhere in this file |
| stock ignores your box | assign `job.Stock = new` *before* `removeObject(old.Name)` |

`FinalDepth` below the stock bottom is legal and is how you add a spoilboard
overcut. Bind it — `op.setExpression("FinalDepth", "-CAM.cut_depth")` — then prove
it is live by changing the cell and re-reading the path's minimum Z, not by
re-reading the property.

### Re-nesting: a Job's Model clones do NOT track the source objects

`Job.Create` fills `job.Model` with `Draft.clone()` objects, and a Draft clone holds
its **own** Placement, captured at creation. Move the source `Part::Feature` to
re-nest a sheet and the clone stays exactly where it was — so the toolpath does not
move. The source object's `BoundBox` reports the new position, the printout looks
right, and the G-code is unchanged.

This is nasty because the obvious verification lies to you: you check the parts you
moved, not the clones the job actually cuts.

```python
for j in PathJob.Instances():
    for c in j.Model.Group:
        s = c.Objects[0]                      # Draft clone -> its source
        c.Placement = App.Placement(s.Placement.Base, s.Placement.Rotation)
    for o in j.Operations.Group: o.touch()
doc.recompute()
```

**Verify against the toolpath extents, never the source objects** — and when two
jobs share one sheet, assert they do not overlap:

```python
a, b = extents(jobCoupon), extents(jobRibs)   # from the PATH commands
assert a[3] < b[2], "coupon and ribs collide on the shared sheet"
```

### Re-audit EVERY job after every change, not just the one you are editing

On a multi-job document an operation can go missing without any error: the job still
recomputes, `integrityCheck()` still returns `True`, and posting still emits a valid
file — containing only the operations that remain. On this project `OP_Sheet2_Profile`
vanished at some point and was not noticed for several rounds, because attention had
moved to a different job and only that one was being re-checked. A re-post at that
moment would have written a sheet file containing a scoring pass and nothing else.

Cheap standing check after any structural edit:

```python
for j in PathJob.Instances():
    cut = [o for o in j.Operations.Group if hasattr(o, "Side")]
    assert cut, "%s has no cutting operation" % j.Name
    print(j.Name, len(j.Model.Group), "models", [o.Name for o in j.Operations.Group])
```

### `Shape.translate()` writes the PLACEMENT — it does not move the geometry

Nesting parts for CAM is where this bites. You section a part, translate it to the
origin, then set the object's Placement to its nest position — and the translation
silently evaporates, because you just overwrote the very thing that held it.

```python
cut = solid.common(box)            # geometry sits at x 1440..1739
cut.translate(App.Vector(-1440, 0, 0))   # sets Placement, geometry UNCHANGED
f.Shape = cut                      # f.Placement is now (-1440, 0, 0)
f.Placement = nest_placement       # <- discards it; part lands 1440 mm away
```

Symptom: one part in the nest is exactly `x0` out of position and the stock looks
far too small. `BoundBox` will not warn you — it reports the *located* shape, so
the source object measures correctly right up until you overwrite its Placement.

Fix by **composing**, not baking — a matrix transform can convert arcs to
B-splines, which silently destroys dogbones:

```python
f.Placement = (App.Placement(pos, rot)
               .multiply(App.Placement(App.Vector(-x0, 0, 0), App.Rotation())))
```

Assert the nest is inside the stock before building the job; it costs one line and
catches this immediately:

```python
assert all(0 < b.XMin and b.XMax < W and 0 < b.YMin and b.YMax < L
           for b in [p.Shape.BoundBox for p in placed])
```

### Holding tabs: `Path.Dressup.Tags`, and the two things that silently defeat them

Use the **App-layer** create and attach the view provider yourself —
`Path.Dressup.Gui.Tags.Create()` ends with `setEdit()`, which opens a modal task
panel and wedges the MCP (§1):

```python
import Path.Dressup.Tags as DTags
from Path.Dressup.Gui.Tags import PathDressupTagViewProvider
d = DTags.Create(op, "DressupTags")          # also adds itself to the Job's Operations
d.ViewObject.Proxy = PathDressupTagViewProvider(d.ViewObject)   # no setEdit
```

**1. One dressup needs one closed contour.** A Profile op covering several models
gives `pathData.baseWire is None`, `supportsTagGeneration()` returns `False`, and
`generateTags()` silently produces **zero** positions — no error. Split into one
Profile op per part (`op.Base = [(clone, ("Face4",))]`, the bottom face) and put a
dressup on each.

**2. Tab height is measured up from `FinalDepth`, so a spoilboard overcut eats it.**
With `FinalDepth = -(thickness + cut_over)`, a tab of height `h` leaves
`h - cut_over` of real material. Height 3 mm with a 2 mm overcut leaves 1 mm; height
2 mm leaves nothing at all and the "tabs" are air. Bind it:

```python
d.setExpression("Height", "CAM.tab_h")       # tab_h = cut_over + tab_hold
```

Verify against the stock, not the property — assert no cutting move goes below the
tab top inside a tab window, and that the plateau Z actually appears in the path:

```python
expect_top = -(cut_depth - tab_h)            # e.g. -16.05
assert expect_top in [round(z,3) for z in cut_levels]
```

Auto-generated positions distribute along the whole wire and **will land inside
slots and notches**. On a slotted part, place them yourself on the solid long edge
— find it as the longest straight edge of the bottom face's outer wire, since the
slotted side is chopped into short segments:

```python
longest = max([e for e in wire.Edges if e.Curve.TypeId == 'Part::GeomLine'],
              key=lambda e: e.Length)
```

Expect `Width` and `Height` defaults to be nonsense for your job (they scale off the
path — 38 mm wide, half the cut depth), and a third feedrate to appear in the posted
G-code: the tab ramps run slower than the cutting feed. Count them as
`tabs × affected_passes × 2`.

### MODELLED DOGBONES DO NOT SURVIVE THE OFFSET — always add a dressup

**This one scrapped real material.** A dogbone arc whose radius equals the tool
radius is *geometrically* perfect — the r-offset of that arc is exactly its centre,
so the tool centre should pass through it. But the offset is computed by OCC, and a
feature that collapses to zero length gets **dropped**. The modelled dogbones simply
never appear in the toolpath, every corner is cut as a plain fillet of radius r, and
nothing anywhere reports a problem: no error, valid path, correct-looking preview.

Symptom on the bench: *"the dogbones did not cut"* and parts that will not seat. On
this project the measured error was **3.150 mm** proud per joint.

**Model the corner SQUARE and let CAM add the bone.** A dogbone modelled into the
part is geometry the tool cannot produce — and worse, it is geometry the *simulator*
expects, so the simulation shows the target with big round lobes the toolpath never
visits and the result looks inexplicably wrong. Strip every dogbone and relief from
the CAM geometry (`arcs == 0` on every nest part is the check) and add the dressup.

Derive the square version inside the CAM document; do not edit the design model:

```python
for fn in dogbone_features: src.getObject(fn).Suppressed = True    # then restore in a finally:
```

Watch for **no-op features**: on this project `dogbones_LONG_A/B` were Pocket
features that removed exactly 0 mm³ — the reliefs were baked into the profile
*sketch*, so suppressing the feature squared nothing. Always confirm suppression
changed the volume; if it did not, the geometry lives somewhere else.

**Never rely on modelled dogbone geometry.** Add the dressup to every cutting op:

```python
import Path.Dressup.Gui.DogboneII as DB      # Gui variant: attaches the VP, no setEdit
d = DB.Create(op, "DressupDogbone")
d.Style = "Dogbone"; d.Incision = "adaptive"; d.Side = "Left"
```

It also **rescues geometry whose relief is too small to cut** — a 0.160" square
T-bone that a 1/4" endmill cannot enter still comes out correct, because the dressup
bones the toolpath corner regardless of what the model contains. That can be cheaper
than fixing the CAD.

Two things a dressup breaks silently, both of which post a *valid but wrong* file:

- **It reorders `job.Operations.Group`.** `addOperation(obj, before=base)` inserts by
  index, so a scoring pass ended up *after* the cut and an M0 stop ended up first —
  the G-code posted fine with the stop at line 13. Re-assert the whole group
  explicitly after adding any dressup, and assert the posted operation order:
  `re.findall(r"\(Begin operation: (.*?)\)", gcode)`.
- **It can drop an unrelated operation entirely** (see the re-audit note above).

### `op.Base` face references decay to `?FaceN` when geometry changes

Scoping an op to one model (`op.Base = [(clone, ("Face4",))]`) stores a *topological
name*. Change the underlying geometry and FreeCAD rewrites it to `?Face4` — the
reference no longer resolves, the op goes `['Touched','Invalid']`, and its Path goes
stale rather than erroring. Nothing in the posted file announces it.

```python
for b, subs in op.Base:
    for s in subs:
        assert not s.startswith("?"), "stale element reference: %s" % s
```

Re-bind by locating the face afresh (clear `Base` first — assigning over it keeps the
bad name):

```python
idx = [i+1 for i,f in enumerate(clone.Shape.Faces)
       if abs(f.CenterOfMass.z - z_bottom) < 1e-6 and abs(f.Surface.Axis.z) > 0.99][0]
op.Base = []
op.Base = [(clone, ("Face%d" % idx,))]
```

### Detect slots as GAPS in the open edge, not by pairing walls

Pairing "vertical edges that touch the open edge" misses any slot at a part **end**,
because its outer boundary is the part end, not a wall. On this project that silently
filled in a whole end slot when synthesising square geometry — the parts would have
been unusable. Walk the open edge's solid segments and take the gaps between them,
including before the first and after the last.

Validate synthesised geometry by **area delta against an exact expected quantity**:
filling only reliefs should add an integer multiple of one relief's area
(`+115.6 = 7.00 × 16.52`). A non-integer means something else got filled too — which
is exactly how the missing end slot was caught.

#### Verify by sampling the mating part's footprint — not by distance to a corner

"Distance from corner to path ≤ tool radius" is **not** a sufficient test: it is
satisfied by a tool merely tangent to the corner. And do not reason about a single
tool position — the bone is an in-and-out *move*, so it sweeps a stadium, not a disc.
Hand-derivation will tell you a correct dogbone fails. Sample instead:

```python
# tab of thickness T seats in a slot of width W  ->  columns at wall+delta, wall-delta
delta = (W - T) / 2.0
for x in (w1 + delta, w2 - delta):
    for k in range(101):                       # 5 mm into the slot from the floor
        if dist_to_path((x, floorV + dirV*k*0.05)) > R:
            blocked = True                     # material left inside the tab footprint
```

Two things that made this test lie to me, both worth copying:

- **Validate the checker against a known answer before trusting it.** Run it on a
  case whose result you already have (undressed = 3.150, dressed = 0.000). A checker
  that returns the same number for every input is broken, not a finding.
- **Pair slot walls by GAP, not by index parity.** The part's two end edges are also
  vertical, so `walls[0],walls[1]` pairs an end edge with a slot wall and silently
  finds no slots. And make the detector orientation-agnostic — nested parts get
  rotated, so slot walls may be horizontal; a detector that only looks for vertical
  walls reports "no slots" for every part and reads like success.

Use a uniform grid index over path segments for the distance query, or a full-sheet
check over ~17 k segments takes minutes.

### Is the profile actually cuttable? Test the corners, not the area

Before generating a single toolpath from someone else's slotted model, check that
the tool can reach every internal corner. A relief that is too small does not
error — the offset just clips and leaves a fillet blocking the joint.

- **Square / T-bone relief must be ≥ one tool DIAMETER.** Derivation: with the
  corner at the origin, slot at `x≤0, y≥0`, the only disc of radius `r` that
  contains the corner and stays in the void is centred at `(0, r)`; it spans
  `y ∈ [0, 2r]`, so the relief must be `≥ 2r` on both sides. A 0.160" relief with
  a 0.250" cutter is 0.64× what it needs and leaves 3.05 mm of material in the slot.
- **A circular dogbone of radius exactly `r`,** centred `cutter_r*(1-1/√2)*√2` from
  the corner on the diagonal, is exactly cuttable — the offset degenerates to the
  arc centre, which is the tool centre.

Do **not** trust a morphological erode/dilate of the void to find these. Eroding
shrinks a correct dogbone circle to a point and OCC drops zero-area features, so
proper dogbones are reported as unreachable — a false positive that will send you
"fixing" correct geometry. Use the offset-path test instead, which is what CAM
actually does:

```python
path = face.OuterWire.makeOffset2D(r)     # this IS the cutter-centre path
# corner is cleared iff its distance to that path is <= r
```
