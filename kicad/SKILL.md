---
name: kicad
description: Design TrailCurrent electronics in KiCad 9 through the `kicad` MCP server (TrailCurrent KiCad Tools) — schematics with hierarchical sheets, ERC and design checks, SPICE simulation, symbol/footprint search, creation, import and audit, PCB layout (update from schematic, outline, stackup, manufacturer design rules, placement, routing, zones), DRC, renders and manufacturing packages. ALL schematic and board edits go through the MCP tools; never hand-edit .kicad_sch / .kicad_pcb / .kicad_sym files. Use whenever a task touches a KiCad project, a part, a footprint, a board, or fab outputs.
---

# KiCad (via the `kicad` MCP server)

The tools come from TrailCurrent KiCad Tools (`TrailCurrent/Utilities/MCPs/kicad`).
They work on files and verify every change with KiCad itself (kicad-cli netlist,
ERC, DRC). If a tool is missing or wrong, fix the MCP (with a test in `tests/`) —
do not fall back to editing S-expressions by hand.

## Conventions

- Millimetres and degrees. Schematic Y grows **down** from the page's top-left.
  Keep symbols on the 1.27 mm grid (tools snap by default). Use an A4 page's
  usable area roughly x 20–270, y 20–190.
- Pins: `REF.PIN` — number or unique name (`U1.3`, `U1.SDA`). PCB pads: `REF.PAD`.
- New symbols return their pins as `number:name@x,y->dx,dy` (`->` is the outward
  direction a wire should leave in).
- Every write snapshots the file first: `file_snapshots(file, "list"/"restore")`.
- A file open in KiCad is refused unless the edit can go live; ask the user to
  close the schematic (or File → Revert after) rather than passing `allow_open`.

## Schematic loop

1. `project_create` or `project_info`.
2. Find parts: `lib_search_symbols` → `lib_symbol_info` (pins, units, filters).
   Footprints: `lib_search_footprints` / `sch_suggest_footprints`.
3. Build in **one** `sch_edit` call per sheet: `add_symbol`, then connections.
   Prefer `label_pin` (short stub + net label) for anything not adjacent; use
   `connect` only for short, obvious wires; `power` puts GND/+3V3/… on a pin
   facing away from it; `no_connect` every intentionally unused pin.
4. `sch_annotate`.
5. **Verify, don't assume:** `sch_netlist` (KiCad's real connectivity),
   `sch_erc` (aim for 0 errors), `sch_check` (footprints exist, symbol pins
   match footprint pads, unconnected pins, sheet pin/label parity, required
   fields), and look at `sch_render`'s PNG.

Hierarchy: `sch_add_sheet(name, file, pins=[{name, shape, side}])` creates the
sheet, its pins, the child file and the child's hierarchical labels. In the
child, `label_pin(pin, net=<sheet pin name>)` moves that hierarchical label onto
the pin. Power symbols (GND, +3V3 …) are global across sheets. Reusing the same
file in another `sch_add_sheet` makes a second instance; annotate afterwards.

## TrailCurrent part conventions

- Boards are assembled by **NextPCB**, which buys parts by manufacturer part number. Every
  BOM part needs `Manufacturer_Name` + `Manufacturer_Part_Number` (exact, orderable MPN).
  LCSC numbers are no longer used. `sch_check(required_fields=["Manufacturer_Part_Number"])`
  before an order; `lib_check_sourcing` checks a whole library against NextPCB's catalog.
- **Prefer parts from the `NextPCB_*` libraries** (`nextpcb_libraries` lists them): they are
  order-ready — exact MPN in NextPCB's catalog, catalog symbol + footprint, pins = pads, KiCad
  loads them, KiCad DRC clean, fields stamped (`NextPCB_Verified`). A board built only from
  them needs no manual part checks before ordering.
- New parts, in this order:
  1. `parts_search` → `parts_info` → `parts_add` (order-ready import into
     `NextPCB_<category>`; refused, with the reason, if any check fails). Confirm against the
     datasheet: catalog data is sometimes partly in Chinese.
  2. Refused because the catalog has no KiCad files: make the part in
     `TrailCurrentSymbolLibrary` (`lib_create_symbol` / `lib_create_footprint`, or
     `lib_footprint_wizard_build`) and `lib_set_fields` the catalog's manufacturer + MPN.
  Then `lib_audit`.
- Ordering: `fab_package(project, "nextpcb-standard")`; its `order_check.order_ready` must be
  true (every BOM line has an MPN NextPCB's catalog knows). People use the **NextPCB order
  files** button in the PCB editor for the same thing.
- The catalog is a free service that blocks busy addresses (error 400010, "please log in").
  Don't loop `parts_search` over many parts: check lists with `parts_match` /
  `lib_check_sourcing` (one request) and reuse results. If it is limited, stop and tell
  the user; the client refuses for an hour by itself.
- Prototype passives: `Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder`,
  `Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder` (still give them an MPN).
- Shared parts live in TrailCurrentKiCADLibraries (`TrailCurrentSymbolLibrary`,
  `TrailCurrentFootprints`, models under `${TRAILCURRENT_3DMODEL_DIR}/<category>/`).
  Never edit sym-lib-table / fp-lib-table / kicad_common.json — if a library is
  missing in KiCad, tell the user to run TrailCurrentKiCADLibraries/install.sh.
- People use the **NextPCB parts** button (schematic and PCB editors) for the same search.

## PCB loop

1. `pcb_update_from_schematic` (F8 equivalent) — new parts land beside the board.
2. `pcb_set_outline`, `pcb_set_layers` (stackup), `pcb_apply_fab_profile`
   (`pcb_fab_profiles` lists JLCPCB/PCBWay/NextPCB/OSH Park/AISLER/Eurocircuits).
3. `pcb_arrange` for a first placement, then `pcb_place` to refine (connectors
   at edges, decoupling caps next to their IC pins — use `pcb_list_footprints(pads=true)`).
4. `pcb_add_zone` (GND pour), route with `pcb_autoroute` (Freerouting) or
   `pcb_add_tracks` / `pcb_route` (straight lines — DRC after).
5. `pcb_drc` until errors and unrouted are 0; `pcb_render` (2d/3d) and look.
6. `fab_package(project, profile)` → `Product/<Name>/EDA/manufacturing/<profile>/`
   (NextPCB profiles write NextPCB's BOM/placement columns and warn about lines without an MPN).

Live: with KiCad open and its API on (Preferences → Plugins → Enable KiCad API),
placement/track tools act in the editor (undoable). `live_status` lists the
open boards by full path. KiCad 9's API cannot open a board — ask the user to
open it in the PCB editor. File-editing tools on an open board make KiCad save,
then reload (their unsaved hand edits get saved too — say so before doing it).
Undo/redo: `live_run_action("common.Interactive.undo")`.
Nets: write them as in the schematic (`A` finds the root-sheet net `/A`); an
unknown net is refused, never created.
Escape hatches: `pcb_python`, `kicad_cli`, `live_run_action` (`kicad_actions`),
`sch_raw`.

## Known traps

- KiCad silently ignores the whole `.kicad_dru` if one rule is malformed — run
  `pcb_drc` after `pcb_custom_rules`.
- `pcb_drc` refills zones first (it saves the board).
- `lib_footprint_mismatch` warnings on stock footprints are not caused by the tools.
- `sim_run` needs ngspice installed; R/C/L simulate from their value, sources
  need `sim_set_model` (`Simulation_SPICE:VDC` / `VPULSE` / `VSIN` symbols).
  `.ac` needs `ac=1` in a source's params; `no_ac_signal` lists nodes with
  nothing to show (DC rails).
- `pcb_autoroute` picks the newest Freerouting jar an installed Java can run;
  `kicad_setup(component="freerouting")` shows which. Releases from 2.2.0 on
  need Java 25.
- After `lib_import_lcsc` / `lib_import_archive`, read `remaining_issues` and
  `warnings`, and `lib_render` the part. EasyEDA pins come in as
  `unspecified`; rebuild the symbol with real pin types if ERC matters.
