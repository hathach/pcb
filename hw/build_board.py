"""pcbnew driver: instantiate footprints, nets, net classes, 2-layer stackup.

Run: python3 hw/build_board.py

Idempotent: a non-DNP PARTS ref already present on the board is reused
(skip-if-present) rather than reloaded, so re-running does not duplicate
footprints; see `_add_footprints` for why (KiCad 9.0.2 pcbnew quirk).
"""

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


def main() -> None:
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    fps = _add_footprints(b)
    nets = _add_nets(b)
    _wire_pads(fps, nets)

    b.SetCopperLayerCount(2)
    _set_net_classes(b)

    pcbnew.SaveBoard(BOARD_FILE, b)
    pcbnew.GetSettingsManager().SaveProject()  # required or net classes are lost

    print(f"footprints={len(fps)} nets={len(nets)}")


if __name__ == "__main__":
    main()
