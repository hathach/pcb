# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# PCB Projects — Agent Instructions

This tree is the home for hathach's PCB designs — a **monorepo,
Adafruit-style**: every board lives in its own directory of this single
repo (github.com/hathach/pcb), alongside the shared docs, footprint lib,
and tools. Read `README.md` for the inventory, and the board's
own docs before touching anything. Before any pcbnew scripting read
`docs/kicad-pcbnew-facts.md`; to start a new board read `docs/pipeline.md`;
parts sourcing starts at `docs/parts-palette.md`; shared audited footprints
live in `lib/pcb.pretty/`.

## Ground rules

- **Design style:** follow Adafruit practices — the rulebook is
  `~/code/adafruit/MBAdafruitBoards/SCHEMATIC_LAYOUT_RULES_AND_TOOLS.md`
  (their Eagle libs sit beside it). Reuse their sub-circuits when a similar
  circuit exists.
- **Verify from primary sources:** datasheets/reference manuals live in the
  Calibre library at `~/Documents/calibre-library` — check there before
  asserting pinouts, register facts, or connector pinouts from memory.
- **Markdown tables:** always align columns in the raw source
  (`tools/align_md_tables.py`).
- **Fab costs real money:** before any order, run an adversarial multi-agent
  review of footprints, live-board wiring, and the fab package (the
  2026-07-30 pre-order audit in pico2_trace_motherboard is the template),
  and get the user's explicit go for payment — the user always clicks Pay.

## pico2_trace_motherboard (first board, the reference)

Pico 2 SWD+ETM trace carrier + TinyUSB dev/test bench. RP2350, 2-layer
92×64 mm. **Ordered:** JLCPCB `W2026073018593887` (2026-07-30, 5 PCB /
2 assembled, $81.27, both USB ports Type-C C165948). Fab provenance:
`fab/MANIFEST.txt`. Bring-up when boards arrive: `docs/BRINGUP.md`
(first-power checklist, GP27 VBUS-detect ≥2 V threshold note, trace ladder
48→80→120→150 MHz core; RP2350 TPIU is DDR at clk_sys/2, J-Trace V2 tops
out at 150 MHz TRACECLK ⇒ 300 MHz core practical max).

### Architecture — netlist-driven KiCad (reuse for new boards)

Single source of truth `hw/netlist.py` (parts + pin→net) drives everything:

```bash
cd pico2_trace_motherboard
rm pico2_trace.kicad_pcb && python3 -c "import pcbnew; pcbnew.SaveBoard('pico2_trace.kicad_pcb', pcbnew.NewBoard('pico2_trace.kicad_pcb'))"
python3 hw/build_board.py --place   # footprints, nets, outline, placement, silk
python3 hw/route_trace.py           # all copper (probe-based, hand-derived lanes)
python3 hw/pour.py && python3 hw/pour.py --fill   # GND zones (fill MUST be its own process)
```

The board regenerates from an empty file **byte-equivalently** (proven by
semantic compare) — regenerate, never hand-nudge. Gate battery after any
change:

1. `kicad-cli pcb drc --format json` → parse JSON (never exit codes);
   baseline = exactly 2 `silk_edge_clearance` warnings on PICO, 0 unconnected.
2. `python3 -m pytest hw/checks.py -q` (includes net-level regression guards;
   single test: `python3 -m pytest hw/checks.py::test_usb_nets -q`).
3. Netlist parity: emit via `hw.netlist.emit_netlist`, `python3 -m hw.gen_sch`,
   `kicad-cli sch export netlist`, then
   `python3 hw/checks.py --compare-netlists <sch.net> pico2_trace.net`.
   ERC (`kicad-cli sch erc --format json`) baseline = warnings only, all
   `endpoint_off_grid`.
4. GND-pour union-find gate: ring-sampled (radius+0.45 mm) over vias +
   tracks + pads edge classes, must be exactly 1 component. (Inline pcbnew
   script — the method is recorded in `.superpowers/sdd/progress.md`; DRC's
   `unconnected_items == 0` is the first-line check, the union-find catches
   pad-less orphan islands DRC can miss.)

Visual check: `kicad-cli pcb render --side top -o render.png pico2_trace.kicad_pcb`.

pcbnew API landmines are recorded in `PLAN.md` → "Verified environment
facts" (ZONE_FILLER segfaults in-memory, BOARD.Remove corrupts populated
boards, netclasses need SaveProject, etc.) — read before scripting.
`hw/gen_sch.py` requires NUMERIC pad names: stock footprints with
alphanumeric pads (e.g. USB-C A1..B12) get local renumbered copies in
`pico2_trace.pretty/` (see `usb_c_pwr`/`usb_c_dev`, three-reviewer audited).

### Ordering at JLCPCB

- Playbook: `docs/ORDERING.md` (specs, Economic-PCBA constraints,
  Extended-fee behavior: deselected matched lines still pay the loading fee;
  any THT line brings back ~$7 hand-solder+manual labor).
- Browser automation: `tools/jlc-cdp/` — CDP driver + every wizard trap
  (assembly detaches on gerber re-upload, cart forks on save, cascader
  needs synthetic pointer-event sequences, CPL stays in KiCad y-down
  frame — do NOT convert to pos.csv frame).
- Upload staging convention: `~/Desktop/jlcpcb-order/` (zip + BOM_jlc.csv +
  CPL_jlc.csv).
