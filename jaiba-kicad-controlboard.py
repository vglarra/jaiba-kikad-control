"""
KiCad pcbnew script — master board for 3x Teensy 4.1 in sockets, 150x100...
no: 150x150mm board.

  - Sensor Teensy A: 9x velostat channels (A0-A8 = physical Teensy pins 14-22)
  - Sensor Teensy B: 7x piezo channels    (A0-A6 = physical Teensy pins 14-20)
  - UI Teensy: ST7796 TFT + XPT2046 touch header, plus BOTH sensor UART links
    (Serial1 pins 0/1 to Sensor A, Serial3 pins 14/15 to Sensor B)

*** VERIFY BEFORE ROUTING OR FABRICATING ***
TEENSY_ROW1 / TEENSY_ROW2 below are my best-effort reconstruction of the
Teensy 4.1's physical pin order from memory, not copied from the datasheet
in front of me. The mechanical dimensions (61mm long, two rows 17.78mm/0.7in
apart, 2.54mm pitch) I'm confident about — that's just the standard DIP-style
socket spacing every Teensy 4.1 carrier uses. The pin ORDER in each row is
what needs checking against the official pinout card before you rely on it:
https://www.pjrc.com/teensy/pinout.html
If a pin turns out to be in the wrong slot, the fix is just editing these
two lists and re-running — nothing else in the script depends on the
specific values, only on the lists being internally consistent.

WHAT THIS SCRIPT DOES vs LEAVES FOR YOU (same philosophy as the sensor-board
script this follows on from):
  - Draws the 3.3V/GND bus bars.
  - Places all 3 Teensy sockets, all 16 sensor channel circuits (headers +
    resistors + diodes, same divider circuit as your velostat/piezo boards),
    4 cal/curve buttons, the TFT+touch header, and 4 mounting holes.
  - Auto-routes ONLY short, local, single-purpose traces: header->resistor
    (or header->R1) inside each channel, and the TFT header straight down
    into the UI Teensy (this one's safe because the header sits directly
    above ROW1 with nothing else in between — see build_tft_header).
  - Everything else — each channel's signal net reaching its Teensy analog
    pin, the two UART links between Teensysays, buttons reaching their
    Teensy pins, and every Teensy's power pins reaching the bus bars — is
    given a matching net name (so KiCad's ratsnest will show you exactly
    where a wire needs to go) but is NOT drawn as a trace. Routing those
    would mean crossing under ROW2 to reach ROW1 pins, which isn't a
    straight-line job I want to guess at without being able to check DRC
    myself. Run Inspect > DRC to see the ratsnest and route those by hand
    (or with KiCad's interactive router) once you've confirmed the pinout.

FIRMWARE NOTE: the UIFirmware_Arduino.ino you shared only reads Serial1
today (one sensor Teensy). This board wires up a second UART (Serial3,
pins 14/15) to Sensor Teensy B, but the UI firmware will need a small
extension to actually read it — happy to help with that separately.

Run from KiCad's Scripting Console with a board open. Clear the board first
if re-running after a previous test.
"""

import os
import pcbnew

FOOTPRINT_LIB_DIR = os.environ.get(
    "KICAD9_FOOTPRINT_DIR",
    r"C:\Program Files\KiCad\9.0\share\kicad\footprints"
).rstrip("\\/")

BOARD_W = 150.0
BOARD_H = 150.0

PIN_PITCH = 2.54
ROW_GAP = 17.78  # 0.7in between a Teensy's two pin rows — mechanically fixed

# --- Teensy 4.1 pin tables (see disclaimer above) ---
# Index 0 = the end nearest the USB connector.
TEENSY_ROW1 = ["GND", "3V3", "23", "22", "21", "20", "19", "18", "17", "16",
               "15", "14", "13", "12", "11", "10", "9", "8", "7", "6",
               "5", "4", "3", "2"]
TEENSY_ROW2 = ["VIN", "GND", "0", "1", "24", "25", "26", "27", "28", "29",
               "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
               "40", "41", "GND", "3V3"]

# --- Zone origins (x0,y0 = position of ROW1 index 0 / the USB end) ---
TEENSY_A_X, TEENSY_A_Y = 8.0, 10.0
TEENSY_B_X, TEENSY_B_Y = 85.0, 10.0
TEENSY_UI_X, TEENSY_UI_Y = 8.0, 125.0

VELO_X = 15.0
VELO_Y_START = 38.0
VELO_ROW_SPACING = 9.0
VELO_R_OFFSET_X = 6.0

PIEZO_X = 95.0
PIEZO_Y_START = 38.0
PIEZO_ROW_SPACING = 11.5  # same as the original sensor-board script
PIEZO_R1_OFFSET_X = 6.0
PIEZO_R2_OFFSET_Y = 4.0
PIEZO_DIODE_OFFSET_X = 20.0
PIEZO_DIODE_OFFSET_Y = -4.0

BUS_3V3_X = 3.0
BUS_GND_X = 147.0
BUS_Y0, BUS_Y1 = 5.0, 148.0

LAYER_EDGE = pcbnew.Edge_Cuts


def mm(v):
    return pcbnew.FromMM(v)


def x_of(pad):
    return pcbnew.ToMM(pad.GetPosition().x)


def y_of(pad):
    return pcbnew.ToMM(pad.GetPosition().y)


def load_footprint(board, lib_name, fp_name, x, y, ref, value=""):
    lib_path = f"{FOOTPRINT_LIB_DIR}/{lib_name}.pretty"
    fp = pcbnew.FootprintLoad(lib_path, fp_name)
    if fp is None:
        raise RuntimeError(
            f"Could not load '{fp_name}' from '{lib_path}'. "
            f"Check FOOTPRINT_LIB_DIR matches your KiCad install."
        )
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetReference(ref)
    if value:
        fp.SetValue(value)
    board.Add(fp)
    return fp


def get_or_create_net(board, name):
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def route(board, pad_a, pad_b, width_mm=0.3):
    net = pad_a.GetNet()
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pad_a.GetPosition())
    t.SetEnd(pad_b.GetPosition())
    t.SetWidth(mm(width_mm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    board.Add(t)
    return t


def draw_bus(board, x, y1, y2, net_name, width_mm=1.0):
    net = get_or_create_net(board, net_name)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(x), mm(y1)))
    t.SetEnd(pcbnew.VECTOR2I(mm(x), mm(y2)))
    t.SetWidth(mm(width_mm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    board.Add(t)
    return t


def seg(board, x1, y1, x2, y2, layer, width_mm=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    s.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    s.SetLayer(layer)
    s.SetWidth(mm(width_mm))
    board.Add(s)


class TeensySocket:
    """Two 1x24 pin sockets, ROW_GAP apart, standing in for a Teensy 4.1
    socket. .pad(name) looks up a single pin by its Teensy pin number/name
    ('0'..'41', or 'GND'/'3V3'/'VIN' — note the latter three are ambiguous
    if used with .pad(), use .pads_named() instead since they each appear
    more than once)."""

    def __init__(self, row1_fp, row2_fp):
        self.row1 = row1_fp
        self.row2 = row2_fp

    def pad(self, pin_name):
        if pin_name in TEENSY_ROW1 and TEENSY_ROW1.count(pin_name) == 1:
            return self.row1.Pads()[TEENSY_ROW1.index(pin_name)]
        if pin_name in TEENSY_ROW2 and TEENSY_ROW2.count(pin_name) == 1:
            return self.row2.Pads()[TEENSY_ROW2.index(pin_name)]
        raise ValueError(f"Pin '{pin_name}' is ambiguous or not found — use pads_named() for GND/3V3/VIN")

    def pads_named(self, name):
        result = []
        for i, n in enumerate(TEENSY_ROW1):
            if n == name:
                result.append(self.row1.Pads()[i])
        for i, n in enumerate(TEENSY_ROW2):
            if n == name:
                result.append(self.row2.Pads()[i])
        return result


def build_teensy_socket(board, x0, y0, ref_prefix):
    row1 = load_footprint(board, "Connector_PinSocket_2.54mm", "PinSocket_1x24_P2.54mm_Vertical",
                           x0, y0, ref=f"{ref_prefix}_R1")
    row2 = load_footprint(board, "Connector_PinSocket_2.54mm", "PinSocket_1x24_P2.54mm_Vertical",
                           x0, y0 + ROW_GAP, ref=f"{ref_prefix}_R2")
    return TeensySocket(row1, row2)


def build_velostat_channel(board, teensy, teensy_pin, cx, cy, idx, group):
    net_3v3 = get_or_create_net(board, "3V3")
    net_gnd = get_or_create_net(board, "GND")
    net_sig = get_or_create_net(board, f"{group}_A{idx}")

    hdr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                          cx, cy, ref=f"J_VELO_{group}{idx}")
    hdr.Pads()[0].SetNet(net_3v3)
    hdr.Pads()[1].SetNet(net_sig)

    r = load_footprint(board, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
                        cx + VELO_R_OFFSET_X, cy, ref=f"R_VELO_{group}{idx}", value="100")
    r.Pads()[0].SetNet(net_sig)
    r.Pads()[1].SetNet(net_gnd)

    route(board, hdr.Pads()[1], r.Pads()[0])  # local, safe

    # Ties the channel's output to the actual Teensy analog pin (ratsnest
    # only — see the header comment for why this isn't drawn as a trace).
    teensy.pad(teensy_pin).SetNet(net_sig)

    # hdr.pin0 (3V3) and r.pin1 (GND) are left bare — bridge to the bus
    # bars by hand, same as the original velostat-board script.
    return hdr, r


def build_piezo_channel(board, teensy, teensy_pin, cx, cy, idx, group):
    net_3v3 = get_or_create_net(board, "3V3")
    net_gnd = get_or_create_net(board, "GND")
    net_sig = get_or_create_net(board, f"{group}_A{idx}")
    net_raw = get_or_create_net(board, f"{group}_RAW{idx}")

    hdr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                          cx, cy, ref=f"J_PIEZO_{group}{idx}")
    hdr.Pads()[0].SetNet(net_raw)
    hdr.Pads()[1].SetNet(net_gnd)

    r1 = load_footprint(board, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
                         cx + PIEZO_R1_OFFSET_X, cy, ref=f"R1_PIEZO_{group}{idx}", value="10k")
    r2 = load_footprint(board, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
                         cx + PIEZO_R1_OFFSET_X, cy + PIEZO_R2_OFFSET_Y, ref=f"R2_PIEZO_{group}{idx}", value="10k")
    d = load_footprint(board, "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal",
                        cx + PIEZO_DIODE_OFFSET_X, cy + PIEZO_DIODE_OFFSET_Y, ref=f"D_PIEZO_{group}{idx}", value="1N4148")

    r1.Pads()[0].SetNet(net_raw)
    r1.Pads()[1].SetNet(net_sig)
    r2.Pads()[0].SetNet(net_sig)
    r2.Pads()[1].SetNet(net_gnd)
    d.Pads()[0].SetNet(net_sig)
    d.Pads()[1].SetNet(net_3v3)

    route(board, hdr.Pads()[0], r1.Pads()[0])  # local, safe

    teensy.pad(teensy_pin).SetNet(net_sig)

    # R1->R2, R1->diode, R2's GND pad, hdr's GND pad, and diode's cathode
    # ->3V3 are all left bare — bridge by hand (same as the original script).
    return hdr, r1, r2, d


def build_button(board, teensy, teensy_pin, ref, y_offset=4.0):
    """Places a 2-pin push button just below the Teensy's ROW2, aligned to
    the X position of teensy_pin (read back from the actual placed pad, so
    this stays correct even if the absolute pin table has an error)."""
    net_gnd = get_or_create_net(board, "GND")
    net_sig = get_or_create_net(board, f"BTN_{ref}")

    tpad = teensy.pad(teensy_pin)
    cx = x_of(tpad)
    cy = y_of(tpad) + ROW_GAP + y_offset  # ROW2 sits ROW_GAP below ROW1

    btn = load_footprint(board, "Button_Switch_THT", "SW_PUSH_6mm", cx, cy, ref=ref)
    # SW_PUSH_6mm has 4 pads (two bridged pairs). Pads 1 & 3 are the two
    # switched nodes on the common 6mm tactile footprint — double check
    # this against your exact footprint variant before soldering.
    btn.Pads()[0].SetNet(net_sig)
    btn.Pads()[2].SetNet(net_gnd)

    tpad.SetNet(net_sig)  # ratsnest only — see header comment
    return btn


def build_tft_header(board, ui_teensy):
    """1x8 signal header placed directly above the UI Teensy's ROW1, so the
    connection down into ROW1 is a straight vertical run with nothing else
    in between — the one cross-board connection this script auto-routes."""
    net_3v3 = get_or_create_net(board, "3V3")
    net_gnd = get_or_create_net(board, "GND")

    # Ascending-X order on ROW1: SCK(13), MISO(12), MOSI(11), CS(10),
    # RST(9), DC(8), T_IRQ(7, unused), T_CS(6). This ordering is guaranteed
    # by TEENSY_ROW1's internal consistency, not by hand-picked coordinates.
    pins_order = ["13", "12", "11", "10", "9", "8", "7", "6"]
    func_names = {"13": "SCK", "12": "MISO", "11": "MOSI", "10": "CS",
                  "9": "RST", "8": "DC", "7": "T_IRQ", "6": "T_CS"}

    first_pad = ui_teensy.pad(pins_order[0])
    hx = x_of(first_pad)
    hy = y_of(first_pad) - 10.0  # 10mm above ROW1

    hdr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical",
                          hx, hy, ref="J_TFT")
    for i, pin in enumerate(pins_order):
        net = get_or_create_net(board, f"TFT_{func_names[pin]}")
        hdr.Pads()[i].SetNet(net)
        tpad = ui_teensy.pad(pin)
        tpad.SetNet(net)
        route(board, hdr.Pads()[i], tpad)  # straight down, safe

    # Separate 2-pin power header for the display module, just to the left
    # of the signal header — left as manual bridges to the bus bars.
    pwr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                          hx - 2 * PIN_PITCH, hy, ref="J_TFT_PWR")
    pwr.Pads()[0].SetNet(net_gnd)
    pwr.Pads()[1].SetNet(net_3v3)
    return hdr, pwr


if __name__ == "__main__":
    board = pcbnew.GetBoard()

    # --- Bus bars ---
    draw_bus(board, BUS_3V3_X, BUS_Y0, BUS_Y1, "3V3")
    draw_bus(board, BUS_GND_X, BUS_Y0, BUS_Y1, "GND")

    # --- Sensor Teensy A: 9x velostat ---
    teensy_a = build_teensy_socket(board, TEENSY_A_X, TEENSY_A_Y, "J_TEENSYA")
    for i in range(9):
        y = VELO_Y_START + i * VELO_ROW_SPACING
        build_velostat_channel(board, teensy_a, str(14 + i), VELO_X, y, i, "TEENSYA")
    build_button(board, teensy_a, "3", "SW_CAL_A")
    build_button(board, teensy_a, "4", "SW_CURVE_A")

    # --- Sensor Teensy B: 7x piezo ---
    teensy_b = build_teensy_socket(board, TEENSY_B_X, TEENSY_B_Y, "J_TEENSYB")
    for i in range(7):
        y = PIEZO_Y_START + i * PIEZO_ROW_SPACING
        build_piezo_channel(board, teensy_b, str(14 + i), PIEZO_X, y, i, "TEENSYB")
    build_button(board, teensy_b, "3", "SW_CAL_B")
    build_button(board, teensy_b, "4", "SW_CURVE_B")

    # --- UI Teensy: TFT/touch header + both UART links ---
    teensy_ui = build_teensy_socket(board, TEENSY_UI_X, TEENSY_UI_Y, "J_TEENSYUI")
    build_tft_header(board, teensy_ui)

    # UART A: Sensor A's Serial1 <-> UI Teensy's Serial1, crossed.
    net = get_or_create_net(board, "UART_A_1")  # SensorA.TX1 -> UI.RX1
    teensy_a.pad("1").SetNet(net)
    teensy_ui.pad("0").SetNet(net)
    net = get_or_create_net(board, "UART_A_2")  # SensorA.RX1 <- UI.TX1
    teensy_a.pad("0").SetNet(net)
    teensy_ui.pad("1").SetNet(net)

    # UART B: Sensor B's Serial1 <-> UI Teensy's Serial3 (pins 14/15),
    # crossed. Requires the UI firmware to add Serial3 handling — see the
    # firmware note at the top of this file.
    net = get_or_create_net(board, "UART_B_1")  # SensorB.TX1 -> UI.RX3
    teensy_b.pad("1").SetNet(net)
    teensy_ui.pad("15").SetNet(net)
    net = get_or_create_net(board, "UART_B_2")  # SensorB.RX1 <- UI.TX3
    teensy_b.pad("0").SetNet(net)
    teensy_ui.pad("14").SetNet(net)

    # Tie every Teensy's power pins to the bus nets (ratsnest only).
    net_gnd = get_or_create_net(board, "GND")
    net_3v3 = get_or_create_net(board, "3V3")
    for t in (teensy_a, teensy_b, teensy_ui):
        for p in t.pads_named("GND"):
            p.SetNet(net_gnd)
        for p in t.pads_named("3V3"):
            p.SetNet(net_3v3)
        # VIN is left unconnected — how you power the board (USB vs a
        # separate supply into VIN) is your call, not this script's.

    # --- Board outline ---
    seg(board, 0, 0, BOARD_W, 0, LAYER_EDGE)
    seg(board, BOARD_W, 0, BOARD_W, BOARD_H, LAYER_EDGE)
    seg(board, BOARD_W, BOARD_H, 0, BOARD_H, LAYER_EDGE)
    seg(board, 0, BOARD_H, 0, 0, LAYER_EDGE)

    # --- Mounting holes (corners) ---
    for i, (mx, my) in enumerate([(5, 5), (145, 5), (5, 145), (145, 145)]):
        load_footprint(board, "MountingHole", "MountingHole_3.2mm_M3", mx, my, ref=f"MH{i + 1}")

    pcbnew.Refresh()
    print(f"Board size: {BOARD_W}mm x {BOARD_H}mm")
    print("Placed: 3x Teensy 4.1 socket, 9x velostat channel, 7x piezo channel,")
    print("4x cal/curve button, 1x TFT+touch header, 4x mounting hole.")
    print("")
    print("Manual bridges still needed (ratsnest will show these after DRC):")
    print(" - Each velostat channel: R.pad2 (GND) -> GND bus")
    print(" - Each piezo channel: R1.pad2->R2.pad1, R1.pad2->D anode,")
    print("   R2.pad2 (GND) and hdr.pad2 (GND) -> GND bus, D cathode -> 3V3 bus")
    print(" - Every channel's signal net -> its Teensy analog pin (A0-A8 on")
    print("   Sensor A, A0-A6 on Sensor B) — crosses under ROW2, not auto-routed")
    print(" - Cal/curve buttons -> their Teensy pin + GND")
    print(" - Each Teensy's GND/3V3 pads -> the bus bars")
    print(" - UART_A_1/2 (Sensor A <-> UI Serial1) and UART_B_1/2")
    print("   (Sensor B <-> UI Serial3) — long cross-board runs, not auto-routed")
    print("")
    print("BEFORE ROUTING OR ORDERING: verify TEENSY_ROW1 / TEENSY_ROW2 against")
    print("the official Teensy 4.1 pinout (pjrc.com/teensy/pinout.html) — see")
    print("the disclaimer at the top of this file. Run Inspect > DRC next.")