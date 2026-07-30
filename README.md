# pcb — PCB projects home

Each board is a self-contained git repo in its own directory. This tree is
the reference base for future boards.

| Entry                        | What                                                                     |
| ---------------------------- | ------------------------------------------------------------------------ |
| `pico2_trace_motherboard/`   | Pico 2 SWD+ETM trace carrier + TinyUSB dev/test bench (RP2350, 2-layer). First board ordered from this tree: JLCPCB **W2026073018593887**, 2026-07-30, 5 PCB / 2 assembled, $81.27. |
| `PICO2_TRACE_PCB_HANDOFF.md` | The origin brief for that board (fly-wire rig measurements, requirements). |
| `tools/jlc-cdp/`             | Chrome-DevTools driver + JLCPCB wizard playbook used to place the order.  |

## What to reuse from pico2_trace_motherboard

- **Netlist-driven KiCad flow** (`hw/`): parts+nets as Python single source
  of truth → pcbnew scripting for board build, placement, routing, pour →
  `kicad-cli` DRC/ERC gates. The board file is fully regenerable from an
  empty file (proven byte-equivalent). See `PLAN.md` "Verified environment
  facts" for the pcbnew API landmines (ZONE_FILLER segfault, BOARD.Remove
  corruption, netclass persistence, ...).
- **Gate battery**: parsed-JSON DRC (never exit codes), model↔schematic
  netlist parity, GND-pour union-find (ring-sampled, 3 edge classes),
  pytest checks with net-level regression guards.
- **Ordering playbook**: `docs/ORDERING.md` (JLC specifics: Economic PCBA
  constraints, Extended-fee behavior, part-decision tables) and
  `tools/jlc-cdp/README.md` (wizard automation traps).
- **Custom Type-C footprints** (`pico2_trace.pretty/USB_C_{PWR,DEV}_HRO…`):
  renumbered HRO TYPE-C-31-M-12 lands (LCSC C165948) for power-only and
  USB2-device ports, three-reviewer audited.
