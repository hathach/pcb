# Netlist-driven KiCad pipeline — how to start the next board

The reference implementation is `pico2_trace_motherboard/hw/` (proven: the
board regenerates from an empty file byte-equivalently, survived a
three-reviewer pre-order audit, and shipped as JLC W2026073018593887).

## Architecture

One Python model drives everything:

```
hw/netlist.py     PARTS (Part dataclass: ref/value/fp_class/pins/nc/dnp/padmap)
                  + net assignments + graph helpers (series_between,
                  divider_ratio, net_pins) + emit_netlist() -> .net
hw/fp_lib.py      part class -> (library, footprint) resolution table
hw/build_board.py pcbnew driver: footprints, net wiring (per-pad assert),
                  outline, mounting holes, netclasses (+ SaveProject!)
hw/place.py       placement coordinate table + silk labels
hw/route_trace.py probe-based routing (helpers: _pad/_pos/_add_track/
                  _add_via/_add_path_once/_track_exists)
hw/pour.py        GND zones both layers + stitching vias; fill in own process
hw/gen_sch.py     schematic generator (generic N-pin symbols, ERC-clean)
                  -- REQUIRES numeric pad names everywhere
hw/checks.py      pytest gates + --compare-netlists (semantic differ)
```

## Bootstrapping board #2

1. `mkdir <board> && cd <board> && git init`; copy `hw/` wholesale from
   pico2_trace_motherboard plus `fp-lib-table`, `sym-lib-table`,
   `.gitignore`, `tools/align_md_tables.py`.
2. Gut the board-specific content: PARTS/net tables in `netlist.py`, the
   POS/FUNC_LABELS tables in `place.py`, every routing function in
   `route_trace.py` below the helper layer, the via lists in `pour.py`,
   the assertions in `checks.py`.
3. Keep: all helpers, the pipeline `main()`s, the gate structure,
   `gen_sch.py` untouched.
4. Shared audited footprints: point `fp-lib-table` at a local `.pretty`
   seeded from `~/code/pcb/lib/pcb.pretty/` (copy, keep the board
   self-contained).
5. Regenerate loop (identical for every board):

```bash
rm <board>.kicad_pcb && python3 -c "import pcbnew; pcbnew.SaveBoard('<board>.kicad_pcb', pcbnew.NewBoard('<board>.kicad_pcb'))"
python3 hw/build_board.py --place
python3 hw/route_trace.py
python3 hw/pour.py && python3 hw/pour.py --fill
```

## Gate battery (run after every change)

1. DRC: `kicad-cli pcb drc --format json` → parse JSON; record the board's
   own warning baseline explicitly; unconnected must be 0.
2. `python3 -m pytest hw/checks.py -q` — put net-level regression guards
   here (e.g. `series_between("J8_CC1","GND","R_CC1")`).
3. Netlist parity: `emit_netlist()` + `python3 -m hw.gen_sch` +
   `kicad-cli sch export netlist` + `hw/checks.py --compare-netlists`.
4. GND-pour union-find: ring-sampled (radius+0.45mm) over vias + tracks +
   pads edge classes; must be exactly 1 component. Centre-point sampling
   false-negatives on thermal gaps — always ring-sample.
5. Regen-equivalence when refactoring scripts:
   `python3 ~/code/pcb/tools/board_semantic_compare.py old.kicad_pcb new.kicad_pcb`
   → must print IDENTICAL.

## Non-negotiables learned the expensive way

- Regenerate, never hand-nudge: any hand edit dies on the next regen.
- Read `docs/kicad-pcbnew-facts.md` before writing any pcbnew script.
- Probe pad positions in routing code (`_pos(_pad(...))`) — never
  hardcode a pad position that the footprint defines.
- Multi-pad numbers (shield legs, stacked USB-C contacts) are legal and
  useful; `_pad()` returns the first match — select deterministically
  when it matters.
- Before ordering: adversarial multi-agent review of (a) footprint pad
  maps vs datasheet, (b) live-board pad→net dump, (c) BOM/CPL/gerber
  package freshness. Template: pico2_trace_motherboard commit `0218f22`'s
  audit. The user clicks Pay.
