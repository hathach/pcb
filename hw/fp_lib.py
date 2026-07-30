"""Footprint resolution map: part class -> (library, footprint).

One entry per row of the footprint table in PLAN.md Task 2. `pico2_trace` is
the local `pico2_trace.pretty/` library (custom shroud footprints); every
other library is stock KiCad (`/usr/share/kicad/footprints/<lib>.pretty/`).
"""

FP = {
    # Task 14d/14d-fix (SMT footprint migration / THT elimination, now
    # REVERTED by Task 14g): pico_socket, breakout_1x20 and the hdr_1x0N
    # headers were briefly SMD (a custom-generated PicoSocket_2x20_SMD, the
    # stock "_SMD_Pin1Left" breakout socket, and stock "_SMD_Pin1Left"
    # headers) to cut PCBA cost. Reverted: parts taking repeated hand
    # insertion force stay THT -- SMD 2.54mm sockets/headers have little pad
    # area to resist insertion/removal, are niche/expensive, and (the
    # concrete trigger) PicoSocket_2x20_SMD's land pattern, while derived
    # from a real part's numbers, was never itself a traced, orderable
    # footprint -- the project's largest remaining fab risk. usb_a still
    # swaps the all-THT Molex 67643 for the GCT USB1046 (SMD signal pads, 2
    # THT mounting posts kept -- mechanically required); that migration
    # (Task 14d) stands, since a USB-A receptacle isn't hand-inserted
    # repeatedly the way a socket/header is.
    #
    # Task 14g (this revert):
    #   - pico_socket -> stock "RaspberryPi_Pico_Common_THT" (40 THT pads
    #     numbered "1".."40", on-grid at the nominal pin positions -- no
    #     custom footprint/generator needed any more; hw/gen_sockets.py and
    #     pico2_trace.pretty/PicoSocket_2x20_SMD.kicad_mod are deleted).
    #   - breakout_1x20 -> stock "PinSocket_1x20_P2.54mm_Vertical" (THT).
    #     NOTE: this footprint anchors at pin 1, unlike the SMD
    #     "_SMD_Pin1Left" variant it replaces, which anchored at the row's
    #     geometric centre -- hw/place.py's J1B/J2B coordinates were
    #     re-derived from probed pad positions accordingly (see the Task
    #     14e report for the 22-26mm misalignment bug that exact anchor
    #     mismatch caused once before).
    #   - hdr_1x02/hdr_1x03/hdr_1x06 -> stock "PinHeader_1x0N_P2.54mm_
    #     Vertical" (THT; hdr_1x06 still has no PARTS consumer, kept for
    #     forward consistency).
    "pico_socket": ("Module", "RaspberryPi_Pico_Common_THT"),
    "breakout_1x20": ("Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical"),
    "mipi20": ("pico2_trace", "FTSH-110-01-DV"),
    "cortex10": ("pico2_trace", "FTSH-105-01-DV"),
    "jst_sh3": ("Connector_JST", "JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal"),
    "jst_sh4": ("Connector_JST", "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal"),
    "usb_a": ("Connector_USB", "USB_A_Receptacle_GCT_USB1046"),
    "usb_microb": ("Connector_USB", "USB_Micro-B_Molex_47346-0001"),
    # usb_c_pwr (J8 micro-B -> Type-C swap, 2026-07-30 order session): local
    # copy of stock USB_C_Receptacle_HRO_TYPE-C-31-M-12 (the land pattern of
    # LCSC C165948, JLC Basic) with pads *renumbered* so gen_sch.py's
    # numeric-pad invariant holds: 1=VBUS (A4/B9/A9/B4), 2=CC1 (A5),
    # 3=CC2 (B5), 4=GND (A1/B12/A12/B1), 5=NC data/SBU (A6/A7/A8/B6/B7/B8),
    # 6=shield (4x PTH legs) -- same multi-pad-per-number convention as
    # usb_microb's own shield pad "6".
    "usb_c_pwr": ("pico2_trace", "USB_C_PWR_HRO_TYPE-C-31-M-12"),
    "hdr_1x03": ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical"),
    "hdr_1x02": ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
    "hdr_1x06": ("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical"),
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
