"""Footprint resolution map: part class -> (library, footprint).

One entry per row of the footprint table in PLAN.md Task 2. `pico2_trace` is
the local `pico2_trace.pretty/` library (custom shroud footprints); every
other library is stock KiCad (`/usr/share/kicad/footprints/<lib>.pretty/`).
"""

FP = {
    # Task 14d (SMT footprint migration / THT elimination): pico_socket and
    # breakout_1x20 first pointed at custom SMD-socket footprints generated
    # by hw/gen_sockets.py, each with an NPTH clearance hole under every pin
    # so a THT-style pin could still pass through the board. usb_a swaps the
    # all-THT Molex 67643 for the GCT USB1046 (SMD signal pads, 2 THT
    # mounting posts kept -- mechanically required). hdr_1x02/hdr_1x03/
    # hdr_1x06 swap to the stock "_SMD_Pin1Left" variants (hdr_1x06
    # currently has no PARTS consumer -- J_TRACE_TP was removed from the
    # model in Task 14c -- kept here for forward consistency per the
    # Task 14d brief).
    #
    # Task 14d-fix (blind-bottom sockets, no through-holes -- the pins
    # bottom out inside the socket instead of passing through the board):
    #   - breakout_1x20 now points straight at the stock KiCad
    #     "PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left" footprint -- no
    #     custom geometry at all, zero land-pattern risk. Both J1B and J2B
    #     use this single footprint; place.py already places them 180 deg
    #     apart (rot90/rot270) to put each row's pin "1" at the correct
    #     physical end with its pads outboard of the Pico -- a second
    #     "_Pin1Right"-based fp_class was considered and rejected: the
    #     stock footprint's own pad pattern is a symmetric left/right
    #     zigzag (courtyard is symmetric about the row centerline either
    #     way), so a rigid rotation of ONE footprint reproduces the correct
    #     envelope for both rows; no mirrored variant is needed.
    #   - pico_socket points at a regenerated PicoSocket_2x20_SMD (renamed
    #     from ..._ThruHole): same pad numbering, but the NPTH holes are
    #     gone and the per-pad size/shape/layers/offset are now the real
    #     stock breakout footprint's own numbers (parsed verbatim), not an
    #     invented hole-clearance formula.
    "pico_socket": ("pico2_trace", "PicoSocket_2x20_SMD"),
    "breakout_1x20": ("Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left"),
    "mipi20": ("pico2_trace", "FTSH-110-01-DV"),
    "cortex10": ("pico2_trace", "FTSH-105-01-DV"),
    "jst_sh3": ("Connector_JST", "JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal"),
    "jst_sh4": ("Connector_JST", "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal"),
    "usb_a": ("Connector_USB", "USB_A_Receptacle_GCT_USB1046"),
    "usb_microb": ("Connector_USB", "USB_Micro-B_Molex_47346-0001"),
    "hdr_1x03": ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical_SMD_Pin1Left"),
    "hdr_1x02": ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical_SMD_Pin1Left"),
    "hdr_1x06": ("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"),
    "loadswitch": ("Package_TO_SOT_SMD", "SOT-23-5"),
    "esd6": ("Package_TO_SOT_SMD", "SOT-23-6"),
    "isense": ("Package_TO_SOT_SMD", "SOT-23-5"),
    "fet3": ("Package_TO_SOT_SMD", "SOT-23"),
    "button": ("Button_Switch_SMD", "SW_SPST_B3S-1000"),
    "testpoint": ("TestPoint", "TestPoint_Pad_D1.5mm"),
    "mounthole": ("MountingHole", "MountingHole_3.2mm_M3"),
    "r0402": ("Resistor_SMD", "R_0402_1005Metric"),
    "c0402": ("Capacitor_SMD", "C_0402_1005Metric"),
    "c0805": ("Capacitor_SMD", "C_0805_2012Metric"),  # Task 4: HOST_VBUS bulk cap (bigger than c0402)
    "led0603": ("LED_SMD", "LED_0603_1608Metric"),
    "shunt": ("Resistor_SMD", "R_1206_3216Metric"),
    # Added in Task 3 for honest DNP-part footprints (both verified present
    # under /usr/share/kicad/footprints/ before use):
    "sod123": ("Diode_SMD", "D_SOD-123"),                                    # D_J9_BUSPWR (DNP)
    # Task 14b: real INA219 footprint (verified present on disk), replacing
    # the earlier "isense" (SOT-23-5) stand-in now that U_INA219_ALT is
    # realized Adafruit-style (footprint present + wired + dnp=True).
    "sot23-8": ("Package_TO_SOT_SMD", "SOT-23-8"),                           # U_INA219_ALT (DNP)
}
