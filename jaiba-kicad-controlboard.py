"""
KiCad pcbnew generator -- Jaiba hexa-drum control board.

Generates the whole board from the plan in `jaiba_board_layout.py`: three
Teensy 4.1 sockets (left hemisphere, right hemisphere, UI), 21 dual-layer
sensor channels, cal/curve buttons, the TFT+touch header and the power buses.

  * Right hemisphere Teensy : 9 sensors x (velostat + piezo) = 18 channels
  * Left hemisphere Teensy  : 7 sensors + 2 loop sensors    = 18 channels
  * UI Teensy               : 3 loop sensors + display      =  6 channels

Each drum sensor costs TWO analog inputs (one per layer) and a Teensy 4.1 has
exactly 18 analog inputs, so a hemisphere Teensy is full at 9 sensors.

WHAT THIS SCRIPT DRAWS vs LEAVES FOR YOU
  Drawn in copper: the two power bus bars, the short intra-cell links
  (header->resistor, and the piezo node chain), and the seven TFT/touch signals
  that run straight from the header up to the UI Teensy's ROW2.
  Left as ratsnest (run Inspect > DRC to see them): each channel's two runs to
  its Teensy analog pin, every cell's 3V3/GND taps, the buttons, the UART
  links and the TFT SCK line. This board is single-sided copper, so a flat
  trace cannot cross another trace or a pin row -- those connections are
  insulated wire jumpers on the component side. `jaiba_board_layout.py`
  reports how many there are.

Run from KiCad's Scripting Console with a board open:

    exec(open(r'/path/to/jaiba-kicad-controlboard.py').read())

Clear the board first if you are re-running over a previous test. There is no
`pcbnew` module outside KiCad; to regenerate without KiCad use
`python3 tools/emit_board.py`, which writes the identical board from the same
plan (and `tools/verify_board.py` checks it geometrically).
"""

import os
import sys

try:
    import pcbnew
except ImportError:  # pragma: no cover - depends on the host environment
    raise SystemExit(
        "This script needs KiCad's `pcbnew` module -- run it from KiCad's "
        "Scripting Console. To regenerate the board without KiCad, run "
        "`python3 tools/emit_board.py`."
    )

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                                    # exec() inside KiCad
    _HERE = os.getcwd()
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import jaiba_board_layout as L  # noqa: E402

LIBDIR = os.path.join(_HERE, "kicad-control-board", "jaiba.pretty")
OUT_PATH = os.path.join(_HERE, "kicad-control-board", "kicad-control-board.kicad_pcb")


def mm(v):
    return pcbnew.FromMM(v)


def get_or_create_net(board, name):
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def add_footprint(board, item, nets):
    fp = pcbnew.FootprintLoad(LIBDIR, item["name"])
    if fp is None:
        raise RuntimeError(
            f"Could not load '{item['name']}' from '{LIBDIR}'. "
            f"The footprint library ships with this repo -- check the path."
        )
    fp.SetPosition(pcbnew.VECTOR2I(mm(item["x"]), mm(item["y"])))
    rot = item.get("rot", 0)
    if rot:
        fp.SetOrientationDegrees(rot)
    fp.SetReference(item["ref"])
    fp.SetValue(item["value"])
    board.Add(fp)
    for pad in fp.Pads():
        name = nets.get(pad.GetNumber())
        if name:
            pad.SetNet(name)
    return fp


def main():
    plan = L.plan()
    netnum = L.collect_nets(plan)

    board = pcbnew.GetBoard()
    # KiCad requires an even copper-layer count and does not support a
    # single-layer stackup, so the board is 2-layer here. Whether the fab
    # etches one side is a manufacturing choice, not a board-setup one.
    board.SetCopperLayerCount(2)

    nets = {name: get_or_create_net(board, name) for name in netnum}

    # Jumper links: nets that reach a footprint but are not drawn in copper.
    extra = {}
    for ref, pin, net in plan["links"]:
        extra.setdefault(ref, {})[pin] = net

    for item in plan["footprints"]:
        merged = {**item["nets"], **extra.get(item["ref"], {})}
        add_footprint(board, item, merged)

    for t in plan["tracks"]:
        if "x1" not in t:
            continue
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pcbnew.VECTOR2I(mm(t["x1"]), mm(t["y1"])))
        tr.SetEnd(pcbnew.VECTOR2I(mm(t["x2"]), mm(t["y2"])))
        tr.SetWidth(mm(t.get("width", L.TRACK_W)))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNet(nets[t["net"]])
        board.Add(tr)

    for x1, y1, x2, y2 in plan["edges"]:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        s.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(L.EDGE_W))
        board.Add(s)

    pcbnew.Refresh()
    pcbnew.SaveBoard(OUT_PATH, board)

    print(f"Board       {plan['width']} x {plan['height']} mm (2 copper layers)")
    print(f"Placed      {len(plan['footprints'])} footprints, "
          f"{len(netnum)} nets, {len(plan['tracks'])} tracks")
    print("")
    print(f"Still to route as wire jumpers ({len(plan['links'])} links):")
    print(" - every sensor channel's velostat and piezo node -> Teensy analog pin")
    print(" - every cell's 3V3 and GND taps -> the bus bars")
    print(" - cal / curve buttons -> Teensy pin 3/4 and GND")
    print(" - UART links: Sensor R <-> UI Serial1 (0/1), Sensor L <-> UI Serial3 (14/15)")
    print(" - TFT SCK -> UI Teensy pin 13 (the one TFT signal on ROW1)")
    print("")
    print(f"Saved {OUT_PATH}")
    print("Run Inspect > DRC next.")


if __name__ == "__main__":
    main()
