"""pcbnew driver: instantiate footprints, nets, net classes, 2-layer stackup.

Run: python3 hw/build_board.py

Idempotent: a non-DNP PARTS ref already present on the board is reused
(skip-if-present) rather than reloaded, so re-running does not duplicate
footprints; see `_add_footprints` for why (KiCad 9.0.2 pcbnew quirk).
"""

import math
import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pcbnew

from hw.fp_lib import FP
from hw.netlist import NETS, PARTS

BOARD_FILE = "pico2_trace.kicad_pcb"
SYSTEM_FP_ROOT = "/usr/share/kicad/footprints"
PROJECT_FP_DIR = "pico2_trace.pretty"

# Task 11: board outline + mounting holes + Pico socket edge placement.
BOARD_W_MM = 65.0
BOARD_H_MM = 34.0
CORNER_R_MM = 3.0

# 4x M3 mounting holes, inset ~4 mm from each edge/corner (netless).
MOUNTING_HOLES_MM = {
    "MH1": (4.0, 4.0),
    "MH2": (BOARD_W_MM - 4.0, 4.0),
    "MH3": (4.0, BOARD_H_MM - 4.0),
    "MH4": (BOARD_W_MM - 4.0, BOARD_H_MM - 4.0),
}

# PICO placement: USB/BOOTSEL end overhangs the left board edge (x=0).
PICO_TARGET_LEFT_MM = -1.0  # USB end sits ~1mm outboard
PICO_TARGET_CENTER_Y_MM = BOARD_H_MM / 2.0  # vertically centered
PICO_ORIENTATION_DEG = 90.0


def _fp_dir(lib: str) -> str:
    return PROJECT_FP_DIR if lib == "pico2_trace" else f"{SYSTEM_FP_ROOT}/{lib}.pretty"


def _add_footprints(b) -> dict[str, "pcbnew.FOOTPRINT"]:
    """Load + add every non-DNP PARTS entry; return ref -> FOOTPRINT.

    Idempotence: skip-if-present -- if a footprint with this ref is already
    on the board, reuse it instead of loading a duplicate. (Tried
    remove-then-reload instead; empirically, on KiCad 9.0.2, calling
    `pcbnew.FootprintLoad()` again after a `BOARD.Remove()` of a *populated*
    board -- one with nets/pads already wired, i.e. the second run -- leaves
    the IO_MGR plugin cache and/or the new footprints' PAD list corrupted:
    `FootprintLoad` itself starts raising `'SwigPyObject' object has no
    attribute 'FootprintLoad'`, or a later `fp.Pads()` raises `'SwigPyObject'
    object is not iterable`, then the process segfaults on exit. Skip-if-
    present sidesteps it entirely: a second run makes zero FootprintLoad
    calls and never touches BOARD.Remove.)
    """
    fps: dict[str, "pcbnew.FOOTPRINT"] = {}
    for ref, part in PARTS.items():
        if part.dnp:
            continue
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            lib, name = FP[part.fp_class]
            fp = pcbnew.FootprintLoad(_fp_dir(lib), name)
            assert fp is not None, f"{ref}: FootprintLoad({lib}:{name}) failed"
            b.Add(fp)
        fp.SetReference(ref)
        fp.SetValue(part.value)
        fps[ref] = fp
    return fps


def _add_nets(b) -> dict[str, "pcbnew.NETINFO_ITEM"]:
    """Create every model net; return name -> NETINFO_ITEM.

    Idempotence: reuse the existing NETINFO_ITEM if `name` is already a net
    on the board (via `BOARD.FindNet`) instead of creating a duplicate --
    re-adding a NETINFO_ITEM for a name that already exists corrupts the
    board's net list (observed as pad/footprint objects turning into bare,
    non-iterable SwigPyObjects on the next pcbnew call).
    """
    nets: dict[str, "pcbnew.NETINFO_ITEM"] = {}
    for name in sorted(NETS):
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
        nets[name] = ni
    return nets


def _wire_pads(fps: dict, nets: dict) -> None:
    """Set each pad's net, translating logical pin -> pad number via
    Part.pad_nets() (same rule emit_netlist uses). A footprint pad number can
    appear on more than one physical pad (USB shield tabs, mounting flanges
    on a connector footprint) -- every matching pad gets the net, not just
    the first."""
    for ref, part in PARTS.items():
        if part.dnp:
            continue
        fp = fps[ref]
        for padno, netname in part.pad_nets():
            ni = nets[netname]
            hit = False
            for pad in fp.Pads():
                if pad.GetNumber() == padno:
                    pad.SetNet(ni)
                    hit = True
            assert hit, f"{ref}: no pad numbered {padno!r} (net {netname})"


def _set_net_classes(b) -> None:
    ds = b.GetDesignSettings()
    ns = ds.m_NetSettings

    def nc(name, width_mm, clearance_mm):
        k = pcbnew.NETCLASS(name)
        k.SetTrackWidth(pcbnew.FromMM(width_mm))
        k.SetClearance(pcbnew.FromMM(clearance_mm))
        ns.SetNetclass(name, k)

    nc("Power", 0.5, 0.2)
    nc("Trace", 0.3, 0.25)
    for n in ["GND", "VBUS_NET", "V5_JTRACE", "VSYS", "P3V3", "HOST_VBUS"]:
        ns.SetNetclassPatternAssignment(n, "Power")
    for n in ["TRACECLK", "TD0", "TD1", "TD2", "TD3"]:
        ns.SetNetclassPatternAssignment(n, "Trace")


def _mm(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def _draw_outline(b) -> None:
    """Replace the Task-1 placeholder Edge_Cuts rectangle with a
    BOARD_W_MM x BOARD_H_MM rounded-rect outline (CORNER_R_MM radius),
    origin (0,0) top-left -- same convention as the placeholder.

    Reuses the placeholder's 4 existing PCB_SHAPE segments in place (mutating
    their Start/End) for the outline's 4 straight edges, and only Add()s new
    PCB_SHAPE arcs for the 4 rounded corners -- it never calls BOARD.Remove().
    That's a deliberate workaround, not a style choice: empirically, on this
    KiCad 9.0.2 board (already populated with footprints/nets from Task 10),
    a single BOARD.Remove() of ANY item -- not just footprints, as
    _add_footprints' docstring warns, but a plain Edge_Cuts PCB_SHAPE too --
    poisons the board object for the rest of the process: a subsequent
    GetDrawings() raises `'SwigPyObject' object is not iterable`, or later
    calls like GetDesignSettings().m_NetSettings raise `'SwigPyObject' object
    has no attribute ...`, and the process segfaults on exit. Reused/added
    PCB_SHAPEs are matched by index, not identity, so on a second run (8
    edge shapes already present: 4 segments + 4 arcs) they're reused in
    place too -- idempotent, still zero Remove() calls.
    """
    w, h, r = BOARD_W_MM, BOARD_H_MM, CORNER_R_MM

    existing = [d for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    segments = [d for d in existing if d.GetShape() == pcbnew.SHAPE_T_SEGMENT]
    arcs = [d for d in existing if d.GetShape() == pcbnew.SHAPE_T_ARC]

    def seg(existing_shape, p1, p2):
        s = existing_shape
        if s is None:
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(pcbnew.Edge_Cuts)
            b.Add(s)
        s.SetStart(_mm(*p1))
        s.SetEnd(_mm(*p2))

    def arc(existing_shape, center, start_deg, end_deg):
        """Quarter-circle corner: center + radius, spanning start_deg ->
        end_deg (measured from +X axis, degrees), via SetArcGeometry's
        three-point form (start/mid/end) -- avoids angle-unit ambiguity."""
        cx, cy = center
        mid_deg = (start_deg + end_deg) / 2.0

        def pt(deg):
            rad = math.radians(deg)
            return (cx + r * math.cos(rad), cy + r * math.sin(rad))

        s = existing_shape
        if s is None:
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetLayer(pcbnew.Edge_Cuts)
            b.Add(s)
        s.SetArcGeometry(_mm(*pt(start_deg)), _mm(*pt(mid_deg)), _mm(*pt(end_deg)))

    # Clockwise from the top edge, corners rounded with a 90-degree arc each.
    seg_specs = [
        ((r, 0), (w - r, 0)),  # top
        ((w, r), (w, h - r)),  # right
        ((w - r, h), (r, h)),  # bottom
        ((0, h - r), (0, r)),  # left
    ]
    arc_specs = [
        ((w - r, r), -90, 0),  # top-right
        ((w - r, h - r), 0, 90),  # bottom-right
        ((r, h - r), 90, 180),  # bottom-left
        ((r, r), 180, 270),  # top-left
    ]

    for i, (p1, p2) in enumerate(seg_specs):
        seg(segments[i] if i < len(segments) else None, p1, p2)
    for i, (center, a0, a1) in enumerate(arc_specs):
        arc(arcs[i] if i < len(arcs) else None, center, a0, a1)


def _add_mounting_holes(b) -> None:
    """4x MountingHole:MountingHole_3.2mm_M3, refs MH1-MH4, netless.

    Board-only fixtures, not part of the PARTS/NETS connectivity model (see
    hw/netlist.py) -- intentionally absent from hw/checks.py's lint/tests.
    Same skip-if-present idempotence pattern as _add_footprints (BL-10: no
    pcbnew.AddHole -- MountingHole footprints are the API's substitute).
    """
    lib, name = FP["mounthole"]
    for ref, (x, y) in MOUNTING_HOLES_MM.items():
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            fp = pcbnew.FootprintLoad(_fp_dir(lib), name)
            assert fp is not None, f"{ref}: FootprintLoad({lib}:{name}) failed"
            b.Add(fp)
            fp.SetReference(ref)
        fp.SetPosition(_mm(x, y))


def _place_pico(fps: dict) -> None:
    """Place PICO so the module's USB/BOOTSEL end overhangs the left board
    edge (x ~= -1mm), vertically centered on the board.

    Origin-convention finding (checked programmatically via the footprint's
    F.CrtYd courtyard bbox, not guessed): at rest (0 deg), pin "1" and pin
    "40" sit on the SAME end (native Y=0, confirmed by the footprint's own
    "USB Cable" silk/fab annotation at native Y=-13.3, just outboard of that
    row) -- the near-USB end. Pins "20"/"21" sit at the far/antenna end
    (native Y=48.26, confirmed by the "Possible Antenna"/"Keep Out"
    annotations there). This is the real, physical Pico pinout: pin 1 and
    pin 40 are the two header pins closest to the USB connector.

    Consequence: a pure rotation (no mirror) can reorder the X-axis mapping
    or the Y-axis mapping independently, but NOT both at once here, because
    pin1->pin40 runs one handedness around the module's rectangle (via the
    USB edge) while the brief's literal ask ("pin 1 top-left, pin 40
    bottom-left, USB end at the left board edge") requires the opposite
    handedness -- i.e. it requires a mirror flip, which for a THT module
    footprint would flip it onto the back copper layer (physically wrong:
    you cannot mirror a real 3D Pico board through the PCB plane and still
    have it sit on top). Verified computationally by sweeping all 4
    rotations' pad-1/pad-40/pad-20/pad-21 positions and courtyard bbox --
    only 0/180 deg give a portrait module (long axis vertical, wrong for an
    edge overhang), and of the two landscape options:
      - 90 deg:  USB end at the board's LEFT (correct) but pin "40" lands
        top-left / pin "1" lands bottom-left (pins 1/40 swapped vs. the
        brief's literal text).
      - 270 deg: pin "1" lands top-left / pin "40" bottom-left (matches the
        brief's literal text) but the USB end ends up at the board's RIGHT.
    The functional requirement (USB/BOOTSEL end overhangs the LEFT edge) is
    the substantive one -- Task 12 will place the debug/trace connectors
    (J3/J4/J6/J7) near the Pico's trace pins, and matters more than which of
    pin 1 vs pin 40 is nominally "on top". 90 deg is used.
    """
    fp = fps["PICO"]
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    fp.SetOrientationDegrees(PICO_ORIENTATION_DEG)

    # Measure the courtyard bbox with the anchor at the origin, then solve
    # for the anchor position that lands the bbox where we want it (bbox is
    # a rigid shape relative to the anchor -- moving the anchor by (dx,dy)
    # moves the whole bbox by (dx,dy)). BuildCourtyardCaches() is required
    # here: on a footprint fetched via FindFootprintByReference (the
    # skip-if-present path -- true on every run after the first, since PICO
    # was already added in Task 10), the courtyard polygon cache is not
    # populated yet and GetCourtyard().BBox() silently returns an all-zero
    # box instead of raising.
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    left_mm = pcbnew.ToMM(bb.GetLeft())
    center_y_mm = pcbnew.ToMM(bb.GetTop() + bb.GetBottom()) / 2.0

    dx = PICO_TARGET_LEFT_MM - left_mm
    dy = PICO_TARGET_CENTER_Y_MM - center_y_mm
    fp.SetPosition(_mm(dx, dy))


def main() -> None:
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    fps = _add_footprints(b)
    nets = _add_nets(b)
    _wire_pads(fps, nets)

    _add_mounting_holes(b)
    _place_pico(fps)
    _draw_outline(b)

    b.SetCopperLayerCount(2)
    _set_net_classes(b)

    pcbnew.SaveBoard(BOARD_FILE, b)
    pcbnew.GetSettingsManager().SaveProject()  # required or net classes are lost

    print(f"footprints={len(fps)} nets={len(nets)}")


if __name__ == "__main__":
    main()
