"""
Render the board to an SVG preview, without KiCad.

Useful for eyeballing a floorplan change -- where the connectors ended up, how
much of the board is empty, whether the jumper runs are sane -- on a machine
that has no KiCad installed. It draws, in board coordinates:

    board outline        dark green
    F.Cu tracks          bus bars gold, signal pale
    B.Cu guide           dashed light blue (NOT fabricated)
    pads                 grey, outlined by part class
    courtyards           thin outline, coloured by part class
    Teensy USB ends      a blue tab on the side the cable exits

Colours are by part class (Teensy, mux, switch, mounting hole, everything else),
not by net, so this is a placement view rather than a routing view.

Convert to PNG with any SVG renderer, e.g.
    google-chrome --headless --screenshot=board.png --window-size=1000,1500 \\
        --force-device-scale-factor=3 file://$PWD/board_preview.svg

Run:  python3 tools/preview_board.py [out.svg] [board.kicad_pcb]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_sexpr as ks  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BOARD = os.path.join(REPO, "kicad-control-board", "kicad-control-board.kicad_pcb")
DEFAULT_OUT = "/tmp/board_preview.svg"

CLASS_COLOUR = {
    "Teensy_4.1": "#2e8bff",
    "CD74HC4067_Module": "#ff8c00",
    "SW_PUSH_6mm": "#cc44cc",
    "WirePad_1x01": "#ffd24d",
    "SolderPad_1x01": "#7dffb0",
    "MountingHole_3.2mm_M3": "#888888",
}
LABEL_PARTS = ("Teensy_4.1", "CD74HC4067_Module")


def rot_off(x, y, rot):
    rot = int(rot) % 360
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot]


def render(board_path, out_path, margin=8.0):
    board = ks.parse(open(board_path, encoding="utf-8").read())

    xs, ys = [], []
    for g in ks.children(board, "gr_line"):
        lay = ks.child(g, "layer")
        if lay and lay[1] == "Edge.Cuts":
            for k in ("start", "end"):
                pt = ks.child(g, k)
                xs.append(float(pt[1]))
                ys.append(float(pt[2]))
    W, H = max(xs), max(ys)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'width="{W + 2 * margin}mm" height="{H + 2 * margin}mm" '
         f'viewBox="{-margin} {-margin} {W + 2 * margin} {H + 2 * margin}">',
         f'<rect x="0" y="0" width="{W}" height="{H}" '
         'fill="#0b3d2e" stroke="black" stroke-width="0.3"/>']

    for s in ks.children(board, "segment"):
        st, en = ks.child(s, "start"), ks.child(s, "end")
        w = float(ks.child(s, "width")[1])
        lay = ks.child(s, "layer")
        layer = lay[1] if lay else "F.Cu"
        if layer == "B.Cu":
            # the wire-jumper guide -- dashed, so it reads as "wire goes here",
            # not as etched copper
            dash = ' stroke-dasharray="1.2 0.9"'
            colour = "#4fc3f7"
        else:
            dash = ""
            colour = "#c8a020" if w > 0.5 else "#e8e0b0"
        o.append(f'<line x1="{st[1]}" y1="{st[2]}" x2="{en[1]}" y2="{en[2]}" '
                 f'stroke="{colour}" stroke-width="{w}"{dash}/>')

    for f in ks.children(board, "footprint"):
        name = f[1]
        at = ks.child(f, "at")
        ox, oy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0
        ref = next((str(p[2]) for p in ks.children(f, "property")
                    if p[1] == "Reference"), "?")
        colour = CLASS_COLOUR.get(name, "#c04040")

        for p in ks.children(f, "pad"):
            pat = ks.child(p, "at")
            dx, dy = rot_off(float(pat[1]), float(pat[2]), rot)
            sz = ks.child(p, "size")
            w, h = float(sz[1]), float(sz[2])
            cx, cy = ox + dx, oy + dy
            if p[3] in ("rect", "roundrect", "oval") and abs(w - h) > 1e-6:
                o.append(f'<rect x="{cx - w / 2:.2f}" y="{cy - h / 2:.2f}" '
                         f'width="{w:.2f}" height="{h:.2f}" fill="#d9d9d9" '
                         f'stroke="{colour}" stroke-width="0.15"/>')
            else:
                o.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{max(w, h) / 2:.2f}" '
                         f'fill="#d9d9d9" stroke="{colour}" stroke-width="0.15"/>')

        bx, by = [], []
        for g in ks.children(f, "fp_line"):
            lay = ks.child(g, "layer")
            if not lay or lay[1] != "F.CrtYd":
                continue
            for k in ("start", "end"):
                pt = ks.child(g, k)
                dx, dy = rot_off(float(pt[1]), float(pt[2]), rot)
                bx.append(ox + dx)
                by.append(oy + dy)
        if bx:
            o.append(f'<rect x="{min(bx):.2f}" y="{min(by):.2f}" '
                     f'width="{max(bx) - min(bx):.2f}" height="{max(by) - min(by):.2f}" '
                     f'fill="none" stroke="{colour}" stroke-width="0.12"/>')

        if name == "WirePad_1x01":
            o.append(f'<circle cx="{ox:.2f}" cy="{oy:.2f}" r="2.4" '
                     'fill="none" stroke="#ffd24d" stroke-width="0.25"/>')
        if name in LABEL_PARTS or ref.startswith(("J_LOOP", "J_R0", "J_L0")):
            o.append(f'<text x="{ox:.1f}" y="{oy:.1f}" font-size="3" fill="white" '
                     f'text-anchor="middle">{ref}</text>')

        if name == "Teensy_4.1":
            # the footprint's -X end is the USB connector
            ux, uy = ox - 30.48, oy
            o.append(f'<rect x="{ux:.1f}" y="{uy - 3.5:.1f}" width="4" height="7" '
                     'fill="#2e8bff"/>')

    o.append("</svg>")
    open(out_path, "w", encoding="utf-8").write("\n".join(o) + "\n")
    return W, H


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    board = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_BOARD
    W, H = render(board, out)
    print(f"wrote {out}  ({W:.1f} x {H:.1f} mm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
