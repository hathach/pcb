# pcb — PCB projects home

Each board is a self-contained git repo in its own directory (gitignored
here); this umbrella repo versions the shared knowledge, footprints, and
tooling that future boards reuse.

## Layout

| Entry                             | What                                                                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pico2_trace_motherboard/`        | Board #1: Pico 2 SWD+ETM trace carrier + TinyUSB dev/test bench (RP2350, 2-layer). Ordered: JLCPCB **W2026073018593887**, 2026-07-30, 5 PCB / 2 assembled, $81.27. |
| `docs/pipeline.md`                | The netlist-driven KiCad pipeline + gate battery + how to bootstrap board #2.                                                                                      |
| `docs/kicad-pcbnew-facts.md`      | Verified KiCad 9 scripting landmines (pcbnew API, kicad-cli, footprints).                                                                                          |
| `docs/parts-palette.md`           | LCSC/JLC-verified parts with tiers + JLC fee behavior.                                                                                                             |
| `docs/PICO2_TRACE_PCB_HANDOFF.md` | Origin brief for board #1 (fly-wire measurements, requirements).                                                                                                   |
| `lib/pcb.pretty/`                 | Audited shared footprints: USB-C C165948 lands (power-only + USB2-device renumbers), FTSH-110/105 1.27mm headers. Copy into each board's local `.pretty`.          |
| `tools/jlc-cdp/`                  | Chrome-DevTools JLCPCB ordering driver + wizard-trap playbook.                                                                                                     |
| `tools/board_semantic_compare.py` | Prove two `.kicad_pcb` are geometrically identical (regen gate).                                                                                                   |
| `tools/align_md_tables.py`        | Markdown table column aligner (house style).                                                                                                                       |

## Starting a new board

Read `docs/pipeline.md` — short version: copy `pico2_trace_motherboard/hw/`
wholesale, gut the board-specific tables, keep every helper and gate, seed
footprints from `lib/pcb.pretty/`, and regenerate-never-hand-nudge.
