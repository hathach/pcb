"""Footprint resolution map: part class -> (library, footprint).

One entry per row of the footprint table in PLAN.md Task 2. `pico2_trace` is
the local `pico2_trace.pretty/` library (custom shroud footprints); every
other library is stock KiCad (`/usr/share/kicad/footprints/<lib>.pretty/`).
"""

FP = {
    "pico_socket": ("Module", "RaspberryPi_Pico_Common_THT"),
    "breakout_1x20": ("Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical"),
    "mipi20": ("pico2_trace", "FTSH-110-01-DV"),
    "cortex10": ("pico2_trace", "FTSH-105-01-DV"),
    "jst_sh3": ("Connector_JST", "JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal"),
    "jst_sh4": ("Connector_JST", "JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal"),
    "usb_a": ("Connector_USB", "USB_A_Molex_67643_Horizontal"),
    "usb_microb": ("Connector_USB", "USB_Micro-B_Molex_47346-0001"),
    "hdr_1x03": ("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical"),
    "hdr_1x02": ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical"),
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
