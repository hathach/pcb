# KiCad 9.0.2 scripting — verified facts (obey these)

Hard-won on pico2_trace_motherboard (2026-07); every item was hit for real.
Re-verify only if the KiCad version changes.

## pcbnew API landmines

- `pcbnew.SaveBoard` does **not** persist net classes (they live in
  `.kicad_pro`) — after setting them call
  `pcbnew.GetSettingsManager().SaveProject()`.
- `ZONE_FILLER(b).Fill()` **segfaults on an in-memory-mutated board** — only
  fill a board freshly `LoadBoard`-ed from disk, in its own process.
- `BOARD.Remove()` on a populated board corrupts it — design scripts to be
  idempotent (skip-if-present) instead of removing and re-adding.
- `VECTOR2I.Distance()` raises `TypeError`; use `(p1 - p2).EuclideanNorm()`.
- `GetUnconnectedCount(False)` requires the arg.
- `pcbnew.AddHole` does not exist — use `MountingHole` footprints.
- `b.GetNetClasses()` iterates **wxString keys**:
  `{str(k) for k in b.GetNetClasses()}`.
- `LoadBoard` returns `None` (no raise) on a bad path — assert non-None.
- `PCB_VIA.GetWidth()` needs a layer argument in v9.
- Board-level silk text is not exposed as `PCB_TEXT` via SWIG in all paths —
  parse `gr_text` from the file when auditing silk.
- Footprint rotation: for 0402 passives, rot 90 puts pad 1 **south**,
  rot 270 puts it **north** (probe, never assume).

## kicad-cli

- `pcb drc --exit-code-violations` returns **exit 5** on *any* violation
  including warnings, `unconnected_items`, and the empty-board
  `invalid_outline`. Gate on a **parsed `--format json` report**, never exit
  codes or stdout text.
- `--schematic-parity` is a bare boolean flag and needs footprint↔symbol
  UUID links that scripted footprints don't have — treat as advisory; rely
  on a netlist compare instead.
- Gerber export emits drawing items in container order — a regenerated
  board produces textual gerber diffs with identical geometry. Compare
  semantically (`tools/board_semantic_compare.py`), not textually.

## Stock footprint facts

- `Module:RaspberryPi_Pico_Common_THT` = the inner-socket land pattern, 40
  THT pads numbered "1"–"40" by physical pin. Do not add separate inner
  sockets on top of it.
- `PinSocket_1x20_P2.54mm_Vertical` (and the PinHeader THT families) anchor
  at **pin 1**; the `_SMD_Pin1Left` variants anchor at the row centre —
  re-derive placement when switching.
- Schematic generators keyed to numeric pads require local renumbered
  copies of any stock footprint with alphanumeric pads (USB-C `A1..B12`,
  etc.) — see `lib/pcb.pretty/` for audited examples.

## WebGL / browser caveats (JLC viewers)

- Heavy WebGL pages stall CDP `Page.captureScreenshot`; canvas
  `toDataURL` returns black without `preserveDrawingBuffer`. Verify
  placement in a visible window or via JLC's Confirm-Parts-Placement
  service.
