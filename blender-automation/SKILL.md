---
name: blender-automation
description: Drive Blender through the `blender` MCP server (or its raw socket on `localhost:9876`) to build product renders, material and lighting rigs, and multi-stage assembly animations from CAD. Use whenever a task involves Blender, a `.blend` scene, importing CAD geometry into Blender, rendering a product still or turntable, configuring Cycles or EEVEE, or encoding rendered frames to MP4/WebM. Import CAD as glTF, never STL — STL collapses the whole assembly into one grey material. Never call `bpy.ops.render.render()` for an animation through `execute_code`; it blocks Blender's UI thread. Covers the traps that silently cost hours: `read_factory_settings` tearing down the MCP socket, a sandboxed Blender refusing to read `/tmp`, the parent-child double-translation bug, `hide_render` not cascading to mesh children, FreeCAD's glTF exporter writing every material as metallic=1, matte black rendering as mid-grey under Filmic, and long-animation render timeouts that are purely cosmetic because the render completes anyway. Also covers characters and mascots: generating a mesh from an approved model sheet (Hunyuan3D), projecting the sheet as colour, scripted Rigify rigging and its regeneration traps, walk animation, and rendering matching on-screen clips and print-ready merch stills.
---

# Blender Automation

Control Blender interactively via the `blender` MCP server. Blender exposes a TCP socket server on `localhost:9876`, bridged to MCP via `uvx blender-mcp`. Developed against Blender 5.1; the addon API is stable back to 4.x apart from the import operator names noted under Environment Constraints.

## Instructions

You are automating Blender operations.

### Environment configuration — resolve paths, never hardcode them

This skill refers to two locations. **Never bake either one into a file, a script, or
a code snippet you save.**

| Name | What it is |
|---|---|
| `SANDBOX_STAGE_DIR` | A directory Blender can definitely read and write. Must **not** be `/tmp` if Blender is a snap or flatpak — those are sandboxed and cannot see it. |
| `PROJECT_ROOT` | Root of the asset/product repository that renders and CAD files live under. |

Resolve each in this order:

1. **Ask the user**, and offer to save the answer to a gitignored local config file.
2. **Accept it as a parameter** when prompting is impossible.
3. **Read the environment variable.**
4. **Fail with a message naming all three.** Never fall back to a default that happens
   to be one developer's machine.

**Host-side code inherits your shell environment; code inside Blender does not.**
Anything you send through `execute_code` runs in the Blender process, which is usually
launched from a desktop launcher and has none of your shell variables. So:

```python
# host side (Bash, or the Python that talks to the socket) — env works
import os
WORK = os.environ["SANDBOX_STAGE_DIR"]
PROJECT_ROOT = os.environ["PROJECT_ROOT"]

# Blender side — substitute the resolved path INTO the code string you send
send(s, 'execute_code', {'code': f'bpy.ops.import_scene.gltf(filepath="{WORK}/part.glb")'})
```

Blender-side snippets below therefore open with `WORK = "<resolved work dir>"` as a
placeholder. Substitute the real value host-side; do not write it into a saved file.

### MCP Tools (Primary Method — ALWAYS try first)

The `blender` MCP server is configured globally. Use its tools directly for all Blender operations. If the MCP tools are not available or the connection fails, **ask the user to start Blender and enable the MCP addon** (View3D > Sidebar > BlenderMCP > Start Server on port 9876) before falling back to raw socket commands.

### Raw Socket Commands (Fallback ONLY)

Only use raw socket commands if MCP tools are unavailable AND the user has confirmed Blender is running with the addon active. Use a Python script via Bash to send commands to the Blender socket server:

```python
python3 -c "
import socket, json

def blender_cmd(cmd_type, params=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 9876))
    s.settimeout(120)
    payload = json.dumps({'type': cmd_type, 'params': params or {}})
    s.sendall(payload.encode('utf-8'))
    chunks = []
    while True:
        try:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            # Try parsing — if valid JSON, we're done
            try:
                result = json.loads(b''.join(chunks))
                s.close()
                return result
            except json.JSONDecodeError:
                continue
        except socket.timeout:
            break
    s.close()
    return json.loads(b''.join(chunks))

result = blender_cmd('get_scene_info')
print(json.dumps(result, indent=2))
"
```

For multi-step operations, open a persistent connection and send multiple commands:

```python
python3 << 'PYEOF'
import os, socket, json

PROJECT_ROOT = os.environ["PROJECT_ROOT"]   # see "Environment configuration"

def blender_session():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 9876))
    s.settimeout(7200)
    return s

def send(sock, cmd_type, params=None):
    payload = json.dumps({'type': cmd_type, 'params': params or {}})
    sock.sendall(payload.encode('utf-8'))
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        try:
            return json.loads(b''.join(chunks))
        except json.JSONDecodeError:
            continue

s = blender_session()

# Example: import STL, create material, assign it
r = send(s, 'import_file', {'filepath': f'{PROJECT_ROOT}/Product/Example/CAD/part.stl'})
print(json.dumps(r, indent=2))
obj_name = r['result']['imported'][0]

send(s, 'create_material', {'name': 'DarkPlastic', 'base_color': [0.025, 0.027, 0.035], 'roughness': 0.35})
send(s, 'assign_material', {'object_name': obj_name, 'material_name': 'DarkPlastic'})

s.close()
PYEOF
```

### Available Commands

#### Scene & Object Queries
| Command | Params | Description |
|---------|--------|-------------|
| `get_scene_info` | — | Scene overview: objects, materials, render settings |
| `get_object_info` | `name` | Detailed info on one object (transform, mesh stats, bounding box) |
| `list_objects` | `type_filter?`, `collection?` | List objects, optionally filtered |
| `list_materials` | — | All materials with base color info |
| `list_collections` | — | Collection hierarchy |

#### Viewport
| Command | Params | Description |
|---------|--------|-------------|
| `get_viewport_screenshot` | `filepath?`, `max_size?` | Screenshot the 3D viewport to a file |

#### Object Creation & Management
| Command | Params | Description |
|---------|--------|-------------|
| `create_object` | `primitive`, `name?`, `location?`, `rotation?`, `scale?`, plus primitive-specific kwargs (`radius`, `depth`, `segments`, etc.) | Create a primitive. Available: `cube`, `sphere`, `ico_sphere`, `cylinder`, `cone`, `torus`, `plane`, `circle`, `grid`, `monkey`, `empty`, `camera`, `light_point`, `light_sun`, `light_spot`, `light_area`, `bezier_curve`, `nurbs_curve`, `text` |
| `delete_object` | `name` | Delete an object |
| `duplicate_object` | `name`, `new_name?` | Duplicate an object with its data |

#### Transforms
| Command | Params | Description |
|---------|--------|-------------|
| `set_transform` | `name`, `location?`, `rotation?`, `scale?`, `mode?` | Set or add (`mode="add"`) transforms. Rotation is Euler radians. |

#### Modifiers
| Command | Params | Description |
|---------|--------|-------------|
| `add_modifier` | `object_name`, `modifier_type`, `modifier_name?`, `properties?` | Add modifier (e.g. `BEVEL`, `SUBSURF`, `ARRAY`). Properties dict sets modifier attributes. |
| `remove_modifier` | `object_name`, `modifier_name` | Remove a modifier |
| `list_modifiers` | `name` | List modifiers on an object |

#### Materials
| Command | Params | Description |
|---------|--------|-------------|
| `create_material` | `name`, `base_color?`, `metallic?`, `roughness?`, `emission_color?`, `emission_strength?`, `alpha?` | Create/update a Principled BSDF material. Colors are `[R, G, B]` floats 0-1. |
| `assign_material` | `object_name`, `material_name` | Assign material to object's first slot |
| `set_material_color` | `material_name`, `color` | Change base color of existing material |

#### Collections
| Command | Params | Description |
|---------|--------|-------------|
| `create_collection` | `name`, `parent?` | Create a collection |
| `move_to_collection` | `object_name`, `collection_name` | Move object to collection |

#### Import/Export
| Command | Params | Description |
|---------|--------|-------------|
| `import_file` | `filepath` | Import a file. Supported: `.stl`, `.obj`, `.fbx`, `.gltf`, `.glb`, `.ply`, `.svg`, `.dae`, `.abc`, `.usd/.usda/.usdc/.usdz`. Returns list of imported object names. |
| `export_file` | `filepath`, `objects?` | Export scene or selected objects. Supported: `.obj`, `.fbx`, `.gltf`, `.glb`, `.stl`, `.ply`, `.dae`, `.abc`, `.usd/.usda/.usdc`. |

**Note:** STEP (`.stp`/`.step`) import is NOT natively supported. Convert to STL or glTF via FreeCAD first.

#### Selection
| Command | Params | Description |
|---------|--------|-------------|
| `select_objects` | `names` (list), `deselect_others?` | Select objects by name |
| `set_active_object` | `name` | Set the active object |

#### Edit Mode Mesh Operations
| Command | Params | Description |
|---------|--------|-------------|
| `edit_mesh` | `object_name`, `operation`, plus operation-specific kwargs | Mesh edit operations: `subdivide` (`cuts`), `extrude` (`offset`), `inset` (`thickness`), `bevel` (`offset`, `segments`), `loop_cut` (`cuts`), `merge` (`merge_type`), `smooth` (`factor`, `repeat`), `flip_normals`, `recalc_normals` (`inside`), `delete_loose`, `shade_smooth`, `shade_flat` |

#### Animation
| Command | Params | Description |
|---------|--------|-------------|
| `set_keyframe` | `object_name`, `frame`, `data_path?`, `value?` | Insert keyframe. Default data_path is `location`. |
| `set_frame` | `frame` | Set current frame |

#### Rendering (ASYNC — CRITICAL)
| Command | Params | Description |
|---------|--------|-------------|
| `render_image` | `filepath?`, `engine?`, `resolution?` (list `[w,h]`), `samples?`, `animation?`, `frame_start?`, `frame_end?` | **Start** an async render. Returns immediately. |
| `poll_render` | — | Check render status. Returns `rendering`, `complete`, `cancelled`, or `idle`. |

**NEVER use `execute_code` to call `bpy.ops.render.render()` directly — it blocks Blender's UI thread and causes "not responding" dialogs.** Always use `render_image` + `poll_render`.

Render polling pattern:
```python
import time

send(s, 'render_image', {
    'filepath': f'{PROJECT_ROOT}/Brand/Graphics/Exports/Web/render.png',
    'engine': 'CYCLES',
    'resolution': [1920, 1080],
    'samples': 256,
})

while True:
    time.sleep(3)
    r = send(s, 'poll_render')
    status = r.get('result', {}).get('status', 'unknown')
    print(f"Render status: {status}")
    if status in ('complete', 'cancelled', 'failed', 'idle'):
        break
```

#### Arbitrary Code Execution
| Command | Params | Description |
|---------|--------|-------------|
| `execute_code` | `code` | Run arbitrary Python in Blender's context. Has access to `bpy`, `mathutils`, `bmesh`, `math`. Returns stdout capture. **Never use for rendering** — use `render_image` instead. |

### Environment Constraints

- **Install method decides what Blender can read.** A snap or flatpak Blender is **sandboxed** and cannot access `/tmp`. Every path you hand it must be under `$SANDBOX_STAGE_DIR`. If render output appears "not to write," it is almost certainly landing in the sandbox's private tmp (`$XDG_RUNTIME_DIR/.flatpak/org.blender.Blender/tmp/`) rather than where you asked — write to `$SANDBOX_STAGE_DIR` instead. A distro package or the official tarball has no such restriction.
- **GPU: query it, do not assume it.** Call `cprefs.get_devices()` and print each device's `name` and `type`. Backend by vendor: `OPTIX` or `CUDA` on NVIDIA, `HIP` on AMD, `METAL` on Apple silicon, `ONEAPI` on Intel Arc. Timings quoted in this skill were measured on an 8 GB NVIDIA laptop GPU — scale expectations to the hardware actually present.
- **STL import:** Uses `bpy.ops.wm.stl_import()` in Blender 5.x (not `bpy.ops.import_mesh.stl()`).
- **Render engine names:** `CYCLES`, `BLENDER_EEVEE`, `BLENDER_WORKBENCH`.

### MCP Tool Availability — Verify Before Relying on Them

The command table above documents the **full** `blender-mcp` server API. In some environments only a subset is actually registered as callable MCP tools (commonly: `execute_blender_code`, `get_scene_info`, `get_object_info`, `get_viewport_screenshot`, and a few polyhaven/hyper3d helpers). If a documented tool like `render_image`, `create_material`, `set_keyframe`, or `assign_material` is missing, **do everything through `execute_blender_code`** with raw `bpy` Python. The raw-socket fallback pattern with `send(s, 'cmd_name', ...)` only works against a full `blender-mcp` server, not the subset environment.

When `render_image` / `poll_render` are unavailable, a single blocking `bpy.ops.render.render(write_still=True)` inside `execute_blender_code` is acceptable for **still images** (the UI briefly freezes but recovers). For animations you must use the full API — re-check which tools are exposed at the start of any animation task.

### GPU Setup (MANDATORY — always run before any render)

**Always configure the GPU before rendering.** GPU renders are dramatically faster than CPU. Run this once per session before any `render_image` call, and read the printed device list rather than assuming a backend:

```python
send(s, 'execute_code', {'code': """
import bpy
# Set Cycles as render engine
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'GPU'

# Pick the first compute backend this build actually supports
prefs = bpy.context.preferences.addons.get('cycles')
if prefs:
    cprefs = prefs.preferences
    for backend in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
        try:
            cprefs.compute_device_type = backend
            break
        except TypeError:
            continue          # not available in this build
    cprefs.get_devices()
    for d in cprefs.devices:
        d.use = True
        print('device:', d.name, d.type)
    print('backend:', cprefs.compute_device_type)

# Enable denoising for cleaner results at lower sample counts
bpy.context.scene.cycles.use_denoising = True
bpy.context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'

print('Cycles + CUDA GPU rendering enabled with CUDA denoising')
"""})
```

With GPU compute + denoising, Cycles renders are fast enough for both stills and animations. Use `BLENDER_EEVEE` only if you need real-time preview or intentionally want a non-raytraced look.

### Product Visualization Workflow

Typical workflow for rendering a TrailCurrent product:

1. **Query scene** — `get_scene_info` to see what's loaded
2. **Enable GPU** — run the GPU setup code (see above) — do this first, every session
3. **Clear defaults** — `execute_code` to delete default cube/light/camera if present
4. **Export from FreeCAD as glTF/GLB, NOT STL** — see "CAD → Blender Handoff" below. STL collapses the whole assembly to one material; glTF preserves per-body colors and keeps parts as separate objects. **Never reach for STL as the "simpler" option for a product render.**
5. **Import model** — `bpy.ops.import_scene.gltf(filepath=...)` (or `import_file` MCP command if available)
6. **Normalize imported materials** — FreeCAD's Assimp glTF export writes every material with `metallic=1.0` and `roughness=1.0`. Loop through all materials and reset to `metallic=0` / `roughness=0.55` (or similar sensible dielectric defaults), then upgrade specific metals (gold pads, silver shells) afterward. See "FreeCAD glTF Quirks" below.
7. **Center & scale** — `execute_code` to normalize object position and size (parent all imported objects to an empty, recenter the empty)
8. **Apply smooth shading** — `edit_mesh` with `shade_smooth`
9. **Set up lighting** — `create_object` with `light_area` (key, fill, rim lights). For dark materials see "Lighting Dark Materials" below.
10. **Set up camera** — `create_object` with `camera`, then `execute_code` to configure lens and set as scene camera. Use `Vector.to_track_quat('-Z','Y').to_euler()` to aim the camera at a target point instead of constraints (constraints break when objects get replaced — see "Constraint Targets" below).
11. **Configure world** — `execute_code` to set background color/HDRI. Keep world strength low (0.05–0.2) so it doesn't lift dark surfaces.
12. **Add a backdrop (cyclorama)** — see "Cyclorama Backdrop" below for the Simple Deform bend trick that eliminates harsh horizon lines.
13. **Render** — `render_image` with `engine='CYCLES'` (async) + poll with `poll_render`, OR blocking `bpy.ops.render.render(write_still=True)` via `execute_code` if the MCP server doesn't expose the async render commands
14. **Verify** — Read the output image file to check the result

### CAD → Blender Handoff (ALWAYS glTF, NEVER STL)

STL is wrong for product rendering. It collapses the whole assembly to a single tessellated triangle soup, loses all per-body colors, and produces a grey blob that looks nothing like the CAD. Use glTF (`.glb`).

**In FreeCAD (via MCP `execute_code`):**

```python
import FreeCAD as App
doc = App.ActiveDocument
asm = doc.getObject("Assembly")  # or your top-level body/assembly object
PROJECT_ROOT = "<resolved project root>"   # substituted in; see "Environment configuration"
out = f"{PROJECT_ROOT}/Product/<Name>/CAD/<Name>Assembly.glb"
import ImportGui
ImportGui.export([asm], out)
```

**In Blender:**

```python
WORK = "<resolved work dir>"   # must be readable by a sandboxed Blender
bpy.ops.import_scene.gltf(filepath=f"{WORK}/<Name>Assembly.glb")
```

This gives you N separate mesh objects (one per CAD body) with materials named `mat_0`, `mat_1`, etc. that match FreeCAD's per-body ShapeColor assignments. Identify which material belongs to what by inspecting `obj.material_slots` on a named mesh object (e.g., `bpy.data.objects["BodyHeadwatersCaseBottom001"]`) and print each slot's material name and base color.

### FreeCAD glTF Quirks

1. **Everything imports as metallic=1, rough=1.** Artifact of the Assimp glTF exporter. Normalize right after import:

   ```python
   for m in bpy.data.materials:
       if not m.use_nodes:
           continue
       bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
       if not bsdf:
           continue
       bc = bsdf.inputs["Base Color"].default_value
       r, g, b = bc[0], bc[1], bc[2]
       # Default everything to dielectric
       bsdf.inputs["Metallic"].default_value = 0.0
       bsdf.inputs["Roughness"].default_value = 0.55
       # Upgrade gold-ish colors to metallic
       if r > 0.9 and 0.5 < g < 0.85 and b < 0.3:
           bsdf.inputs["Metallic"].default_value = 1.0
           bsdf.inputs["Roughness"].default_value = 0.38
   ```

2. **Per-face colors on child features DO NOT propagate to glTF.** If a PartDesign Body has per-face DiffuseColor set on a child feature (e.g., a `FeatureSubtractivePython` with a logo or inlay that has specific face colors), only the Body's top-level ShapeColor reaches the glTF. The face-level detail collapses to the body color.

   Workarounds (in order of preference):
   - **Assign per-face colors at the Body level** in FreeCAD before export: `body.ViewObject.DiffuseColor = [(r,g,b,a), ...]` as a flat list matching the body's face count. Save the document before export. Sometimes even this doesn't propagate — test by re-importing and counting the green (or whatever color) polygons.
   - **Fix it in Blender after import** by identifying the target polygons by geometric criteria (Z level, radius from center, normal direction) and reassigning their `material_index`. Example for a disc inlay:
     ```python
     cv = bpy.data.objects["BodyCaseCover001"]
     cb = [cv.matrix_world @ Vector(c) for c in cv.bound_box]
     cx = (min(p.x for p in cb) + max(p.x for p in cb)) / 2
     cy = (min(p.y for p in cb) + max(p.y for p in cb)) / 2
     for p in cv.data.polygons:
         n = cv.matrix_world.to_3x3() @ p.normal
         if n.z < 0.8:   # only top-facing polys
             continue
         c = cv.matrix_world @ p.center
         dx, dy = c.x - cx, c.y - cy
         if (dx*dx + dy*dy) ** 0.5 > 0.0352:  # inside 35.2mm radius
             continue
         if 0.04465 < c.z < 0.04495:  # this specific Z level = raised feature, keep dark
             continue
         p.material_index = 1   # reassign to the colored slot
     cv.data.update()
     ```
   - The Z-histogram-per-material trick: bucket top-facing polys by rounded Z and see which levels correspond to which CAD features. Different levels often mean different raised/recessed features that need different materials.

3. **World Y extent vs. body extent.** FreeCAD's `asm.Shape.BoundBox` gives the actual rendered extent including any connectors or features sticking out. A case body might be 91.4 mm wide at mid-height but 94.6 mm wide at the port face (where a DTM connector protrudes). For dimensional callouts, use the bounding box, not the case body alone.

### Lighting Dark Materials (Critical)

Matte black plastic enclosures are surprisingly hard to render correctly. Common failure mode: the object renders as mid-grey, even with a base color of 0.006. Causes and fixes:

1. **Filmic view transform + bright lights = washed out dark materials.** Filmic's log curve lifts near-black values into the mid-grey range. For a properly-dark matte black finish, either:
   - Drop `scene.view_settings.exposure` to `-1.3` and reduce light energy to ~14 W key, ~5 W fill, ~9 W rim (area lights at ~0.5 m distance), OR
   - Switch to `Standard` view transform for direct linear color response

2. **Specular reflection dominates dark materials.** A material with base color `(0.006, 0.006, 0.008)` reflects only ~1% diffusely, so even a small specular component (0.5 IOR level) overwhelms the diffuse signal. Fix by setting:
   - Roughness to **0.88** (very matte, kills specular blowout)
   - Specular IOR Level to **0.20** (if the Principled BSDF exposes it)

3. **Reference recipe — matte black ABS enclosure:**
   ```python
   bsdf.inputs["Base Color"].default_value = (0.006, 0.006, 0.008, 1.0)
   bsdf.inputs["Metallic"].default_value = 0.0
   bsdf.inputs["Roughness"].default_value = 0.88
   if "Specular IOR Level" in bsdf.inputs:
       bsdf.inputs["Specular IOR Level"].default_value = 0.20
   ```
   With Filmic + Medium High Contrast + exposure −1.3, lights at 14/5/9 W, and an off-white (0.68) backdrop, this produces true matte black.

4. **Glowing logo on a dark case — use a pure Emission shader, not Principled BSDF.** Principled emission competes with specular and tends to clip to yellow-white when strength > 1. Replace the shader entirely:
   ```python
   nt = logo_mat.node_tree
   for n in list(nt.nodes):
       nt.nodes.remove(n)
   out = nt.nodes.new("ShaderNodeOutputMaterial")
   em = nt.nodes.new("ShaderNodeEmission")
   em.inputs["Color"].default_value = (0.082, 0.41, 0.052, 1.0)  # TrailCurrent green, linear
   em.inputs["Strength"].default_value = 2.0
   nt.links.new(em.outputs[0], out.inputs[0])
   ```
   Strength 1.5–2.0 works well. Above 2.5 it clips to white. Below 1.0 it's invisible against bright lights.

5. **Flat surfaces perpendicular to the key light blow out.** A thin flat cover (e.g., 4.5 mm thick) viewed from directly above catches full-on specular from an overhead key light and reads as silver. Fix by rotating the camera to an oblique 3/4 angle, or moving the key light off-axis.

### Cyclorama Backdrop (No Harsh Horizon)

A flat plane backdrop produces a hard line where the floor meets the back wall. Use a curved sweep:

```python
bpy.ops.mesh.primitive_grid_add(size=2.0, x_subdivisions=20, y_subdivisions=40, location=(0, 0.4, 0))
cyc = bpy.context.active_object
cyc.name = 'Backdrop'
cyc.scale = (2.0, 2.0, 2.0)
bpy.ops.object.transform_apply(scale=True)
mod = cyc.modifiers.new('Bend', 'SIMPLE_DEFORM')
mod.deform_method = 'BEND'
mod.deform_axis = 'X'
mod.angle = math.radians(90)
bpy.ops.object.modifier_apply(modifier='Bend')
cyc.location = (0, -1.0, 0)
```

This produces a J-shaped sweep where the floor flows smoothly up into the back wall with no visible seam.

### Per-Part Rendering from a Loaded Assembly

Instead of re-importing for each individual part shot, toggle visibility on the already-loaded assembly:

```python
glb_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name != 'Backdrop']

def hide_all_except(keep_names):
    for o in glb_meshes:
        o.hide_render = o.name not in keep_names

# Render just the case bottom
hide_all_except({'BodyCaseBottom001'})
bpy.context.scene.render.filepath = f"{WORK}/case-bottom.png"
bpy.ops.render.render(write_still=True)

# Restore everything
for o in glb_meshes:
    o.hide_render = False
```

This is much faster than re-importing a 700+ object assembly for each shot, and all materials/lights/camera stay configured.

### Constraint Targets and Object Replacement

If you delete an object that a camera has a `TRACK_TO` constraint on, the constraint target becomes `None` and the camera points into empty space. **Prefer aiming the camera directly via rotation math** instead of using constraints, especially when you're swapping objects in and out during a multi-shot render session:

```python
import mathutils
target = mathutils.Vector((0, 0, 0.022))
cam.location = (0.20, -0.30, 0.14)
d = target - mathutils.Vector(cam.location)
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
```

Or, if you must use TRACK_TO, re-link the target after any delete+replace.

### Canvas / Scale Uniformity for Grid Layouts

When rendering multiple orthographic views (top/front/side) that will be displayed in a grid on the web, make sure each image has the **same final canvas size** so CSS `object-fit: contain` scales them by the same factor. Otherwise font sizes, dimension arrows, and object-on-screen sizes vary wildly between tiles even though the source PNGs all look fine individually. Either:

- Pad each annotated image to a uniform canvas size (e.g., 1280×1240) with the object centered and consistent annotation margins
- Or render each view at the same output resolution with the viewport fitted to the longest common dimension

### Assembly Animation Workflow

Product assembly animations show how parts fit together — board into housing, screws into standoffs, lid onto enclosure, etc. These are rendered as video frames then assembled with ffmpeg.

#### Animation Concepts

- **30 fps** is standard. A 1-second move = 30 frames.
- Use **ease-in/ease-out** for natural motion. Set keyframe interpolation to `BEZIER` (default) rather than `LINEAR`.
- Parts should **pause briefly** at their final position before the next part moves (~15-20 frames hold).
- Keep the camera static or on a slow orbit — don't move camera and parts simultaneously.
- **Use EEVEE for animations** (`BLENDER_EEVEE` / `BLENDER_EEVEE_NEXT`). With 32 TAA samples, EEVEE renders ~0.6 s/frame on an 8 GB laptop GPU — a 740-frame animation finishes in ~2.5 minutes. Cycles with 16 samples takes ~6 s/frame (62 min for the same animation) and the visual difference in product animations is negligible. Reserve Cycles for hero stills where material accuracy really matters.
- **The MCP render call will "time out" on long animations — that's cosmetic.** `bpy.ops.render.render(animation=True)` for 700+ frames exceeds the MCP socket timeout (~60 s) and reports `Communication error: No data received`. **The render still completes in Blender.** Verify with `ls <output_dir>/ | wc -l` and proceed to ffmpeg encoding in a separate Bash call.

#### Assembly Animation Gotchas (hard-won — skip these and waste hours)

1. **NEVER call `bpy.ops.wm.read_factory_settings(use_empty=True)`.** It tears down the BlenderMCP addon socket and you lose the MCP connection. To clear the scene, iterate `bpy.data.objects`, `bpy.data.materials`, `bpy.data.meshes` and remove entries manually.

2. **Snap/flatpak sandboxes can't read `/tmp`.** Stage all glTF files under `$SANDBOX_STAGE_DIR` before importing. FreeCAD writes `/tmp` fine, so the pattern is: `ImportGui.export(..., "/tmp/x.glb")` → `cp /tmp/x.glb "$SANDBOX_STAGE_DIR/"` → `bpy.ops.import_scene.gltf(filepath=f"{WORK}/x.glb")`.

3. **Parent-child double-translation bug.** After `parent.location = world_pos`, call `bpy.context.view_layer.update()` before computing `matrix_parent_inverse`. AND zero out the child's local transform after parenting. The only reliable recipe:
   ```python
   parent.location = world_pos
   bpy.context.view_layer.update()
   for fg in children:
       fg.parent = parent
       fg.matrix_parent_inverse = Matrix.Identity(4)
       fg.location = (0, 0, 0)
       fg.rotation_euler = (0, 0, 0)
       fg.scale = (1, 1, 1)
   ```
   Symptom: model lands at exactly 2× the intended offset.

4. **`hide_render` doesn't cascade to mesh children.** Keyframing visibility on a parent empty does nothing for its children. You must iterate `parent.children_recursive` and keyframe `hide_render` + `hide_viewport` on each child mesh individually. Symptom: inner components appear floating at their final positions from frame 1.

5. **Screw copies inherit flipped `matrix_basis`.** When you duplicate a FreeCAD-imported screw and set `rotation_euler = (0,0,0)`, the screw can still render flipped because `matrix_basis` holds a −1 scale in X and Z (from the source link's placement). Fix: set `matrix_basis = Matrix.Translation(world_pos)` and `matrix_parent_inverse = Matrix.Identity(4)` explicitly, then `view_layer.update()`. Verify head/thread direction via vertex density analysis — head has wide max radius, thread tip is narrow.

6. **Assembled PCBs drop as ONE rigid unit.** For a multi-face-color board (Waveshare, CM5, etc.), keyframe ONLY the parent empty. All children should have zero location fcurves. Verify:
   ```python
   sum(1 for c in parent.children_recursive
       if c.animation_data
       and any("location" in fc.data_path
               for fc in c.animation_data.action.fcurves)) == 0
   ```

7. **Z-fighting on inlaid logo/label faces.** 50 μm (0.00005 m) offset is NOT enough — EEVEE shows speckle bleed. Use **0.00015 m (150 μm) minimum**.

8. **Save the scene after setup.** `bpy.ops.wm.save_as_mainfile(filepath=f"{WORK}/<product>_scene.blend")` so you can reopen without re-running the whole pipeline.

#### Assembly Animation Staging Template

22–25 seconds at 30 fps = 660–740 frames. Adapt ranges per product; overlap stages by ~5 frames for smoother flow.

| Frame range | Stage |
|---|---|
| 1–20 | Intro: enclosure base only, low camera angle |
| 20–80 | Mounting screws rise from below |
| 85–145 | First PCB layer drops (3-frame stagger) |
| 150–210 | Standoffs / spacers drop onto first layer |
| 215–275 | Second PCB layer drops onto standoffs |
| 280–340 | Top mounting screws drop into standoff tops |
| 345–405 | Main MCU / main board drops as one rigid unit (drop height ≤ 0.05 m) |
| 420–480 | Connector housings slide in from outside |
| 455–515 | Pins slide in staggered |
| 505–565 | Wedge locks / retainers slide in (Deutsch connectors) |
| 575–620 | Cover drops (logo offset 0.00015) |
| 630–700 | Corner cover screws drop (8-frame stagger) |
| 700–740 | Hold on finished assembly |

Camera slowly orbits from angle=−45° / height=0.09 m / radius=0.42 m (low, pivot at z=0.005) up to angle=0° / height=0.34 m / radius=0.40 m (overhead, pivot at z=0.015). 85mm lens.

#### Render + Encode Pipeline

```python
# Blender side
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.taa_render_samples = 32
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.fps = 30
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = f"{WORK}/product_anim_frames/frame_"
scene.frame_start = 1
scene.frame_end = 740
bpy.ops.render.render(animation=True)
```

```bash
# ffmpeg side (separate Bash call after render completes)
cd "$SANDBOX_STAGE_DIR/product_anim_frames"
ffmpeg -y -framerate 30 -i frame_%04d.png \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -preset medium -movflags +faststart \
  "$SANDBOX_STAGE_DIR/product-assembly.mp4"
ffmpeg -y -framerate 30 -i frame_%04d.png \
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 0 -crf 32 -row-mt 1 -threads 4 \
  "$SANDBOX_STAGE_DIR/product-assembly.webm"
convert "$SANDBOX_STAGE_DIR/product_anim_frames/frame_0740.png" -quality 85 \
  "$SANDBOX_STAGE_DIR/product-assembly-poster.jpg"
```

HTML markup uses a `<video autoplay muted loop playsinline preload="metadata">` block with WebM + MP4 sources and a hero PNG fallback — see `headwaters.html` / `reservoir.html` in the TrailCurrent website for the pattern.

#### Typical Assembly Animation Steps

1. **Import all parts as separate STLs** — each part needs to be a distinct object so it can be animated independently. Import them one at a time with `import_file`, noting each object name.

2. **Position parts at their assembled locations first** — use `set_transform` to place each part where it belongs in the final assembly. Use `get_object_info` to check bounding boxes. This is your "end state."

3. **Record end-state keyframes** — for each part, use `set_keyframe` at the frame where that part finishes moving. Work backwards from assembled state.

4. **Set start-state keyframes** — move parts to their "exploded" start positions (typically straight up or out along one axis) and keyframe at their start frame.

5. **Stagger the timing** — each part should animate in sequence, not all at once. E.g., housing at frames 1-40, board at 50-90, screws at 100-160, lid at 170-210.

6. **Configure interpolation** — use `execute_code` to set keyframe interpolation for smooth easing.

7. **Render as image sequence** — use `render_image` with `animation=True`.

8. **Assemble with ffmpeg** — combine frames into MP4.

#### Assembly Animation Example

```python
import math, os, time

PROJECT_ROOT = os.environ["PROJECT_ROOT"]

# --- 1. Clear scene ---
send(s, 'execute_code', {'code': """
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for col in bpy.data.collections:
    bpy.data.collections.remove(col)
"""})

# --- 2. Import parts (each as separate object) ---
housing = send(s, 'import_file', {'filepath': f'{PROJECT_ROOT}/Product/Example/CAD/housing.stl'})
housing_name = housing['result']['imported'][0]

board = send(s, 'import_file', {'filepath': f'{PROJECT_ROOT}/Product/Example/CAD/board.stl'})
board_name = board['result']['imported'][0]

lid = send(s, 'import_file', {'filepath': f'{PROJECT_ROOT}/Product/Example/CAD/lid.stl'})
lid_name = lid['result']['imported'][0]

# --- 3. Normalize scale and center via execute_code ---
send(s, 'execute_code', {'code': f"""
import bpy, mathutils

# Find overall bounding box of all objects
all_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if all_objs:
    corners = []
    for o in all_objs:
        corners.extend([o.matrix_world @ mathutils.Vector(c) for c in o.bound_box])
    center = sum(corners, mathutils.Vector()) / len(corners)
    max_dim = max(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))
    scale = 2.0 / max_dim if max_dim > 0 else 1.0
    for o in all_objs:
        o.location -= center
        o.scale *= scale
    bpy.context.view_layer.update()
    for o in all_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    print(f'Centered and scaled {{len(all_objs)}} objects (factor={{scale:.3f}})')
"""})

# --- 4. Get assembled positions (these are our end state) ---
housing_info = send(s, 'get_object_info', {'name': housing_name})
board_info = send(s, 'get_object_info', {'name': board_name})
lid_info = send(s, 'get_object_info', {'name': lid_name})

# Read each part's assembled location
h_loc = housing_info['result']['location']
b_loc = board_info['result']['location']
l_loc = lid_info['result']['location']

# --- 5. Define animation timeline ---
FPS = 30
# Housing slides in from left:   frames 1-40
# Board drops in from above:     frames 55-95
# Lid comes down from above:     frames 110-150
# Hold final assembly:           frames 150-180

explode_offset = 3.0  # How far parts start from their assembled position

# --- 6. Keyframe the housing ---
# End position (assembled) at frame 40
send(s, 'set_keyframe', {'object_name': housing_name, 'frame': 40, 'data_path': 'location', 'value': h_loc})
# Start position (offset left) at frame 1
send(s, 'set_keyframe', {'object_name': housing_name, 'frame': 1, 'data_path': 'location',
    'value': [h_loc[0] - explode_offset, h_loc[1], h_loc[2]]})

# --- 7. Keyframe the board ---
send(s, 'set_keyframe', {'object_name': board_name, 'frame': 95, 'data_path': 'location', 'value': b_loc})
send(s, 'set_keyframe', {'object_name': board_name, 'frame': 55, 'data_path': 'location',
    'value': [b_loc[0], b_loc[1], b_loc[2] + explode_offset]})

# --- 8. Keyframe the lid ---
send(s, 'set_keyframe', {'object_name': lid_name, 'frame': 150, 'data_path': 'location', 'value': l_loc})
send(s, 'set_keyframe', {'object_name': lid_name, 'frame': 110, 'data_path': 'location',
    'value': [l_loc[0], l_loc[1], l_loc[2] + explode_offset]})

# --- 9. Set interpolation to smooth easing ---
send(s, 'execute_code', {'code': """
import bpy
for obj in bpy.context.scene.objects:
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.easing = 'EASE_IN_OUT'
print('Set all keyframes to BEZIER ease-in-out')
"""})

# --- 10. Set frame range ---
send(s, 'execute_code', {'code': """
import bpy
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = 180
bpy.context.scene.render.fps = 30
print(f'Animation: frames 1-180, {30} fps, {180/30:.1f}s')
"""})

# --- 11. Materials ---
send(s, 'create_material', {'name': 'Housing', 'base_color': [0.025, 0.027, 0.035], 'roughness': 0.35})
send(s, 'assign_material', {'object_name': housing_name, 'material_name': 'Housing'})

send(s, 'create_material', {'name': 'PCB', 'base_color': [0.0, 0.25, 0.08], 'roughness': 0.5, 'metallic': 0.1})
send(s, 'assign_material', {'object_name': board_name, 'material_name': 'PCB'})

send(s, 'create_material', {'name': 'Lid', 'base_color': [0.03, 0.03, 0.04], 'roughness': 0.3})
send(s, 'assign_material', {'object_name': lid_name, 'material_name': 'Lid'})

# --- 12. Lighting & camera (same as product render) ---
send(s, 'create_object', {'primitive': 'light_area', 'name': 'KeyLight', 'location': [3, -2.5, 4]})
send(s, 'execute_code', {'code': """
import bpy, math
l = bpy.data.objects['KeyLight']
l.data.energy = 250
l.data.size = 3.0
l.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
"""})

send(s, 'create_object', {'primitive': 'light_area', 'name': 'FillLight', 'location': [-3.5, -1, 2.5]})
send(s, 'execute_code', {'code': """
import bpy, math
l = bpy.data.objects['FillLight']
l.data.energy = 100
l.data.size = 5.0
l.rotation_euler = (math.radians(40), math.radians(-15), math.radians(-20))
"""})

send(s, 'create_object', {'primitive': 'camera', 'name': 'AnimCamera', 'location': [4.5, -4.5, 3.5]})
send(s, 'execute_code', {'code': """
import bpy, mathutils
cam = bpy.data.objects['AnimCamera']
bpy.context.scene.camera = cam
cam.data.lens = 65
direction = mathutils.Vector((0, 0, 0.5)) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
"""})

# --- 13. World background ---
send(s, 'execute_code', {'code': """
import bpy
world = bpy.context.scene.world or bpy.data.worlds.new('World')
bpy.context.scene.world = world
world.use_nodes = True
wn = world.node_tree.nodes
wl = world.node_tree.links
wn.clear()
bg = wn.new('ShaderNodeBackground')
bg.inputs['Color'].default_value = (0.08, 0.085, 0.10, 1.0)
bg.inputs['Strength'].default_value = 0.3
out = wn.new('ShaderNodeOutputWorld')
wl.new(bg.outputs['Background'], out.inputs['Surface'])
"""})

# --- 14. Enable GPU and render animation ---
send(s, 'execute_code', {'code': """
import bpy
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'GPU'
prefs = bpy.context.preferences.addons.get('cycles')
if prefs:
    cprefs = prefs.preferences
    cprefs.compute_device_type = 'CUDA'
    cprefs.get_devices()
    for d in cprefs.devices:
        d.use = True
bpy.context.scene.cycles.use_denoising = True
bpy.context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'
print('Cycles + CUDA GPU enabled')
"""})

output_dir = f'{PROJECT_ROOT}/MediaPool/Exports/ProductDemos/assembly_'
send(s, 'render_image', {
    'filepath': output_dir,
    'engine': 'CYCLES',
    'resolution': [1920, 1080],
    'samples': 128,
    'animation': True,
    'frame_start': 1,
    'frame_end': 180,
})

while True:
    time.sleep(5)
    r = send(s, 'poll_render')
    status = r.get('result', {}).get('status', 'unknown')
    print(f'Render: {status}')
    if status in ('complete', 'cancelled', 'failed', 'idle'):
        break
```

After rendering, assemble frames into video:
```bash
ffmpeg -y -framerate 30 \
  -i "$PROJECT_ROOT/MediaPool/Exports/ProductDemos/assembly_%04d.png" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -crf 18 \
  "$PROJECT_ROOT/MediaPool/Exports/ProductDemos/assembly_animation.mp4"
```

Note: ffmpeg frame input uses the pattern from the first numbered file. If Blender outputs `assembly_0001.png`, `assembly_0002.png`, etc., use `-i assembly_%04d.png`.

#### Screw Animation Tips

Screws need rotation AND translation simultaneously:

```python
# Screw starts above its hole, rotated
screw_assembled_loc = [0.5, 0.3, 0.1]  # Final position
screw_start_loc = [0.5, 0.3, 0.1 + 1.5]  # Above the hole

# Frame 100: start position, unrotated
send(s, 'set_keyframe', {'object_name': 'Screw', 'frame': 100, 'data_path': 'location', 'value': screw_start_loc})
send(s, 'set_keyframe', {'object_name': 'Screw', 'frame': 100, 'data_path': 'rotation_euler', 'value': [0, 0, 0]})

# Frame 140: assembled, rotated several turns
import math
send(s, 'set_keyframe', {'object_name': 'Screw', 'frame': 140, 'data_path': 'location', 'value': screw_assembled_loc})
send(s, 'set_keyframe', {'object_name': 'Screw', 'frame': 140, 'data_path': 'rotation_euler',
    'value': [0, 0, math.pi * 6]})  # 3 full turns
```

#### Camera Orbit During Assembly

A slow orbit adds visual interest. Use an empty as a pivot:

```python
send(s, 'create_object', {'primitive': 'empty', 'name': 'CameraPivot', 'location': [0, 0, 0.5]})
send(s, 'execute_code', {'code': """
import bpy, math
pivot = bpy.data.objects['CameraPivot']
cam = bpy.data.objects['AnimCamera']
cam.parent = pivot

# Slow 30-degree orbit over the full animation
pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert(data_path='rotation_euler', frame=1)
pivot.rotation_euler = (0, 0, math.radians(30))
pivot.keyframe_insert(data_path='rotation_euler', frame=180)

# Linear interpolation for smooth constant-speed orbit
for fc in pivot.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
"""})
```

### Example file placement convention (adapt to your own repo layout)

- Product renders for web: `Brand/Graphics/Exports/Web/`
- Product renders for print: `Brand/Graphics/Exports/Print/`
- Product renders for social: `Brand/Graphics/Exports/Social/`
- Turntable/animation videos: `MediaPool/Exports/ProductDemos/`
- Blender source files (.blend): `Brand/Graphics/Source/Mockups/`
- Product-specific 3D scenes: `Product/<Name>/CAD/`

All paths are relative to `$PROJECT_ROOT` (see "Environment configuration").

## Characters and Mascots: Generate, Rig, Animate, Render

Lessons from building a brand mascot that has to look identical in video and on printed merch. The goal for any mascot: **one 3D model is the single source** for every on-screen appearance, web image, firmware sprite and merch print, so the audience recognizes the same character everywhere.

### Pipeline that worked

1. **Approve a design image first.** Generate a few full-body model-sheet candidates with an image model (front view, relaxed A-pose, arms away from the body, whole figure in frame, plain white background, no props or backpack), and let the user pick one. Every later step derives from that one image.
2. **Let a 3D-generation model build the mesh** from the approved sheet (Hunyuan3D 2.1 in ComfyUI: 30 steps, cfg 5, 4096 latent tokens, octree 256, surface-net 0.6). **Remove the background first.** A white backdrop gets reconstructed as walls and a floor around the character.
3. **In Blender, do only mechanical work:** scale, light decimate, project colours, rig, pose, animate, light, render. Don't sculpt faces or reshape bodies by script. Scripted reshaping caused every major defect in the first attempt (child proportions, beard lumps, mismatched hands, cross-eyes).
4. **Never use an image model for individual character images or poses** after this point. Every image is a render of the model. Image models drift the face on every generation.

### Texturing a generated mesh from its model sheet

- **Planar front projection** of the approved sheet: UV = sheet pixel at the vertex's (x, z), aligned by the figure's bounding box. Map the true-normal Y to a mix factor so forward-facing faces show the sheet and side/back faces show per-vertex colour.
- **Side and back colour:** sample the sheet at the same (x, z), but first
  - **fill the sheet's background** outward from the figure's own edge colours (push-pull pyramid fill), so samples at the silhouette never pick up white,
  - **blur it heavily** (box blur, radius ~14 px on a 1296 px sheet), so the back of the jacket doesn't get the front's zipper and pockets,
  - **sample a little inward** for side-facing vertices (offset x by ~3.5 cm × |normal.x|) **toward the limb's own axis**, not toward the body centre. Stepping toward the centre from the inside of a leg or arm lands in the gap between the limbs, which is background fill, and renders as a pale seam down the inner thigh. Legs: axis at ±0.11 m, arms at ±0.30 m on a 1.75 m figure; do the same for the projection UVs of the inner leg faces (2 cm).
- **The head needs explicit rules,** because the sheet only shows the face:
  - **Behind the face:** hair, blended in over ~6 cm of depth so the hairline isn't a hard edge.
  - **Above the brim line:** cap colour, as the median of saturated cap pixels, not a single sample (that grabbed the dark patch).
  - **Brim underside** (normal.z < −0.45): shaded cap colour, or it renders as a grey band.
  - **Below the head:** the hood/collar back gets jacket colour.
  - **Ears stick out** past the head width. Exclude them from the hair rule.
- **Force the painted face only on forward-facing faces** (true −normal.y > ~0.35). Forcing it further round the cheek stretches the sheet into pale streaks.
- **Asymmetric face?** Mirror the good half of the sheet's head rows around the head's own symmetry axis (centre of the cap/head silhouette rows), feather ~20 rows below the chin, then project.
- **Hands:** colour every vertex weighted to `DEF-hand/palm/f_/thumb` with the sheet's skin tone, and fade the projection out on them. Otherwise their sides pick up whatever they hang next to (cargo pockets).
- **Colour space trap:** `image.pixels` returns display (sRGB) values. `FLOAT_COLOR` attributes are linear. Convert (`((c+0.055)/1.055)**2.4`) before writing, or every sampled area renders washed-out pale.
- **Camera angle:** projected characters look best within about 20° of the front. Plan hero and merch shots there. Wide or moving shots tolerate the sides.

### Rigging with Rigify (scripted)

- **Measure joints from the mesh,** don't guess. Take z-slices of the mesh, read where the legs split, where the arms separate from the torso, and the narrowest neck and wrist slices. Set each joint's depth to the mesh centre at that height.
- **Bend direction:** put **knees ~4 cm in front of** and **elbows ~3.5 cm behind** the straight line between their neighbours. Joints placed dead centre make the IK bend knees backward. That reads as a broken, twisted walk.
- **Move hands as one rigid piece** (hand plus all finger bones): rotate and scale the whole sub-tree from wrist to hand-tip. Placing finger bones one by one breaks the hand.
- Delete the metarig's face and breast bones if the face is painted on.
- Bind with `parent_set(type="ARMATURE_AUTO")`, then confirm every vertex got weights.
- **Stress-test every rig before animating:** arm raised in FK, elbow bent, head turned 25°, knee bent, fist closed. Render close-ups of **the face and both hands** from front, three-quarter and side, not just a thumbnail of the whole figure.

### Rigging fixes found in review

- **Boots as separate objects, and a real hem.** Bisect the trouser legs at a clean height (bmesh `bisect_plane`, `clear_inner=True`), extrude the new loop 2 cm down and 7% outward as a hem lip, then 20% inward as the hem's underside; bisect the boots 1 cm lower and extrude a dark inner collar 5 cm up and inward so it hides in the trouser. Recolour the boot top under the hem with the sheet's collar leather and turn its projection off. A ragged cut ("faces entirely below z") shows the trouser interior as dark shards.
- **Boots: split at the real ankle, with straight shin bones.** Sole and toe on `DEF-foot`, the shaft on `DEF-shin.001`, blending over the ankle, and `bbone_segments = 1` on the limb DEF bones (see "Walk cycle: ankles"). A fully rigid boot shears against the trouser at the collar; automatic weights alone fold it like a hinge.
- **Walk arms in FK, not IK.** Moving `hand_ik` while holding its rest rotation bends the wrist as the arm swings. Set `IK_FK = 1` and rotate `upper_arm_fk` (swing), with a small trailing bend on `forearm_fk`. The hand follows with a straight wrist.
- **Hand/cuff colour:** skin on vertices with summed hand weight above 0.65 (smoothstep from 0.55), the sleeve's median colour on the cuff (hand weight 0.02 to 0.55), and the front projection **fully off** on anything with hand weight above 0.08. A gap between where the cuff rule ends and where the skin rule reaches full strength leaves a pale jagged band at the wrist (the sheet's sleeve rim). Use the **same skin colour as the face**; a hand tone sampled from the sheet's hands came out far darker and more saturated than the face.
- **Despeckle the vertex colours:** any vertex more than ~35% lighter than its neighbours' average (a sheet edge pixel) takes the neighbours' colour. Three passes over the edge graph clear the pale streaks along hems and cuffs.
- **Ears:** solid skin where |x| is past the head's own width (measure it). Pull the hairline forward to just in front of the ear, or a skin patch shows beside the ear in profile.
- **Project the edge-filled sheet, not the cutout.** Where the mesh silhouette is a hair larger than the sheet's, the cutout's transparent edge pixels render as a dark halo around the ears and the cap.
- **An unused image is dropped on save.** Scripts that run later must load the sheet from its file path, not look it up in `bpy.data.images`.

### Projection and colour traps found in review

- **Never drive the projection mix from the live world normal.** When the character turns toward the camera, his side swings "forward" and the flat sheet smears across it. Store how much each vertex faces the front **once, at rest**, as a float attribute, and read that in the shader.
- **Don't let an attribute share a name with a UV map** (a UV map called `front` and an attribute called `front`). The Attribute node silently reads the UV coordinates, which in this case painted the face on the back of the head. Check `me.attributes[name].data_type` if a mask behaves strangely.
- **Don't run `recalc_face_normals` on a generated mesh** without checking. On a Hunyuan mesh it flipped most normals inward. Their exported normals were already correct.
- **Don't mirror a face half to "fix" asymmetry.** Mirroring the iris too made him cross-eyed. If one side looks wrong, find the cause first: here it was the turn, not the sheet.
- **Convert sRGB to linear exactly once, after every colour rule.** Rules added after the conversion write unconverted values, which render washed out. A region whose colour "won't change" no matter what you set is the tell.
- **Use a sky-above, ground-below world,** not one flat colour. A uniform world lights the underside of the jaw, brim and arms as brightly as the top of the cap, which looks like a white patch.
- **Projection threshold:** a wide cartoon face's sides still face ~40% forward. Use a wide blend (normal.y −0.35 to −0.75) so the face edge fades into flat side colours, and a looser threshold for the middle of the face (nose underside, lips, chin face slightly down but are seen from the front).
- **Side of the head:** flat colours, not sheet samples, with the boundaries as distance fields thresholded in the shader (see "Clean colour boundaries" below). Per-vertex region painting looked blocky and put hair under the ear lobes.
- **Ears:** find them geometrically. At each height, measure the skull width just in front of and just behind the ear, then mark anything wider in the ear's depth band as ear. Use that as a gate inside an ellipse field around the ear centre (semi-axes a few mm larger than the measured ear) so the edge is clean.
- **Boots: split, not rigid.** Sole and toe on `DEF-foot`, the boot shaft on `DEF-shin.001` (it moves with the trouser leg), blending at the real ankle. A fully rigid boot shears against the trouser at the collar.
- **Lower jaw and neck sit just below the "head" height,** so head rules miss them. Keep the neck rule to the neck itself (a cylinder about 8.5 cm around the neck axis, plus the downward-facing jaw underside). A box "z 1.20–1.30, |x| < 0.15" also covers the hood collar on both sides, which then renders skin-coloured. The collar's front-facing surfaces should keep the sheet projection (lining, shirt collar, zipper top are drawn there); only the jaw underside needs it off.

### Rigify regeneration traps (hit on an existing rig)

- **Regenerating deletes custom bones** (eye bones, extra controls) and **wipes custom properties on pose bones**. Objects bone-parented to deleted bones drop to the rig origin (eyes ended up inside the neck, looking cross-eyed). Store each such object's rest transform as a custom property on the object, and rebuild from it after every regeneration.
- **Editing the metarig in Edit Mode:** connected bones share endpoints. Compute every target from `bone.head_local`/`tail_local` first, then assign. Mapping bone by bone in place transforms shared points twice.
- **Segment bones are named like `DEF-forearm.L.001`.** Detect the side with `".L" in name`-style logic on the base name, not `name.endswith(".L")`.
- **Drivers on `hide_render`/`hide_viewport` stop evaluating** once the object is hidden, and **go stale after a regeneration**. To toggle a variant (backpack on or off), drive `show_viewport`/`show_render` of a Geometry Nodes modifier whose group outputs nothing, and recreate those drivers after every regeneration.
- **Never non-uniformly scale through a band that crosses a face or jaw.** To change proportions, scale whole regions rigidly and blend only through simple geometry, like the neck.

### Work in the user's live Blender, not in headless scripts

The user's standing rule: character work goes through the Blender MCP in their open Blender, where they can watch each change land and the result is saved in the `.blend`. A day of headless `blender -b --python` scripts produced rig and texture bugs they had to catch from renders, and scripts that had to be rebuilt every time. Only two things belong outside the live session: reading images, and the long final render (run the saved scene file with plain command-line Blender, no script, so their Blender stays free).

- Check `get_addon_status` first. If Blender isn't reachable, tell the user how to start the server (N sidebar, BlenderMCP tab, Start MCP Server) and **wait**. Don't start other work in the meantime; the user called that "jumping the gun".
- **`look` fails under flatpak Blender** (it writes to `/tmp`, which the sandbox can't share). Render check images with `bpy.ops.render.render(write_still=True)` into a folder next to the `.blend`, then read the files. A Workbench render with cavity shading (`shading.show_cavity`, single colour) is the fastest way to see sculpted edges like a cap lip.
- Make a `Lookdev` collection in the character file with the clip's sun and a check camera, and keep the world the clip uses. Judge the face under the lighting the audience will see.
- Check renders set `scene.render.filepath`; set it back to the animation's output folder (`//frames/`) before the final save, or the command-line render writes 1,350 frames under the last check image's name.
- Keep each `execute_blender_code` call under about 30 s (socket timeout). Build a 1,350-frame animation in one call (keyframe inserts are fast); render only a few check frames per call.
- Blender 5: `action.fcurves` may not exist (layered actions); `scene.copy()` makes a linked copy (same objects, own render settings, camera and world).
- `bpy.ops.wm.open_mainfile(filepath, use_scripts=True, load_ui=False)` works from inside an MCP call and the connection survives it, so the character file and the scene file can both be edited in one session (fix the character, save, reopen the scene). `use_scripts=True` avoids the Rigify UI script's "allow execution" dialog.
- **Scene file as the asset.** Build the environment and the walk once in the live file and save it as the scene file. Add a second scene (`scene.copy()`, name it `Swag`, and set `use_fake_user = True` or the save drops it: a scene no window shows has zero users) for the merch still: exclude the environment collection in its view layer, link the sun into its master collection, give it its own camera, transparent film, 5000 × 5000, frame = the final pose. Then render both from the command line: `blender -b scene.blend -S Scene -a` and `blender -b scene.blend -S Swag -o //swag_#### -f 1350`. Same objects, lights and frame, so the merch still is provably the clip's character.
- **Merch still (Fourthwall):** 5000 × 5000 PNG, RGBA, transparent film, character about 3,500–4,000 px tall. Check that semi-transparent pixels are under ~1% of the inked area (DTG prints a white underbase under any partial alpha).

### Clean colour boundaries on a coarse generated mesh

A decimated Hunyuan mesh has about 7 mm between vertices on the head. Any region painted per vertex (cap/hair, hair/skin, stubble) renders as a jagged, blocky line, and no amount of rule tweaking fixes that. Do this instead:

- **Store signed distance fields, not colours.** For each boundary compute a per-vertex value in metres that is positive inside the region (`z - cap_edge_z`, `y - hairline_y`, an ellipse for the ears). It varies linearly across each face, so the shader's **Map Range (smoothstep, From −0.004 to 0.004)** on the Attribute node's `Fac` gives a clean per-pixel line. Combine regions with `min` (intersection) and `max` (union) before storing.
- **Layer the head in the material:** skin → stubble (soft ±12 mm band whose top runs from the mouth corners back to just under the ear) → hair (side hair plus a fringe region under the brim) → ears (solid skin, override hair) → cap (over everything) → brim underside (cap × 0.62). Gate the whole head system with `z − neck_top` so the body keeps its vertex colours.
- **Find the cap edge from the surface itself.** Per vertex, roughness = mean of (1 − n·n') over edge neighbours, one smoothing pass. The generated mesh sculpts hair as grooves (rough) and the cap as a smooth shell, so a table of mean roughness by angle-around-the-head and height shows the edge: ~1.48 at the sides, ~1.445 at the back, up to the brim root (~1.59) at the front for a 1.75 m figure. A single cap height was 6–8 cm too high at the back and read as "hair bleeding into the hat".
- **The brim is cap by overhang, not height:** `max(z − cap_edge(angle), min(r − head_radius − 0.015, z − 1.52))`. Otherwise the drooping brim sides go hair-coloured, or the forehead under the brim goes orange.
- **Hairline:** sideburn front edge ~4.5 cm in front of the ear's front edge, ending at the ear's middle height; skin under the lobe; behind the ear the hair bottom slopes from the lobe down to the nape; above the ear top the hairline sweeps forward toward the fringe (about 1.5 m forward per metre up); fringe = the band between the brows' top and the brim root at the front. Painting hair "behind the sideburn line" all the way down to the neck is what wrapped hair under the ear lobes.
- **Gate the sheet projection off wherever the fields say hair** (`factor × (1 − side_hair)`). With it on, the sheet's temple and sideburn pixels stretch across the side of the head in blocky patches.
- **Fade the projection out earlier** on surfaces turning sideways (−normal.y from 0.45 to 0.80, looser for the mid-face) so the brows aren't dragged along the temple. Shift the cheek UVs about 2 cm inward only on the cheeks (|x| beyond the eyes, below the brow line); shifting the fringe too misaligns the strands.
- **Flat side skin, from a cheek patch.** Median of the sheet below the eyes and inside the face outline (for a 1.75 m figure: |x| 0.095–0.135, z 1.39–1.42). Not a per-height lookup along the face edge: that sweeps the eye white and the teeth across the side of the face as stripes. Stubble = 60% skin + 40% of the sheet's jaw sample; the first 45% hair mix read as grey.
- **Specular makes faces grey.** Principled's default specular reflects the sky at grazing angles, so the sides of the face and the chin desaturate. Set `Specular IOR Level` ≈ 0.15 and roughness ≈ 0.65 on the character material. The user saw this as "weird lighting around the jaw" and "grey on the chin and sides".

### Clothes and boots are separate objects

A generated character comes as one merged shell. Split the boots off (faces entirely below the pant hem, found with a Workbench cavity render; here z < 0.242 on a 1.75 m figure) into their own objects, extrude their top rim 6 cm up and 15% inward so it hides inside the pant leg, and give each boot its own Armature modifier: sole and toe on `DEF-foot`, shaft on `DEF-shin.001`, with a **sharp 3.5 cm crease at the ankle**. The pant leg below the knee goes fully on the lower shin so the hem never follows the foot. Because boot and trouser share no vertices nothing shears, and the boot flexes at the ankle like a real one. A boot parented rigidly to the foot bone pokes through the hem as soon as the foot tilts 30°, so don't do that for a shaft this tall.

### Eyes: measure before you move anything

- Print a per-pixel classification row across each eye (white / dark / orange / skin) and read the iris and opening extents off it. Bounding boxes of colour masks lie: the dark eye outline and the lids merge with the iris. On this sheet both irises sat hard against the inner corner, 10 px off centre, which is what reads as cross-eyed.
- Move each iris as a full disk (rim included, radius measured from the row data) by the offset that centres it in the opening, and fill the vacated strip row by row with the pixel just outside the disk on the **outer** side (white mid-eye, lid colour at the top and bottom rows). Fills from the far side pick up highlights and show as a crescent; partial-disk moves leave rim slivers; radial warps stretch the rim. Keep the corrected sheet as a separate file and point the texture node at it.
- Never shift UVs anywhere near the eyes: a 2 cm cheek shift dragged the eye whites onto the temples.

### Bangs under a cap brim

A planar projection paints the sheet's brim onto the forehead behind it, so orange lands between the fringe strands. Switch the projection off in the fringe region and paint it flat hair colour, with the bottom edge traced from the sheet: per column, the lowest dark pixel (luminance < 0.2) scanning upward from **above the eyebrows**. Measure where the brows really are first (here z 1.53 to 1.56, directly under the bangs); a scan floor inside the brow band paints the brows as hair and they vanish.

### Select body parts by bone weights, never by a position box

A box "x beyond 0.12, z 0.35 to 0.95" meant to catch the arms also contains both legs, and the hand plane then painted the shins skin-coloured. Pick arm vertices as summed `DEF-upper_arm/forearm/hand` weight above 0.2 on the right side of the body, then apply geometric rules (a cuff plane across the wrist) inside that set.

### Never call `animation_data_clear()` on a Rigify rig

It deletes the rig's **drivers** along with the keys. Every switch on the rig then silently stops working: IK/FK, IK stretch, pole vector, all of them, and nothing warns you. Symptom here: `IK_Stretch = 0` and `pole_vector = True` had no effect and the knees kept bending backward. To drop old keys, unassign or replace the action (`rig.animation_data.action = None`). If the drivers are already gone, regenerate from the metarig (`rigify_generate` with the metarig active and `data.rigify_target_rig` set); that restores them but also clears the action and the custom properties, so re-key the animation and reset `IK_FK`, `IK_Stretch`, `pole_vector` afterwards. Set `rigify_parameters.bbones = 1` on the metarig's limb bones first so the regenerated DEF bones are straight.

### Knees: check the bend direction numerically

For each frame of interest print the knee's position relative to the hip-to-ankle line (here `knee.y - (hip.y + ankle.y)/2`, negative = in front for a character facing -Y). A positive number with a bent knee means it bends backward. A knee offset of 4 cm in the metarig was not enough on a mesh whose shin leans forward, so the rest knee ended up behind the chord and the IK picked the wrong direction. Fix in pose, not by moving the joint off the mesh: `thigh_parent["pole_vector"] = True` and put `thigh_ik_target` well in front of the knee (60 cm) in armature space, keyed once.

### Measure heights from the mesh and the sheet before writing a boundary rule

Print, per 5 mm of height along the centre column, the mesh vertex count, radius and mean normal.z, next to the sheet's colour at the same height. That table showed the forehead to z 1.575, sculpted bang strands at 1.58 to 1.622, a flat downward-facing brim underside at 1.625 to 1.64 (matching the sheet's brim edge at 1.63), and brows at 1.535 to 1.565. Three earlier guesses at the cap boundary (1.505, 1.588, "by radius") each painted the strands orange or the brows as hair. Also classify pixels along a line across each boundary in the render (cap / hair / skin / cloth per row) and read the transition width in pixels; a blend of 8 mm reads as "bleed" at 5000 px.

### Crisp boundaries, one plane, in the shader

Threshold every field in the shader with a 1 to 3 mm smoothstep, never 8 to 24 mm. Where a texture hands over to a flat colour (cuff to hand), switch both the texture and the colour at the **same** field in the shader (`factor *= 1 - S(f_hand)`), not with a separate per-vertex mask: a per-vertex mask ramps over a whole face (7 mm) and the vertex colours underneath show through as a muddy band.

### Weights across a joint must blend, even on trousers

Assigning everything below the knee to one shin bone with a hard cut at the knee height produced dark triangular shards around the pant hem as soon as the knee bent 7°: faces across the cut shear because one side follows the thigh and the other the shin. Blend thigh to shin over about ±4 cm around the knee (smoothstep), and keep the boot on the separate boot object. Check a posed close-up of the hem from the front with the boots hidden to tell a weight fault from a boot fault.

### Frame the merch still from the character's real position

Place the still camera from the rig's evaluated transform in the still's own scene (`scene.view_layers[0].depsgraph`, after `scene.frame_set`), not from `rig.matrix_world`, which reflects the active scene at its own frame. Then verify the framing by measuring the rendered alpha: top and bottom margins both positive, figure height about 1.75 m worth of pixels. An 85 mm lens at 4.6 m only covers 1.95 m vertically on a square frame, so a target at z 1.25 cut the boots off; 70 mm aimed at z 0.9 from z 1.25 fits the whole figure with margins.

### Rigify knee pole: fix the rest pose, don't move the pole

If the fitted rest knee sits behind the hip-to-ankle line (print `knee.y - chord_y`; here it was 1.6 cm behind because the generated shin leans forward over a big boot), the IK bends knees backward without a pole, and Rigify places its pole control behind the leg. Turning `pole_vector` on and moving the pole in front of the knee "fixes" the bend direction but **twists the whole leg about its long axis** (pole angle is fixed at -90°). The mesh below the knee swings sideways and the trouser hem flaps out behind the leg. Fix at the source: in the metarig put the knee 1.5-2 cm in front of the hip-ankle chord, regenerate onto the same rig, and leave `pole_vector` off. Keep the walk: set `use_fake_user` on the action before `rigify_generate` (it clears animation data), then reassign the action (and the slot in Blender 5) and reset the custom properties (`IK_FK`, `IK_Stretch`).

Diagnose twist by colouring each vertex by its dominant deform bone (a FLOAT_COLOR attribute, Workbench, `color_type = "VERTEX"`) and rendering the walk frame. If the trouser (shin) and the boot shaft (lower shin) point different ways, the bones are twisted or out of reach. Numbers to print per frame: angle between the shin's and the foot's side axes (compare to rest), knee position relative to the chord, hip-to-IK-target distance against the chain length.

### Keying child bones in armature space needs the parent evaluated first

`pose_bone.matrix = M` converts M to the bone's local basis using the parent's pose **from the last depsgraph update**. Setting the torso and then the hips/chest/head in the same frame without `view_layer.update()` between them used the previous frame's torso, so the hip joint ended up 2.6 cm high and the legs over-reached. Key in hierarchy order: parent, `view_layer.update()`, children (reset their basis first, then rotate relative to the evaluated matrix), update, grandchildren. With mesh armature modifiers switched off during keying, 1,350 frames take about 15 s.

### Centre the step under the hip

The fitted rest ankle sat 7 cm in front of the hip joint. A step cycle centred on the rest ankle always lands the front foot 7 cm further forward than intended. Offset the walking foot positions back by about 80% of `hip.y - ankle.y` (scaled by the walk amplitude so the end pose is the sheet's). Then scan every frame: distance from `ORG-thigh` head to `MCH-thigh_ik_target` must stay under the chain length. Any frame above it stretches the lower shin, and the boot slides away from the trouser hem.

### GPU attribute limit: pack scalar fields

A material that reads more than about 14 vertex attributes (each Attribute node name, the colour attribute, the UV map, Generated coordinates) fails to compile in EEVEE and renders **magenta**, with no error in the log. Adding Generated coordinates for a procedural texture pushed the Wade material over. Pack scalar fields three per FLOAT_COLOR attribute (`pk_a` = cap, side hair, fringe ...), read them with one Attribute node's Vector output plus Separate XYZ, and keep a repack function to rerun after any field changes.

### Soft cast shadows in EEVEE (Blender 5)

A sun's `angle` only softens shadows when `use_shadow_jitter` is on. Without it the cap brim cast a hard horizontal line across the forehead. The sheet has that shadow painted as a gradient. Set jitter on, `shadow_filter_radius` about 3, angle about 20°. To prove a line is a shadow, render once with `light.use_shadow = False` and compare a pixel column.

### Stubble round the jaw

The projected sheet stubble ends where the jaw turns away; a flat colour there reads as a smooth pink patch. Use a procedural layer in the stubble region: Voronoi F1 distance (3D, Generated coordinates scaled to metres by the mesh dimensions, scale about 340) mapped to small dots, density varied by a noise texture, dot colour about 30% darker than the sheet's measured stubble median. Include the jaw underside: select skin-toned vertex colours facing down below the head line, not a height box (the hood collar sits at the same height).

### Walk cycle: ankles

- **Rigify limb DEF bones are 10-segment bendy bones.** The lower shin curves toward the foot, so a boot shaft bends like rubber at every step. Set `bbone_segments = 1` on `DEF-thigh*`, `DEF-shin*`, `DEF-upper_arm*`, `DEF-forearm*`.
- **Step length must fit the legs.** 0.56 m legs with a 0.6 m step needed IK stretch to reach, which made the legs rubbery and dragged the boots. Set `IK_Stretch = 0` on `thigh_parent.*` and keep the step near 0.45 × leg length (speed 0.9 m/s, 32-frame cycle here). Gait references: the body is lowest just after contact (the "down" pose) and highest at passing; the foot slaps down in the first 10% of the cycle, the ankle dorsiflexes to 5–15° after heel lift, then plantarflexes quickly for push-off.
- **Use the foot-roll control, `foot_heel_ik.<side>`.** +X rolls onto the ball (ankle rises and moves forward, toes stay planted); −X rocks onto the heel (toe up). Keep `foot_ik` at its rest rotation and on the ground through the stance; let the roll do the ankle. Per cycle fraction p: heel strike −14° at p = 0 easing to 0 by 0.10, flat to 0.40, 0 → +32° by toe-off at 0.60, back to 0 by 0.78, then to −14° by 1.0 for the next strike. Without the roll the foot stays flat until it leaves the ground and the shin leans 45° over it, which is what "ankles bending in odd ways" meant.
- Check it with a side view of the feet at six frames across one cycle and a front three-quarter at three; the heel-up push-off should be visible on the rear foot.

### Before telling the user it's done

Put a frame from the on-screen clip next to the merch render and ask: **is that the same character, yes or no?** Also check close-ups of the face from front, three-quarter and side, both hands, the back, and a side view of the walk. The user will spot each of those defects in seconds.
