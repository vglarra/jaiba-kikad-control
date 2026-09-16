"""
KiCad pcbnew script — master board for 3x Teensy 4.1 in sockets, 150x100...
no: 150x150mm board.

  - Sensor Teensy A: 9x velostat channels (A0-A8 = physical Teensy pins 14-22)
  - Sensor Teensy B: 7x piezo channels    (A0-A6 = physical Teensy pins 14-20)
  - UI Teensy: ST7796 TFT + XPT2046 touch header, plus BOTH sensor UART links
    (Serial1 pins 0/1 to Sensor A, Serial3 pins 14/15 to Sensor B)

*** PINOUT NOW VERIFIED AGAINST A REAL TEENSY 4.1 PHOTO ***
TEENSY_ROW1 / TEENSY_ROW2 below were corrected from an actual photo of the
board's silkscreen (my first pass was reconstructed from memory and had
real errors — no VIN pin exists in the main rows, it's 5V; pin 13 was
missing from row 1; row 2 runs 0-12 consecutively before 3.3V, not the
"0,1 then jump to 24" order I'd guessed). Still worth a final glance
against https://www.pjrc.com/teensy/pinout.html since I'm reading this off
one photo, not the datasheet — but confidence is much higher now. If
anything's still off, the fix is editing these two lists and re-running;
nothing else depends on the specific values, only on internal consistency.

Two things this correction changed, beyond the tables themselves:
  - Cal/curve buttons (pins 3, 4) are on ROW2, not ROW1 as I'd assumed —
    build_button() now checks which row a pin is actually on and offsets
    away from the Teensy body accordingly, instead of always assuming ROW1.
  - The TFT header's 8 signal pins are NOT all on one row: 7 of them
    (T_CS/T_IRQ/DC/RST/CS/MOSI/MISO — pins 6,7,8,9,10,11,12) are on ROW2,
    and only SCK (pin 13) is on ROW1. build_tft_header() now auto-routes
    the 7 ROW2 pins from a header placed below ROW2, and leaves SCK as a
    manual bridge (net-matched only) since reaching it means crossing
    under ROW2 — same reasoning as everything else left manual below.

SINGLE-SIDED COPPER: this board has one copper layer, so nothing can cross
anything else in copper — no vias, no routing under a row of pads. Every
connection listed below as "not auto-routed" will very likely need an
actual insulated wire jumper on the component side, not a hand-drawn PCB
trace, since a flat copper trace can't cross the Teensy's other pin row
(or another trace) without shorting. This script sets the board to 1
copper layer (see the bottom of the __main__ block) specifically so
KiCad's DRC and interactive router enforce that reality instead of
assuming a second layer bails you out.

WHAT THIS SCRIPT DOES vs LEAVES FOR YOU (same philosophy as the sensor-board
script this follows on from):
  - Draws the 3.3V/GND bus bars.
  - Places all 3 Teensy sockets, all 16 sensor channel circuits (headers +
    resistors + diodes, same divider circuit as your velostat/piezo boards),
    4 cal/curve buttons, the TFT+touch header, and 4 mounting holes.
  - Auto-routes ONLY short, local, single-purpose traces: header->resistor
    (or header->R1) inside each channel, and the 7 ROW2 pins of the TFT
    header (see above).
  - Everything else — each channel's signal net reaching its Teensy analog
    pin, the two UART links between the sensor Teensys and the UI Teensy,
    buttons reaching their Teensy pins, the TFT header's SCK pin, and
    every Teensy's power pins reaching the bus bars — is given a matching
    net name (so KiCad's ratsnest will show you exactly where a wire needs
    to go) but is NOT drawn as a trace, because it means crossing under
    the Teensy's other pin row and I'd rather you route it with DRC
    watching than have me guess at a path. Run Inspect > DRC to see the
    ratsnest and route those by hand (or with the interactive router).

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
BOARD_H = 180.0  # +30mm vs the original 150x150 — see space note below

PIN_PITCH = 2.54
ROW_GAP = 17.78  # 0.7in between a Teensy's two pin rows — mechanically fixed

# --- Teensy 4.1 pin tables (photo-verified, see disclaimer above) ---
# Index 0 = the end nearest the USB connector.
TEENSY_ROW1 = ["5V", "GND", "3V3", "23", "22", "21", "20", "19", "18", "17",
               "16", "15", "14", "13", "GND", "41", "40", "39", "38", "37",
               "36", "35", "34", "33"]
TEENSY_ROW2 = ["GND", "0", "1", "2", "3", "4", "5", "6", "7", "8",
               "9", "10", "11", "12", "3V3", "24", "25", "26", "27", "28",
               "29", "30", "31", "32"]

# --- Zone origins (x0,y0 = position of ROW1 index 0 / the USB end) ---
# Board grew from 150x150 to 150x180 so the channel stacks and the UI
# Teensy have real breathing room between them — that gap is exactly where
# you'll want to work when routing the channel->pin and UART ratsnest by
# hand or with KiCad's interactive router, and cramped spacing there was
# the main thing worth spending the extra room on (see the routing note
# at the top of this file for why those connections are left as ratsnest
# rather than auto-routed).
TEENSY_A_X, TEENSY_A_Y = 8.0, 10.0
TEENSY_B_X, TEENSY_B_Y = 85.0, 10.0
TEENSY_UI_X, TEENSY_UI_Y = 8.0, 135.0

VELO_X = 15.0
VELO_Y_START = 38.0
VELO_ROW_SPACING = 10.0  # was 9.0 — a bit more room per row for hand-soldering
VELO_R_OFFSET_X = 6.0

PIEZO_X = 95.0
PIEZO_Y_START = 38.0
PIEZO_ROW_SPACING = 13.0  # was 11.5 — same reasoning as VELO_ROW_SPACING
PIEZO_R1_OFFSET_X = 6.0
PIEZO_R2_OFFSET_Y = 4.0
PIEZO_DIODE_OFFSET_X = 20.0
PIEZO_DIODE_OFFSET_Y = -4.0

BUS_3V3_X = 3.0
BUS_GND_X = 147.0
BUS_Y0, BUS_Y1 = 5.0, 175.0

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
    """Places a 2-pin push button just outside whichever row teensy_pin is
    actually on (ROW1 pins get pulled up above the Teensy, ROW2 pins get
    pushed down below it), aligned to the pin's real X position read back
    from the placed pad. Checking the row instead of assuming ROW2 is what
    catches cases like pins 3/4, which turned out to be on ROW2 here."""
    net_gnd = get_or_create_net(board, "GND")
    net_sig = get_or_create_net(board, f"BTN_{ref}")

    tpad = teensy.pad(teensy_pin)
    cx = x_of(tpad)
    if teensy_pin in TEENSY_ROW1:
        cy = y_of(tpad) - y_offset  # open space is above ROW1
    else:
        cy = y_of(tpad) + y_offset  # open space is below ROW2

    btn = load_footprint(board, "Button_Switch_THT", "SW_PUSH_6mm", cx, cy, ref=ref)
    # SW_PUSH_6mm has 4 pads (two bridged pairs). Pads 1 & 3 are the two
    # switched nodes on the common 6mm tactile footprint — double check
    # this against your exact footprint variant before soldering.
    btn.Pads()[0].SetNet(net_sig)
    btn.Pads()[2].SetNet(net_gnd)

    tpad.SetNet(net_sig)  # ratsnest only — see header comment
    return btn


def build_tft_header(board, ui_teensy):
    """1x8 signal header placed just below the UI Teensy's ROW2. Of the 8
    TFT/touch pins, 7 (T_CS/T_IRQ/DC/RST/CS/MOSI/MISO — pins 6-12) are on
    ROW2, so those get placed directly above their targets and auto-routed
    straight up. SCK (pin 13) is the one outlier on ROW1 — it gets a header
    pad and a matching net, but reaching it means crossing under ROW2, so
    it's left as a ratsnest connection like everything else in that
    category (see the header comment)."""
    net_3v3 = get_or_create_net(board, "3V3")
    net_gnd = get_or_create_net(board, "GND")
    func_names = {"13": "SCK", "12": "MISO", "11": "MOSI", "10": "CS",
                  "9": "RST", "8": "DC", "7": "T_IRQ", "6": "T_CS"}

    # Ascending-X order on ROW2 for the 7 pins that live there. Guaranteed
    # by TEENSY_ROW2's internal consistency, not hand-picked coordinates.
    row2_pins = ["6", "7", "8", "9", "10", "11", "12"]

    first_pad = ui_teensy.pad(row2_pins[0])
    hx = x_of(first_pad) - PIN_PITCH  # leave one slot to the left for SCK
    hy = y_of(first_pad) + 10.0  # 10mm below ROW2 — the open/outer side

    hdr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x08_P2.54mm_Vertical",
                          hx, hy, ref="J_TFT")

    # Pad 0 = SCK (pin 13, on ROW1) — ratsnest only.
    net_sck = get_or_create_net(board, "TFT_SCK")
    hdr.Pads()[0].SetNet(net_sck)
    ui_teensy.pad("13").SetNet(net_sck)

    # Pads 1-7 = the 7 ROW2 pins, auto-routed straight up.
    for i, pin in enumerate(row2_pins):
        net = get_or_create_net(board, f"TFT_{func_names[pin]}")
        hdr.Pads()[i + 1].SetNet(net)
        tpad = ui_teensy.pad(pin)
        tpad.SetNet(net)
        route(board, hdr.Pads()[i + 1], tpad)  # straight up, safe

    # Separate 2-pin power header for the display module, just to the left
    # of the signal header — left as manual bridges to the bus bars.
    pwr = load_footprint(board, "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
                          hx - 2 * PIN_PITCH, hy, ref="J_TFT_PWR")
    pwr.Pads()[0].SetNet(net_gnd)
    pwr.Pads()[1].SetNet(net_3v3)
    return hdr, pwr


if __name__ == "__main__":
    board = pcbnew.GetBoard()
    board.SetCopperLayerCount(1)  # single-sided copper — see note at top of file

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
    for i, (mx, my) in enumerate([(5, 5), (145, 5), (5, 175), (145, 175)]):
        load_footprint(board, "MountingHole", "MountingHole_3.2mm_M3", mx, my, ref=f"MH{i + 1}")

    pcbnew.Refresh()
    print(f"Board size: {BOARD_W}mm x {BOARD_H}mm")
    print("Placed: 3x Teensy 4.1 socket, 9x velostat channel, 7x piezo channel,")
    print("4x cal/curve button, 1x TFT+touch header, 4x mounting hole.")
    print("")
    print("Manual bridges still needed — this is a single copper layer, so these")
    print("will very likely be actual wire jumpers on the component side, not")
    print("hand-drawn PCB traces (ratsnest will show you every one after DRC):")
    print(" - Each velostat channel: R.pad2 (GND) -> GND bus")
    print(" - Each piezo channel: R1.pad2->R2.pad1, R1.pad2->D anode,")
    print("   R2.pad2 (GND) and hdr.pad2 (GND) -> GND bus, D cathode -> 3V3 bus")
    print(" - Every channel's signal net -> its Teensy analog pin (A0-A8 on")
    print("   Sensor A, A0-A6 on Sensor B)")
    print(" - Cal/curve buttons -> their Teensy pin + GND")
    print(" - TFT header's SCK pin -> UI Teensy pin 13 (the one TFT signal on ROW1)")
    print(" - Each Teensy's GND/3V3 pads -> the bus bars")
    print(" - UART_A_1/2 (Sensor A <-> UI Serial1) and UART_B_1/2")
    print("   (Sensor B <-> UI Serial3)")
    print("")
    print("Pinout was corrected against a real Teensy 4.1 photo (see the top of")
    print("this file) — worth one more glance at pjrc.com/teensy/pinout.html")
    print("before ordering, but confidence is high. Run Inspect > DRC next.")