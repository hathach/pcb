# Pico 2 Trace Motherboard — Bring-Up Note

## Toolchain

**Verified 2026-07-24, KiCad 9.0.2.**

- `kicad-cli version` → `9.0.2`; `python3 -c "import pcbnew; print(pcbnew.Version())"` → `9.0.2` (system Python, no venv needed for `pcbnew`).
- Board scaffold: `pcbnew.BOARD()` scripted in-memory, placeholder 65×34 mm `Edge.Cuts` rectangle added, `SetCopperLayerCount(2)`, saved with `pcbnew.SaveBoard("pico2_trace.kicad_pcb", b)` — this also wrote a complete `pico2_trace.kicad_pro` / `.kicad_prl` (per `PLAN.md`, never hand-write the `.kicad_pro`).
- Baseline DRC gate (parsed JSON, per `PLAN.md` "Verified environment facts" — never trust exit code or stdout text):
  ```
  kicad-cli pcb drc --format json -o /tmp/drc.json pico2_trace.kicad_pcb
  python3 -c "import json;v=json.load(open('/tmp/drc.json'))['violations'];print('violations:',[x['type'] for x in v])"
  ```
  Result: `violations: []` (exit 0). Confirms the placeholder outline is required — DRC on an outline-less board would report `invalid_outline` and exit 5.

### SKiDL spike (Step 3/4 of Task 1)

Goal: determine whether SKiDL's `KICAD9` schematic target can be used to auto-generate the project schematic from `hw/netlist.py` later in the plan, or whether the schematic must be hand-drawn in eeschema.

- `python3 -m venv .venv && . .venv/bin/activate`
- `pip install -q skidl kinet2pcb kinparse` → succeeded (no `PIP_FAILED`). Installed `skidl==2.2.3` (`kinet2pcb`, `kinparse` also installed).
- Ran the generation spike inside the venv with `KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols` exported:
  ```python
  import skidl
  from skidl import Part, Net, set_default_tool, KICAD9, generate_schematic
  set_default_tool(KICAD9)
  r1 = Part("Device", "R", value="8.2k", footprint="Resistor_SMD:R_0402_1005Metric")
  n = Net("N1"); n += r1[1]
  generate_schematic()
  ```
  Output: `SKIDL_GEN_OK ['skidl.kicad_sch']` — SKiDL wrote `./skidl.kicad_sch` (fixed filename `skidl.kicad_sch`, not project-name-based — a known SKiDL quirk, see below). SKiDL's own internal ERC pass on the generated file reported 1 error (`pin_not_connected` — expected, pin 2 of R1 was deliberately left dangling in the spike) and 2 warnings (`global_label_dangling`, `lib_symbol_mismatch` — a benign local-vs-library symbol note).
- Smoke-tested the generated file with the real KiCad 9 tool (outside the venv, system `kicad-cli`):
  ```
  kicad-cli sch erc skidl.kicad_sch; echo exit=$?
  ```
  Output: `Found 3 violations` / `exit=0` — matches SKiDL's own ERC count exactly (1 error + 2 warnings), and **`kicad-cli` parsed the file without a crash**. This is the pass/fail signal from the Task 1 brief: exit 0/5 and no parse crash → `auto`.

**Decision: `SCHEMATIC_MODE=auto`.** SKiDL 2.2.3 + `KICAD9` target produces a `.kicad_sch` that KiCad 9.0.2's own `kicad-cli sch erc` reads and checks cleanly. Later tasks may drive schematic generation from `hw/netlist.py` via SKiDL instead of hand-drawing in eeschema, falling back to manual drawing only for parts SKiDL can't express (see caveats below).

**Known SKiDL caveats to carry forward:**
- Output is a **flat** schematic (no hierarchical sheets) with **crude auto-placement** — fine for ERC/netlist purposes, not for a human-reviewable layout as-is.
- Output filename is fixed to `./skidl.kicad_sch` (actually `./<script-derived-name>.kicad_sch`, not the project name) — must be renamed/moved into place by the caller.
- Custom (non-stock) symbols must already exist in a resolvable library before generation; SKiDL does not create new symbols.

The spike's scratch outputs (`skidl.kicad_sch`, `skidl-erc.rpt`, `skidl.erc`, `skidl.log`, `skidl_REPL.*`) and the `.venv/` used to run it are not committed — see `.gitignore`.
