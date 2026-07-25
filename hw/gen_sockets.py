#!/usr/bin/env python3
"""Generate the two custom SMT socket footprints (Task 14d, THT elimination).

pico2_trace:PicoSocket_2x20_SMD_ThruHole -- Adafruit-5905-style SMT female
    carrier for the Pico: 40 numbered SMD pads ("1".."40", matching the
    stock RaspberryPi_Pico_Common_THT pin numbering exactly -- the
    netlist/schematic/routing model keys off these numbers) offset
    laterally outward from each nominal pin position, plus 40 NPTH
    clearance holes AT the nominal positions so the Pico's own male header
    pins still pass through the board (this is a *socket*, not a
    solder-the-Pico-down footprint like stock RaspberryPi_Pico_Common_SMD).

pico2_trace:PinSocket_1x20_SMD_ThruHole -- same treatment for the J1B/J2B
    breakout rows (20 numbered SMD pads + 20 NPTH clearance holes).

Both grids are derived programmatically from the stock footprints they
replace (pad coordinates read verbatim, never re-typed by hand) so the
socket lines up with a real Pico / real 0.1" header pins:
  - Module.pretty/RaspberryPi_Pico_Common_THT.kicad_mod (pads "1".."40")
  - Connector_PinSocket_2.54mm.pretty/PinSocket_1x20_P2.54mm_Vertical.kicad_mod
    (pads "1".."20")

Geometry decisions (full writeup: .superpowers/sdd/task-14d-report.md):
  - NPTH clearance hole: 1.15mm drill, np_thru_hole circle, "*.Mask" only
    (no copper) -- at the pin's exact nominal position.
  - SMD pad: 1.0 x 2.2mm rectangle (1.0mm = radial width away from the
    hole, 2.2mm = length along the pitch direction -- 0.34mm gap to the
    neighbouring pad at 2.54mm pitch), F.Cu+F.Mask+F.Paste, offset outward
    (away from the module's own centreline) so its inner edge sits 0.6mm
    clear of the hole's edge -- machine-solderable and routable without
    fouling the hole.
  - F.SilkS body outline per row + a pin-1 dot + a "USB END" text marker
    (Pico socket only) so orientation is unambiguous without the pads
    themselves carrying a shape cue.
  - F.CrtYd: one rectangle per physical strip (2 for the Pico socket, 1 for
    the breakout), covering the hole+pad envelope with a 0.3mm margin plus
    a half-pitch (1.27mm) overhang at each end -- matches the stock THT
    footprints' own courtyard-overhang convention.

Run: python3 hw/gen_sockets.py   (writes into pico2_trace.pretty/; safe to
re-run -- always regenerates both files from scratch, no in-place editing).
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "pico2_trace.pretty")

PICO_SRC = "/usr/share/kicad/footprints/Module.pretty/RaspberryPi_Pico_Common_THT.kicad_mod"
BREAKOUT_SRC = "/usr/share/kicad/footprints/Connector_PinSocket_2.54mm.pretty/PinSocket_1x20_P2.54mm_Vertical.kicad_mod"

NPTH_DRILL_MM = 1.15
PAD_W_MM = 1.0             # radial (outward) pad dimension
PAD_L_MM = 2.2             # along-pitch pad dimension
PAD_GAP_MM = 0.6           # hole edge -> pad inner edge clearance
CRTYD_MARGIN_MM = 0.3
CRTYD_OVERHANG_MM = 1.27   # half pitch; matches stock THT courtyard convention

_PAD_RE = re.compile(r'\(pad "(\d+)" thru_hole \w+\s*\n\s*\(at (-?[\d.]+) (-?[\d.]+)\)')


def _parse_pad_positions(path: str) -> dict[str, tuple[float, float]]:
    """{pad_number: (x, y)} for every plated thru_hole pad in a stock .kicad_mod."""
    text = open(path).read()
    positions = {}
    for num, x, y in _PAD_RE.findall(text):
        positions[num] = (float(x), float(y))
    assert positions, f"no thru_hole pads parsed from {path}"
    return positions


def _fmt(v: float) -> str:
    """Trim to KiCad's usual float style: no trailing .0, no float noise."""
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _smd_pad(num: str, x: float, y: float, outward: str) -> str:
    """outward: 'x-' or 'x+' -- which side of the hole the pad sits on."""
    sign = -1.0 if outward == "x-" else 1.0
    pad_cx = x + sign * (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM / 2)
    return (
        f'\t(pad "{num}" smd rect\n'
        f"\t\t(at {_fmt(pad_cx)} {_fmt(y)})\n"
        f"\t\t(size {_fmt(PAD_W_MM)} {_fmt(PAD_L_MM)})\n"
        f'\t\t(layers "F.Cu" "F.Mask" "F.Paste")\n'
        f"\t)\n"
    )


def _npth_pad(x: float, y: float) -> str:
    return (
        f'\t(pad "" np_thru_hole circle\n'
        f"\t\t(at {_fmt(x)} {_fmt(y)})\n"
        f"\t\t(size {_fmt(NPTH_DRILL_MM)} {_fmt(NPTH_DRILL_MM)})\n"
        f"\t\t(drill {_fmt(NPTH_DRILL_MM)})\n"
        f'\t\t(layers "*.Mask")\n'
        f"\t)\n"
    )


def _silk_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    lines = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        lines.append(
            "\t(fp_line\n"
            f"\t\t(start {_fmt(ax)} {_fmt(ay)})\n"
            f"\t\t(end {_fmt(bx)} {_fmt(by)})\n"
            "\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type solid)\n\t\t)\n"
            '\t\t(layer "F.SilkS")\n'
            "\t)\n"
        )
    return "".join(lines)


def _crtyd_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    lines = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        lines.append(
            "\t(fp_line\n"
            f"\t\t(start {_fmt(ax)} {_fmt(ay)})\n"
            f"\t\t(end {_fmt(bx)} {_fmt(by)})\n"
            "\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n"
            '\t\t(layer "F.CrtYd")\n'
            "\t)\n"
        )
    return "".join(lines)


def _pin1_dot(x: float, y: float) -> str:
    """Small filled silk dot next to pin 1, offset further outward than the
    pad so it doesn't collide with solder mask -- same visual role as the
    stock Pico/FTSH footprints' own pin-1 marks."""
    cx = x - (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM + 0.4)
    return (
        "\t(fp_circle\n"
        f"\t\t(center {_fmt(cx)} {_fmt(y)})\n"
        f"\t\t(end {_fmt(cx + 0.25)} {_fmt(y)})\n"
        "\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type solid)\n\t\t)\n"
        "\t\t(fill solid)\n"
        '\t\t(layer "F.SilkS")\n'
        "\t)\n"
    )


def _property(name: str, value: str, x: float, y: float, layer: str) -> str:
    return (
        f'\t(property "{name}" "{value}"\n'
        f"\t\t(at {_fmt(x)} {_fmt(y)} 0)\n"
        f'\t\t(layer "{layer}")\n'
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n"
        "\t)\n"
    )


def gen_pico_socket() -> str:
    pins = _parse_pad_positions(PICO_SRC)
    row1 = sorted(int(n) for n in pins if pins[n][0] == min(x for x, _ in pins.values()))
    row2 = sorted(int(n) for n in pins if pins[n][0] == max(x for x, _ in pins.values()))
    x_left = min(x for x, _ in pins.values())
    x_right = max(x for x, _ in pins.values())
    y_lo = min(y for _, y in pins.values())
    y_hi = max(y for _, y in pins.values())
    cx = (x_left + x_right) / 2

    body = ['(footprint "PicoSocket_2x20_SMD_ThruHole"\n']
    body.append("\t(version 20241229)\n")
    body.append('\t(generator "pico2_trace/hw/gen_sockets.py")\n')
    body.append('\t(layer "F.Cu")\n')
    body.append(
        '\t(descr "SMT female socket carrier for a Raspberry Pi Pico 2 (Adafruit-5905-style: '
        "two 1x20 2.54mm SMD socket strips), pad numbering \\\"1\\\"..\\\"40\\\" matches stock "
        'RaspberryPi_Pico_Common_THT physical pin numbers; NPTH clearance holes at the nominal '
        'pin grid pass the Pico'"'"'s own male header pins through the board. Grid derived from '
        'RaspberryPi_Pico_Common_THT.kicad_mod.")\n'
    )
    body.append('\t(tags "Raspberry Pi Pico 2 SMD socket carrier THT elimination")\n')
    body.append(_property("Reference", "REF**", cx, y_lo - 4.6, "F.SilkS"))
    body.append(_property("Value", "PicoSocket_2x20_SMD_ThruHole", cx, y_hi + 3.3, "F.Fab"))
    body.append("\t(attr smd)\n")

    # Body-outline silk per row (inset from the courtyard so it reads as the
    # actual strip body), plus pin-1 dot and a USB-end text marker (pins
    # "1"/"40" sit at y_lo -- the near-USB end, per build_board.py's own
    # verified Pico orientation finding).
    for row_x in (x_left, x_right):
        outward = "x-" if row_x == x_left else "x+"
        sign = -1.0 if outward == "x-" else 1.0
        inner = row_x - sign * 0.9
        outer = row_x + sign * (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM + 0.3)
        x0, x1 = (outer, inner) if outward == "x-" else (inner, outer)
        body.append(_silk_rect(x0, y_lo - CRTYD_OVERHANG_MM + 0.3, x1, y_hi + CRTYD_OVERHANG_MM - 0.3))

    body.append(_pin1_dot(x_left, y_lo))
    body.append(
        '\t(fp_text user "USB END"\n'
        f"\t\t(at {_fmt(cx)} {_fmt(y_lo - 1.8)} 0)\n"
        '\t\t(layer "F.SilkS")\n'
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.8 0.8)\n\t\t\t\t(thickness 0.12)\n\t\t\t)\n\t\t)\n"
        "\t)\n"
    )

    # Courtyard: one rectangle per physical socket strip.
    for row_x in (x_left, x_right):
        outward = "x-" if row_x == x_left else "x+"
        sign = -1.0 if outward == "x-" else 1.0
        pad_outer = row_x + sign * (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM)
        inner = row_x - sign * CRTYD_MARGIN_MM
        outer = pad_outer + sign * CRTYD_MARGIN_MM
        x0, x1 = (outer, inner) if outward == "x-" else (inner, outer)
        body.append(_crtyd_rect(x0, y_lo - CRTYD_OVERHANG_MM, x1, y_hi + CRTYD_OVERHANG_MM))

    # Pads: SMD (numbered, carries the net) + NPTH (unnumbered, mechanical)
    # at every one of the 40 positions, numbers taken verbatim from the
    # source THT footprint.
    for num in [str(n) for n in row1] + [str(n) for n in row2]:
        x, y = pins[num]
        outward = "x-" if x == x_left else "x+"
        body.append(_smd_pad(num, x, y, outward))
        body.append(_npth_pad(x, y))

    body.append("\t(embedded_fonts no)\n")
    body.append(")\n")
    return "".join(body)


def gen_breakout_socket() -> str:
    pins = _parse_pad_positions(BREAKOUT_SRC)
    y_lo = min(y for _, y in pins.values())
    y_hi = max(y for _, y in pins.values())
    x_hole = pins["1"][0]
    outward = "x-"  # single row: pads offset toward -x (arbitrary but fixed)
    sign = -1.0

    body = ['(footprint "PinSocket_1x20_SMD_ThruHole"\n']
    body.append("\t(version 20241229)\n")
    body.append('\t(generator "pico2_trace/hw/gen_sockets.py")\n')
    body.append('\t(layer "F.Cu")\n')
    body.append(
        '\t(descr "SMT 1x20 2.54mm female socket strip (breakout row), pad numbering \\\"1\\\"..\\\"20\\\" '
        "matches stock PinSocket_1x20_P2.54mm_Vertical; NPTH clearance holes at the nominal pin grid pass "
        'a plugged male pin through the board. Grid derived from PinSocket_1x20_P2.54mm_Vertical.kicad_mod.")\n'
    )
    body.append('\t(tags "pin socket SMD 1x20 2.54mm THT elimination")\n')
    body.append(_property("Reference", "REF**", 0, y_lo - 2.77, "F.SilkS"))
    body.append(_property("Value", "PinSocket_1x20_SMD_ThruHole", 0, y_hi + 2.77, "F.Fab"))
    body.append("\t(attr smd)\n")

    inner = x_hole - sign * 0.9
    outer = x_hole + sign * (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM + 0.3)
    x0, x1 = (outer, inner) if outward == "x-" else (inner, outer)
    body.append(_silk_rect(x0, y_lo - CRTYD_OVERHANG_MM + 0.3, x1, y_hi + CRTYD_OVERHANG_MM - 0.3))
    body.append(_pin1_dot(x_hole, y_lo))

    pad_outer = x_hole + sign * (NPTH_DRILL_MM / 2 + PAD_GAP_MM + PAD_W_MM)
    cy_inner = x_hole - sign * CRTYD_MARGIN_MM
    cy_outer = pad_outer + sign * CRTYD_MARGIN_MM
    x0, x1 = (cy_outer, cy_inner) if outward == "x-" else (cy_inner, cy_outer)
    body.append(_crtyd_rect(x0, y_lo - CRTYD_OVERHANG_MM, x1, y_hi + CRTYD_OVERHANG_MM))

    for num in [str(n) for n in range(1, 21)]:
        x, y = pins[num]
        body.append(_smd_pad(num, x, y, outward))
        body.append(_npth_pad(x, y))

    body.append("\t(embedded_fonts no)\n")
    body.append(")\n")
    return "".join(body)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "PicoSocket_2x20_SMD_ThruHole.kicad_mod"), "w") as f:
        f.write(gen_pico_socket())
    with open(os.path.join(OUT_DIR, "PinSocket_1x20_SMD_ThruHole.kicad_mod"), "w") as f:
        f.write(gen_breakout_socket())
    print("wrote PicoSocket_2x20_SMD_ThruHole.kicad_mod + PinSocket_1x20_SMD_ThruHole.kicad_mod")


if __name__ == "__main__":
    main()
