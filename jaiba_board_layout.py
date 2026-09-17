"""
Jaiba hexa-drum control board -- placement and net plan.

This module is the single source of truth for the board's geometry. It is pure
Python: no `pcbnew`, no KiCad install, no I/O. Two consumers use it:

  * jaiba-kicad-controlboard.py  -- applies the plan through pcbnew, for use
    from KiCad's Scripting Console.
  * tools/emit_board.py          -- writes a .kicad_pcb directly, so the board
    can be regenerated and geometry-checked on a machine without KiCad.

Design (see README):
  One Teensy 4.1 per hemisphere. Each drum sensor carries a velostat layer and
  a piezo layer, so every sensor costs two analog inputs. The Teensy 4.1 has
  exactly 18 analog inputs (A0-A17 = pins 14-27 and 38-41), so one Teensy can
  serve at most 9 dual-layer sensors.

  Right hemisphere   9 sensors     -> 18 analog channels  (Teensy full)
  Left hemisphere    7 sensors     -> 14 analog channels
                   + 2 loop sensors ->  4 channels       (18 total, full)
  UI Teensy          3 loop sensors ->  6 channels       (of its 16 free pins)

  14 of the 18 analog pins sit on ROW1 (the 5V/GND/3V3 row) and only 4
  (pins 24-27) on ROW2, so each sensor Teensy's channels are split into a
  7-cell row above ROW1 and a 2-cell row below ROW2.

  `links` are nets that exist but are deliberately not drawn in copper: on a
  single-sided board they are insulated wire jumpers, and KiCad shows them as
  ratsnest after DRC.
"""

# --------------------------------------------------------------------------
# Board
# --------------------------------------------------------------------------

# 168 wide, not 160: the drum solder pads extend each cell by ~6 mm, and at
# 160 the second column's pads would overhang the edge by 0.15 mm.
BOARD_W = 168.0
BOARD_H = 240.0

# --- copper sizes ----------------------------------------------------------
# This board is home-etched: no solder mask, no plated barrels, and the
# iron-transfer and etch steps are what limit the feature size. So everything
# is deliberately fat.
#
# The tightest feature on the whole board is the gap between two pads on the
# 2.54 mm header grid: PAD_DIA below leaves 2.54 - 2.2 = 0.34 mm there, and no
# track can pass between two adjacent header pads at all. That gap is the one
# to watch while etching -- if it bridges, drop PAD_DIA to 2.0 (0.54 mm gap)
# and re-run; the footprints are regenerated with it.
TRACK_W = 0.8          # signal
BUS_W = 1.0            # power bus bar
EDGE_W = 0.15
PAD_DIA = 2.2          # every plated through-hole pad, in every footprint

MOUNT_INSET = 4.0
MOUNT_FP = "MountingHole_3.2mm_M3"

# --------------------------------------------------------------------------
# Teensy 4.1 pin tables -- photo-verified AND cross-checked against the
# published Teensy 4.1 footprint + symbol (XenGi/teensy.pretty + teensy_library).
# Index 0 is the end nearest the USB connector.
# --------------------------------------------------------------------------

TEENSY_ROW1 = ["5V", "GND", "3V3", "23", "22", "21", "20", "19", "18", "17",
               "16", "15", "14", "13", "GND", "41", "40", "39", "38", "37",
               "36", "35", "34", "33"]
TEENSY_ROW2 = ["GND", "0", "1", "2", "3", "4", "5", "6", "7", "8",
               "9", "10", "11", "12", "3V3", "24", "25", "26", "27", "28",
               "29", "30", "31", "32"]

TEENSY_PITCH = 2.54
TEENSY_HALF_SPAN = 23 * TEENSY_PITCH / 2.0   # 29.21
TEENSY_ROW_Y = 7.62                          # rows at -7.62 (ROW1) / +7.62 (ROW2)
TEENSY_FP = "Teensy_4.1"

# Analog-capable pins in ascending X order along each row (the ordering that
# matters for keeping channel traces from crossing each other).
#   ROW1 analog: 23,22,21,20,19,18,17,16,15,14 then 41,40,39,38
#   ROW2 analog: 24,25,26,27
ROW1_ANALOG = ["23", "22", "21", "20", "19", "18", "17",
               "16", "15", "14", "41", "40", "39", "38"]
ROW2_ANALOG = ["24", "25", "26", "27"]


def teensy_pad_offset(pin):
    """Footprint-local (x, y) of a Teensy pad, addressed by pin name.

    Repeated pins (GND x3, 3V3 x2) resolve to their first occurrence; the
    emitter applies a net to every pad sharing that number.
    """
    if pin in TEENSY_ROW1 and TEENSY_ROW1.count(pin) == 1:
        i = TEENSY_ROW1.index(pin)
        return (-TEENSY_HALF_SPAN + i * TEENSY_PITCH, -TEENSY_ROW_Y)
    if pin in TEENSY_ROW2 and TEENSY_ROW2.count(pin) == 1:
        i = TEENSY_ROW2.index(pin)
        return (-TEENSY_HALF_SPAN + i * TEENSY_PITCH, TEENSY_ROW_Y)
    raise ValueError(f"pin {pin!r} is ambiguous or unknown")


def teensy_pad_abs(origin, pin):
    x, y = teensy_pad_offset(pin)
    return (origin[0] + x, origin[1] + y)


# --------------------------------------------------------------------------
# Sensor channel cell -- one drum sensor (velostat + piezo) = 5 parts
# --------------------------------------------------------------------------
#
# Local layout (origin = cell bottom-left), all offsets in mm:
#
#   J_PAD  1x04 at (2.00, 2.00)    pins: 1=3V3 2=VELO 3=PRAW 4=GND
#   R_VELO 100R  at (6.00, 4.54)   pad1=VELO  pad2=GND
#   R1     10k   at (6.00, 12.00)  pad1=PRAW  pad2=PSIG
#   R2     10k   at (16.16, 16.50) rot 180 -> pad1=PSIG pad2=GND
#   D      1N4148 at (8.54, 21.00) pad1=K(cathode)->3V3  pad2=A(anode)->PSIG
#
# R2 sits rotated 180 degrees so its PSIG pad lands directly under R1's PSIG
# pad, and the diode's anode lands under R2's -- that makes the PSIG node one
# straight vertical trace instead of a crossing-prone zig-zag.
#
# The diode's ANODE faces the ADC node and its CATHODE faces 3.3V. The original
# board had this back to front: cathode at the ADC node forward-biases the
# diode for any signal below ~2.6 V, clamping the piezo node and killing
# sensing rather than protecting it. (KiCad's D_DO-35 pad 1 is the cathode.)

CELL_PITCH_X = 18.0
CELL_PITCH_Y = 23.0
CELL_BBOX = (0.23, 0.23, 17.21, 22.25)   # x1, y1, x2, y2 including courtyards

R_FP = "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
D_FP = "D_DO-35_SOD27_P7.62mm_Horizontal"
HDR4_FP = "PinHeader_1x04_P2.54mm_Vertical"
HDR2_FP = "PinHeader_1x02_P2.54mm_Vertical"
HDR8_FP = "PinHeader_1x08_P2.54mm_Vertical"
SW_FP = "SW_PUSH_6mm"


def sensor_cell(ox, oy, cid, nets, mirrored=False):
    """Place one dual-layer sensor cell with its origin at (ox, oy).

    `nets` keys: velo (velostat ADC node), praw (raw piezo), psig (piezo ADC
    node). 3V3 and GND are board-wide.

    `mirrored=False` puts the connector on the cell's LEFT (used when the cell
    sits above its Teensy's ROW1). `mirrored=True` puts it on the RIGHT, so a
    column of cells along the board edge presents all its connectors outward
    where the drum cables arrive. The passives stay the same parts either way --
    only their positions and R2's origin shift.

    In the mirrored cell the velostat wiper runs left along y=2.54 above the
    100R body and then drops onto its pad, and the raw-piezo feed crosses the
    cell on a diagonal that clears R_VELO's pads; the piezo ADC node is still
    one straight vertical trace.
    """
    # (x, y, rot) for J_PAD, R_VELO, R1, R2, D. Pad roles follow the rotation:
    # a rot-180 resistor keeps pad 1 at its origin and puts pad 2 to its left.
    if mirrored:
        # True mirror of the layout below about x = 18.0, so the connector ends
        # up at the cell's right edge. Mirroring is what keeps the routing
        # crossing-free -- hand-placing the parts did not (the velostat feed ran
        # straight across the 3V3 pad).
        #
        # The raw-piezo feed steps left before it turns down: a single diagonal
        # from J.3 to R1.1 passes within 0.10 mm of J.4's ground pad once the
        # pads are 2.2 mm and the track is 0.8 mm, which will not etch reliably.
        j = (16.00, 2.00, 0)
        rvelo = (12.00, 4.54, 180)
        r1 = (12.00, 12.00, 180)
        r2 = (1.84, 16.50, 0)
        d = (9.46, 21.00, 180)
        # One signal wire pad per net, so the jumper never lands on a resistor
        # or diode lead. Each sits on the side its node already lives on --
        # putting both on the right would make the two routes topologically
        # cross, which no planar routing can fix:
        #   velostat node is on the left, so its pad goes in the free band
        #     between R_VELO and R1 (y 6.5..10.5);
        #   the piezo node is the vertical at x=1.84, so its pad goes right,
        #     crossed on y=18.50 which clears R2's pads by 2.0 mm and D's by
        #     2.5 mm.
        pads = [(6.00, 8.50, nets["velo"], "VELO"),
                (15.50, 18.50, nets["psig"], "PSIG")]
        # One bare pad per drum-cable pin, straight out from the connector.
        drum = [(2.00, "3V3", "1"), (4.54, nets["velo"], "2"),
                (7.08, nets["praw"], "3"), (9.62, "GND", "4")]
        drum_x = SOLDER_OFFSET_X
        trk = [
            dict(x1=ox + 16.00, y1=oy + 4.54, x2=ox + 12.00, y2=oy + 4.54, net=nets["velo"]),
            dict(x1=ox + 12.00, y1=oy + 4.54, x2=ox + 6.00, y2=oy + 4.54, net=nets["velo"]),
            dict(x1=ox + 6.00, y1=oy + 4.54, x2=ox + 6.00, y2=oy + 8.50, net=nets["velo"]),
            dict(x1=ox + 16.00, y1=oy + 7.08, x2=ox + 13.00, y2=oy + 7.08, net=nets["praw"]),
            dict(x1=ox + 13.00, y1=oy + 7.08, x2=ox + 13.00, y2=oy + 12.00, net=nets["praw"]),
            dict(x1=ox + 13.00, y1=oy + 12.00, x2=ox + 12.00, y2=oy + 12.00, net=nets["praw"]),
            dict(x1=ox + 1.84, y1=oy + 12.00, x2=ox + 1.84, y2=oy + 21.00, net=nets["psig"]),
            dict(x1=ox + 1.84, y1=oy + 18.50, x2=ox + 15.50, y2=oy + 18.50, net=nets["psig"]),
        ] + [dict(x1=ox + SOLDER_EXIT, y1=oy + y, x2=ox + SOLDER_OFFSET_X, y2=oy + y,
                  net=net) for y, net, _ in drum]
    else:
        j = (2.00, 2.00, 0)
        rvelo = (6.00, 4.54, 0)
        r1 = (6.00, 12.00, 0)
        r2 = (16.16, 16.50, 180)
        d = (8.54, 21.00, 0)
        trk = [
            dict(x1=ox + 2.00, y1=oy + 4.54, x2=ox + 6.00, y2=oy + 4.54, net=nets["velo"]),
            dict(x1=ox + 2.00, y1=oy + 7.08, x2=ox + 5.00, y2=oy + 7.08, net=nets["praw"]),
            dict(x1=ox + 5.00, y1=oy + 7.08, x2=ox + 5.00, y2=oy + 12.00, net=nets["praw"]),
            dict(x1=ox + 5.00, y1=oy + 12.00, x2=ox + 6.00, y2=oy + 12.00, net=nets["praw"]),
            dict(x1=ox + 16.16, y1=oy + 12.00, x2=ox + 16.16, y2=oy + 21.00, net=nets["psig"]),
        ]

    fp = [
        dict(name=HDR4_FP, ref=f"J_{cid}", value="Conn_01x04",
             x=ox + j[0], y=oy + j[1], rot=j[2],
             nets={"1": "3V3", "2": nets["velo"], "3": nets["praw"], "4": "GND"}),
        dict(name=R_FP, ref=f"RV_{cid}", value="100",
             x=ox + rvelo[0], y=oy + rvelo[1], rot=rvelo[2],
             nets={"1": nets["velo"], "2": "GND"}),
        dict(name=R_FP, ref=f"R1_{cid}", value="10k",
             x=ox + r1[0], y=oy + r1[1], rot=r1[2],
             nets={"1": nets["praw"], "2": nets["psig"]}),
        dict(name=R_FP, ref=f"R2_{cid}", value="10k",
             x=ox + r2[0], y=oy + r2[1], rot=r2[2],
             nets={"1": nets["psig"], "2": "GND"}),
        dict(name=D_FP, ref=f"D_{cid}", value="1N4148",
             x=ox + d[0], y=oy + d[1], rot=d[2],
             nets={"1": "3V3", "2": nets["psig"]}),
    ]
    for px, py, net, label in pads:
        fp.append(dict(name=WIREPAD_FP, ref=f"W_{cid}_{label}", value="WirePad",
                       x=ox + px, y=oy + py, rot=0, nets={"1": net}))
    for y, net, pin in drum:
        fp.append(dict(name=SOLDERPAD_FP, ref=f"SP_{cid}_{pin}", value="SolderPad",
                       x=ox + drum_x, y=oy + y, rot=0, nets={"1": net}))
    return fp, trk


def loop_cell(ox, oy, cid, velo_net, mirrored=False):
    """One velostat-only loop sensor: 2-pin header plus a 100R pulldown.

    Far smaller than a dual-layer sensor cell -- there is no piezo front end --
    and its wiper goes to a mux channel rather than straight to a Teensy pin.
    `mirrored` puts the connector on the right, like sensor_cell.
    """
    if mirrored:
        # Mirror of the layout below about x = 18.0: connector on the right, and
        # at x=16.00 so it lines up exactly with the dual cells' connectors in
        # the same column.
        jx, jy = 16.00, 2.00
        rx, ry, rot = 12.00, 4.54, 180
        # The loop cell is only 6 mm tall, so its pad sits just past the
        # connector, out into the aisle rather than inside the cell.
        pads = [(20.50, 4.54, velo_net, "VELO")]
        drum = [(2.00, "3V3", "1"), (4.54, velo_net, "2")]
        drum_x = LOOP_SOLDER_X
        trk = [dict(x1=ox + 16.00, y1=oy + 4.54, x2=ox + 12.00, y2=oy + 4.54,
                    net=velo_net),
               dict(x1=ox + 16.00, y1=oy + 4.54, x2=ox + 20.50, y2=oy + 4.54,
                    net=velo_net)] + [
               dict(x1=ox + SOLDER_EXIT, y1=oy + y, x2=ox + drum_x, y2=oy + y,
                    net=net) for y, net, _ in drum]
    else:
        jx, jy = 0.00, 0.00
        rx, ry, rot = 4.50, 2.54, 0
        pads = [(-4.50, 2.54, velo_net, "VELO")]
        trk = [dict(x1=ox, y1=oy + 2.54, x2=ox + 4.50, y2=oy + 2.54,
                    net=velo_net),
               dict(x1=ox, y1=oy + 2.54, x2=ox - 4.50, y2=oy + 2.54,
                    net=velo_net)]
    fp = [
        dict(name=HDR2_FP, ref=f"J_{cid}", value="Conn_01x02",
             x=ox + jx, y=oy + jy, rot=0, nets={"1": "3V3", "2": velo_net}),
        dict(name=R_FP, ref=f"RV_{cid}", value="100",
             x=ox + rx, y=oy + ry, rot=rot,
             nets={"1": velo_net, "2": "GND"}),
    ]
    for px, py, net, label in pads:
        fp.append(dict(name=WIREPAD_FP, ref=f"W_{cid}_{label}", value="WirePad",
                       x=ox + px, y=oy + py, rot=0, nets={"1": net}))
    for y, net, pin in drum:
        fp.append(dict(name=SOLDERPAD_FP, ref=f"SP_{cid}_{pin}", value="SolderPad",
                       x=ox + drum_x, y=oy + y, rot=0, nets={"1": net}))
    return fp, trk


def fan_wire_pads(footprints, tracks, items, sign, prefix):
    """Place one diagonal fan of wire pads.

    `items` is [(pin_x, pin_y, net, label)] already sorted left to right. Each
    pad steps further out from the pin row and further along than the last, so
    the stubs nest -- a stub always ends left of where the next one starts
    (i*LANDING_STEP < 2.54*(i+1)) -- and the wires comb out instead of bunching
    at the 2.54 mm pin pitch.
    """
    for i, (px, py, net, label) in enumerate(items):
        lx = px + i * LANDING_STEP
        ly = py + sign * (LANDING_BASE + i * LANDING_STEP)
        footprints.append(dict(name=WIREPAD_FP, ref=f"W_{prefix}_{label}",
                               value="WirePad", x=lx, y=ly, rot=0,
                               nets={"1": net}))
        tracks.append(dict(x1=px, y1=py, x2=lx, y2=ly, net=net, width=TRACK_W))


def add_wire_pads(footprints, tracks, jumpers, origins):
    """Give every wire jumper its own solder pad beside its Teensy.

    Soldering a wire onto a pin that already holds a Teensy socket means two
    joints in one hole and a lot of heat going into the socket. Each pad here is
    an extension of the pin row -- a short F.Cu stub runs from the pin out to a
    dedicated through-hole pad -- so the socket joint and the wire joint are
    separate and the socket never sees the iron again.

    Pads step diagonally, each one further out and further along than the last.
    The stubs stay nested because a stub always ends left of where the next one
    starts (i*STEP < 2.54*(i+1) for the pin pitch), so they cannot cross.
    """
    rows = {}
    for ref, pin, net in jumpers:
        ox, oy = origins[ref]
        dx, dy = teensy_pad_offset(pin)
        rows.setdefault((ref, "R1" if dy < 0 else "R2"), []).append(
            (ox + dx, oy + dy, pin, net, ref))

    for (ref, row), items in rows.items():
        items.sort(key=lambda t: t[0])
        sign = -1.0 if row == "R1" else 1.0
        short = ref.split("_")[-1]
        for i, (px, py, pin, net, _) in enumerate(items):
            lx = px + i * LANDING_STEP
            ly = py + sign * (LANDING_BASE + i * LANDING_STEP)
            footprints.append(dict(name=WIREPAD_FP, ref=f"W_{short}_{pin}",
                                   value="WirePad", x=lx, y=ly, rot=0,
                                   nets={"1": net}))
            tracks.append(dict(x1=px, y1=py, x2=lx, y2=ly, net=net,
                               width=TRACK_W))


# --------------------------------------------------------------------------
# Board floorplan
# --------------------------------------------------------------------------

N_HEMI_ROW1 = 7      # sensors in the right hemisphere's ROW1 channel group
N_HEMI_ROW2 = 2      # ... and the rest of the right hemisphere's sensors
N_LOOP = 5           # loop-control sensors, velostat-only, behind the mux

# --------------------------------------------------------------------------
# Floorplan
# --------------------------------------------------------------------------
#
# The drum pad cables arrive at the RIGHT-hand edge of the board, and the three
# Teensys' USB sockets point LEFT, so the board is split into two regions:
#
#   left  : the three Teensys stacked vertically, USB facing left, with their
#           cal/curve buttons, the mux, and the TFT header
#   right : every sensor connector, in two columns of cells whose connectors
#           face outward. The aisle between the columns is what lets a cable
#           reach the inner column.
#
# The cost of gathering the connectors here is that each cell's two runs to its
# Teensy become long jumpers (roughly 30-130 mm) instead of the ~15 mm they were
# when the cells sat directly above ROW1. They are jumpers either way on a
# single-sided board.
#
#   +----------------------------------------------------+
#   |  U_R  [buttons]                        colA   colB |
#   |  U_L  [buttons]   U_MUX                  ||     || |
#   |  U_UI [TFT]                              ||     || |
#   +----------------------------------------------------+
# (BOARD_W / BOARD_H are declared once, at the top of the module.)

TEENSY_X = 36.0                      # Teensy origin; body spans x 5.27..66.73

# Right region: two columns of cells, 18 mm apart in x.
COL_A_X = 104.0
COL_B_X = 136.0
COL_DUAL_Y0 = 8.0                    # first dual-layer cell row
COL_DUAL_PITCH = 25.0                # content height is 24.02 mm
COL_LOOP_Y0 = 210.0                  # loop cells go below the dual ones
COL_LOOP_PITCH = 8.0                 # content height is 6.09 mm
N_DUAL_PER_COL = 8                   # 8 + 8 = 16 dual-layer sensors
N_LOOP_COL_A = 3                     # 3 + 2 = 5 loop sensors
N_LOOP_COL_B = 2

# Buses run the full height between the two regions, where they are clear of
# every courtyard on both sides.
BUS_3V3_X = 92.0
BUS_GND_X = 100.0
BUS_Y0, BUS_Y1 = 4.0, BOARD_H - 4.0

# Left region: Teensys stacked, each with its own cal/curve buttons below it.
TEENSY_R_Y = 30.0
TEENSY_L_Y = 85.0
TEENSY_UI_Y = 165.0
# Cal/curve buttons. They sit clear of the pin rows and to the right, because
# the wire landing pads now fan diagonally out below ROW2 and would otherwise
# land inside the switches. Being off to the side also puts them somewhere a
# finger can actually reach.
BUTTON_X = 74.0
BTN_DY = 7.0                         # first button, below the Teensy origin
BTN_DY2 = 16.0                       # second, staggered so the bodies clear
MUX_POS = (36.0, 130.0)

# Wire landing pads. Every jumper link gets its own through-hole pad beside the
# Teensy it feeds, joined to the pin by a short F.Cu stub. Staggered so the pads
# step diagonally out from the pin row and the wires comb out instead of
# bunching at 2.54 mm pitch.
WIREPAD_FP = "WirePad_1x01"
# Bare copper pads for the drum-pad cable, outboard of each cell's connector.
# The cell's own vertical channels are all blocked by the passives, so these sit
# on the far side of the connector where there is clear space, and each is fed
# by a straight horizontal stub from its pin -- no fan, no crossings.
SOLDERPAD_FP = "SolderPad_1x01"
SOLDER_OFFSET_X = 20.5          # pad centre, relative to the cell origin
SOLDER_EXIT = 16.0              # the connector pin column
# The loop cell already carries a jumper pad at SOLDER_OFFSET_X, so its drum
# pads sit further out on the same stub (same net, so sharing it is harmless).
LOOP_SOLDER_X = 25.0
LANDING_BASE = 4.5      # first pad this far out from the pin row
LANDING_STEP = 1.15     # each successive pad steps out and along by this much

MOUNT_INSET = 6.0
MOUNT_FP = "MountingHole_3.2mm_M3"

MUX_FP = "CD74HC4067_Module"
# The module's own pin grid, relative to its origin. These must track
# tools/make_module_footprint.py's MY_MODULE -- row A (C0..C15) runs along the
# -y side and row B (SIG, S3..GND) along +y.
MUX_ROW_Y = 7.45
# Row A runs C15 (nearest the +x end) down to C0, so C_i sits at
# MUX_C15_X - (15 - i) * 2.54. Assuming C0 was the rightmost pad put every
# channel stub on the wrong pin.
MUX_C15_X = 19.05
MUX_SIG_X = 8.89
MUX_SIG_PIN = "24"                    # one of the four ROW2 analog pins, freed
                                      # by keeping the loop sensors off them
MUX_SEL_PINS = ("5", "6", "7", "8")   # S0..S3 on otherwise-unused digital pins

TFT_PIN_ORDER = ["6", "7", "8", "9", "10", "11", "12"]
TFT_NETS = ["TFT_T_CS", "TFT_T_IRQ", "TFT_DC", "TFT_RST", "TFT_CS",
            "TFT_MOSI", "TFT_MISO"]


def collect_nets(plan):
    """Deterministic net table shared by every consumer of the plan.

    GND and 3V3 come first so the numbering is stable across regenerations;
    net 0 is reserved by KiCad for "no net".
    """
    order = ["GND", "3V3"]
    seen = set(order)

    def add(name):
        if name and name not in seen:
            seen.add(name)
            order.append(name)

    for f in plan["footprints"]:
        for net in f["nets"].values():
            add(net)
    for t in plan["tracks"]:
        add(t.get("net"))
    for _, _, net in plan["links"]:
        add(net)
    return {name: i + 1 for i, name in enumerate(order)}


def plan():
    """Return the complete board plan as plain data."""
    footprints, tracks, links, jumpers = [], [], [], []

    def jumper(ref, pin, net):
        """A link that will be an insulated wire, so it also gets a solder pad.

        Links that are already drawn in copper (the TFT bus pins) go straight to
        `links` instead -- they need the net but not a pad.
        """
        links.append((ref, pin, net))
        jumpers.append((ref, pin, net))

    # --- power bus bars -----------------------------------------------------
    tracks.append(dict(x1=BUS_3V3_X, y1=BUS_Y0, x2=BUS_3V3_X, y2=BUS_Y1,
                       net="3V3", width=BUS_W))
    tracks.append(dict(x1=BUS_GND_X, y1=BUS_Y0, x2=BUS_GND_X, y2=BUS_Y1,
                       net="GND", width=BUS_W))

    # --- right region: two columns of sensor cells -------------------------
    # 16 dual-layer sensors in 8 rows of 2, then the 5 loop sensors filling the
    # bottom of the columns. Every connector faces right, toward the cables.
    #
    # Which pin pair drives which cell is unchanged from before -- only the
    # positions moved. R's 9 sensors use ROW1 pairs (7) plus ROW2 pairs (2);
    # L's 7 use ROW1 pairs, leaving L's ROW2 pins free for the mux.
    cell_specs = []
    for i in range(N_HEMI_ROW1):
        cell_specs.append(("R", i, ROW1_ANALOG[i], ROW1_ANALOG[N_HEMI_ROW1 + i]))
    for i in range(N_HEMI_ROW2):
        cell_specs.append(("R", N_HEMI_ROW1 + i,
                           ROW2_ANALOG[i], ROW2_ANALOG[N_HEMI_ROW2 + i]))
    for i in range(N_HEMI_ROW1):
        cell_specs.append(("L", i, ROW1_ANALOG[i], ROW1_ANALOG[N_HEMI_ROW1 + i]))

    loop_index = 0
    for col, (cx, n_loop_here) in enumerate(((COL_A_X, N_LOOP_COL_A),
                                             (COL_B_X, N_LOOP_COL_B))):
        for row in range(N_DUAL_PER_COL):
            hemi, idx, pin_v, pin_p = cell_specs[col * N_DUAL_PER_COL + row]
            cid = f"{hemi}{idx}"
            nets = dict(velo=f"{hemi}_VELO{idx}", praw=f"{hemi}_PRAW{idx}",
                        psig=f"{hemi}_PSIG{idx}")
            fp, trk = sensor_cell(cx, COL_DUAL_Y0 + row * COL_DUAL_PITCH, cid,
                                  nets, mirrored=True)
            footprints += fp
            tracks += trk
            jumper("U_" + hemi, pin_v, nets["velo"])
            jumper("U_" + hemi, pin_p, nets["psig"])

        for j in range(n_loop_here):
            cid = f"LOOP{loop_index}"
            fp, trk = loop_cell(cx, COL_LOOP_Y0 + j * COL_LOOP_PITCH, cid,
                                f"LOOP_VELO{loop_index}", mirrored=True)
            footprints += fp
            tracks += trk
            loop_index += 1

    # --- left region: the three Teensys, stacked, USB facing left ----------
    footprints.append(dict(name=TEENSY_FP, ref="U_R", value="Teensy4.1",
                           x=TEENSY_X, y=TEENSY_R_Y, rot=0,
                           nets={"GND": "GND", "3V3": "3V3"}))
    footprints.append(dict(name=TEENSY_FP, ref="U_L", value="Teensy4.1",
                           x=TEENSY_X, y=TEENSY_L_Y, rot=0,
                           nets={"GND": "GND", "3V3": "3V3"}))
    footprints.append(dict(name=TEENSY_FP, ref="U_UI", value="Teensy4.1",
                           x=TEENSY_X, y=TEENSY_UI_Y, rot=0,
                           nets={"GND": "GND", "3V3": "3V3"}))

    # cal / curve buttons on ROW2 pins 3 and 4 of each sensor Teensy. Staggered
    # in Y because two 6 mm switches on adjacent 2.54 mm pins cannot sit side by
    # side -- the original board put both at the same Y and they overlapped.
    for hemi, ty in (("R", TEENSY_R_Y), ("L", TEENSY_L_Y)):
        footprints.append(dict(name=SW_FP, ref=f"SW_CAL_{hemi}", value="SW_PUSH",
                               x=BUTTON_X, y=ty + BTN_DY, rot=0,
                               nets={"1": f"BTN_CAL_{hemi}", "2": "GND"}))
        footprints.append(dict(name=SW_FP, ref=f"SW_CURVE_{hemi}", value="SW_PUSH",
                               x=BUTTON_X, y=ty + BTN_DY2, rot=0,
                               nets={"1": f"BTN_CURVE_{hemi}", "2": "GND"}))
        jumper("U_" + hemi, "3", f"BTN_CAL_{hemi}")
        jumper("U_" + hemi, "4", f"BTN_CURVE_{hemi}")

    # --- the loop sensors' multiplexer -------------------------------------
    # Five velostat-only loop sensors need five analog inputs; L has only four
    # spare, so they share one ADC pin through a CD74HC4067 (4 select lines).
    # The percussive pads keep dedicated ADC pins -- the mux is never in their
    # signal path. The mux sits next to U_L so its SIG run to the ADC is short;
    # the five long runs are the loop wipers, which are low-impedance.
    mux_nets = {"VCC": "3V3", "GND": "GND", "EN": "GND", "SIG": "MUX_SIG"}
    for j, sel in enumerate(("S0", "S1", "S2", "S3")):
        mux_nets[sel] = f"MUX_{sel}"
    for i in range(N_LOOP):
        mux_nets[f"C{i}"] = f"LOOP_VELO{i}"
    footprints.append(dict(name=MUX_FP, ref="U_MUX", value="CD74HC4067",
                           x=MUX_POS[0], y=MUX_POS[1], rot=0, nets=mux_nets))
    # EN is tied to ground at the module, so the mux is always enabled -- no
    # Teensy pin spent on it.
    jumper("U_L", MUX_SIG_PIN, "MUX_SIG")
    for j, pin in enumerate(MUX_SEL_PINS):
        jumper("U_L", pin, f"MUX_S{j}")

    # --- UART links: Sensor R <-> UI Serial1 (0/1), Sensor L <-> Serial3 (14/15)
    for hemi, (ui_rx, ui_tx) in (("R", ("0", "1")), ("L", ("15", "14"))):
        jumper("U_UI", ui_rx, f"UART_{hemi}_1")
        jumper("U_UI", ui_tx, f"UART_{hemi}_2")
        jumper("U_" + hemi, "1", f"UART_{hemi}_1")
        jumper("U_" + hemi, "0", f"UART_{hemi}_2")

    # --- TFT + touch header (rotated 90 so its pads run along +X) ---------
    # UI ROW2 pins 6..12 are contiguous, so a header laid along +X with pad 1
    # one pitch to the left lands pads 2..8 exactly under pins 6..12 and the
    # seven links become straight vertical traces.
    pin6_x, pin6_y = teensy_pad_abs((TEENSY_X, TEENSY_UI_Y), "6")
    hdr_x = pin6_x - TEENSY_PITCH
    hdr_y = pin6_y + 9.0
    footprints.append(dict(name=HDR8_FP, ref="J_TFT", value="Conn_01x08",
                           x=hdr_x, y=hdr_y, rot=90,
                           nets={"1": "TFT_SCK", "2": TFT_NETS[0], "3": TFT_NETS[1],
                                 "4": TFT_NETS[2], "5": TFT_NETS[3], "6": TFT_NETS[4],
                                 "7": TFT_NETS[5], "8": TFT_NETS[6]}))
    for i, pin in enumerate(TFT_PIN_ORDER):
        px, py = teensy_pad_abs((TEENSY_X, TEENSY_UI_Y), pin)
        tracks.append(dict(x1=hdr_x + (i + 1) * TEENSY_PITCH, y1=hdr_y,
                           x2=px, y2=py, net=TFT_NETS[i], width=TRACK_W))
        links.append(("U_UI", pin, TFT_NETS[i]))
    # SCK lives on ROW1 -> jumper, like every other cross-row link.
    jumper("U_UI", "13", "TFT_SCK")

    footprints.append(dict(name=HDR2_FP, ref="J_TFT_PWR", value="Conn_01x02",
                           x=hdr_x - 8.0, y=hdr_y, rot=90,
                           nets={"1": "GND", "2": "3V3"}))

    # --- multiplexer extension pads ----------------------------------------
    # The module plugs into its own header, so its pins are already occupied --
    # same problem as the Teensy sockets. Each pin that carries a wire gets a
    # pad of its own: the channel inputs fan up, the control pins fan down.
    mx, my = MUX_POS
    chan = []
    for i in range(N_LOOP):
        chan.append((mx + MUX_C15_X - (15 - i) * 2.54, my - MUX_ROW_Y,
                     f"LOOP_VELO{i}", f"C{i}"))
    chan.sort(key=lambda t: t[0])
    fan_wire_pads(footprints, tracks, chan, -1.0, "MUX")

    ctrl = []
    for label, net, xi in (("GND", "GND", MUX_SIG_X - 7 * 2.54),
                           ("VCC", "3V3", MUX_SIG_X - 6 * 2.54),
                           ("EN", "GND", MUX_SIG_X - 5 * 2.54),
                           ("S0", "MUX_S0", MUX_SIG_X - 4 * 2.54),
                           ("S1", "MUX_S1", MUX_SIG_X - 3 * 2.54),
                           ("S2", "MUX_S2", MUX_SIG_X - 2 * 2.54),
                           ("S3", "MUX_S3", MUX_SIG_X - 1 * 2.54),
                           ("SIG", "MUX_SIG", MUX_SIG_X)):
        ctrl.append((mx + xi, my + MUX_ROW_Y, net, label))
    fan_wire_pads(footprints, tracks, ctrl, 1.0, "MUX")

    # --- wire landing pads, one per jumper ---------------------------------
    add_wire_pads(footprints, tracks, jumpers,
                  {"U_R": (TEENSY_X, TEENSY_R_Y),
                   "U_L": (TEENSY_X, TEENSY_L_Y),
                   "U_UI": (TEENSY_X, TEENSY_UI_Y)})

    # --- mounting holes -----------------------------------------------------
    for n, (mx, my) in enumerate([(MOUNT_INSET, MOUNT_INSET),
                                  (BOARD_W - MOUNT_INSET, MOUNT_INSET),
                                  (MOUNT_INSET, BOARD_H - MOUNT_INSET),
                                  (BOARD_W - MOUNT_INSET, BOARD_H - MOUNT_INSET)], 1):
        footprints.append(dict(name=MOUNT_FP, ref=f"MH{n}", value="MountingHole",
                               x=mx, y=my, rot=0, nets={}))

    edges = [
        (0.0, 0.0, BOARD_W, 0.0),
        (BOARD_W, 0.0, BOARD_W, BOARD_H),
        (BOARD_W, BOARD_H, 0.0, BOARD_H),
        (0.0, BOARD_H, 0.0, 0.0),
    ]
    return dict(footprints=footprints, tracks=tracks, links=links, edges=edges,
                width=BOARD_W, height=BOARD_H)


if __name__ == "__main__":
    p = plan()
    print(f"board          {p['width']} x {p['height']} mm")
    print(f"footprints     {len(p['footprints'])}")
    print(f"copper tracks  {len(p['tracks'])}")
    print(f"jumper links   {len(p['links'])}")
    nets = sorted({t["net"] for t in p["tracks"]} |
                  {l[2] for l in p["links"]} |
                  {n for f in p["footprints"] for n in f["nets"].values()})
    print(f"nets           {len(nets)}")
