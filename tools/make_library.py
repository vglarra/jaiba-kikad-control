"""
Extract a project-local KiCad footprint library from the committed board.

The board generator needs footprints for the passives, headers, switch and
mounting holes. Those normally come from KiCad's system libraries, which means
the generator only runs on a machine that has KiCad installed and pointed at
the right library path (the original script hard-coded a Windows path).

The committed .kicad_pcb already embeds a full copy of every footprint it uses,
so this script lifts them back out into `kicad-control-board/jaiba.pretty/`.
After that the project is self-contained: the generator can load every
footprint from the repo without depending on a KiCad install.

Run:  python3 tools/make_library.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kicad_sexpr as ks          # noqa: E402
import jaiba_board_layout as L    # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(REPO, "kicad-control-board", "kicad-control-board.kicad_pcb")
LIBDIR = os.path.join(REPO, "kicad-control-board", "jaiba.pretty")


def resize_tht_pads(fp, dia):
    """Widen every plated through-hole pad to `dia`.

    These footprints arrive from the board with whatever annular ring KiCad's
    library uses, which assumes a plated, masked, professionally made board.
    This one is home-etched: the copper ring is the only thing holding solder,
    and there is no mask to stop a bridge. So every plated pad is widened to a
    single size.

    Bare NPTH holes (the mounting holes) are left alone -- they have no copper.
    The drill is untouched, so only the annular ring grows.
    """
    changed = 0
    for p in ks.children(fp, "pad"):
        if p[2] != "thru_hole":
            continue
        size = ks.child(p, "size")
        if size is None:
            continue
        size[1] = str(dia)
        size[2] = str(dia)
        changed += 1
    return changed


# Footprints lifted verbatim out of the committed board.
WANTED = [
    "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
    "D_DO-35_SOD27_P7.62mm_Horizontal",
    "PinHeader_1x02_P2.54mm_Vertical",
    "PinHeader_1x08_P2.54mm_Vertical",
    "SW_PUSH_6mm",
    "MountingHole_3.2mm_M3",
]

# Only meaningful at the footprint's own top level. Pads and graphics also
# carry `(at ...)` -- those are geometry, not placement, and must be kept.
TOP_LEVEL_INSTANCE_KEYS = ("at", "uuid", "path", "sheetname", "sheetfile", "tstamp")


def new_uuid():
    # Quoted: these are emitted into the board file and KiCad writes every uuid
    # as a string.
    return ks.Quoted(str(uuid.uuid4()))


def strip_uuid(node):
    """Drop every uuid so KiCad assigns fresh ones when the part is placed."""
    out = []
    for item in node:
        if isinstance(item, list):
            if item and item[0] == "uuid":
                continue
            item = strip_uuid(item)
        out.append(item)
    return out


def strip_instance(node):
    """Drop instance-only data so the node is valid as a library footprint."""
    out = []
    for item in node:
        if isinstance(item, list):
            key = item[0] if item else None
            if key in TOP_LEVEL_INSTANCE_KEYS:
                continue
            if key == "pad":
                item = [x for x in item if not (isinstance(x, list) and x and x[0] == "net")]
            item = strip_uuid(item)
        out.append(item)
    return out


def set_property(node, name, value):
    for prop in ks.children(node, "property"):
        if prop[1] == name:
            prop[2] = ks.Quoted(value)
            return True
    return False


def clone_pad(pad, number, y):
    """Clone a header pad, renumbering it and moving it to `y`."""
    out = []
    for item in pad:
        if isinstance(item, list):
            if item[0] == "at":
                out.append(["at", "0", str(y)])
                continue
            if item[0] == "uuid":
                out.append(["uuid", new_uuid()])
                continue
        out.append(item)
    out[1] = ks.Quoted(str(number))
    return out


def make_pin_header(n):
    """Build PinHeader_1xN by generalising the extracted 1x02.

    KiCad's vertical pin-header footprints follow a fixed rule that the 1x02
    and 1x08 in the committed board both obey: for N pins on a 2.54 mm pitch,
    the silk box runs from y=-1.38 to y=2.54*(N-1)+1.38 and the courtyard from
    y=-1.77 to y=2.54*(N-1)+1.78. Verified against N=2 (3.92 / 4.32) and
    N=8 (19.16 / 19.55).
    """
    src = os.path.join(LIBDIR, "PinHeader_1x02_P2.54mm_Vertical.kicad_mod")
    fp = strip_instance(ks.parse(open(src, encoding="utf-8").read()))

    old_last = 2.54 * 1
    new_last = 2.54 * (n - 1)
    old_silk, new_silk = old_last + 1.38, new_last + 1.38
    old_crtyd, new_crtyd = old_last + 1.78, new_last + 1.78

    # Grow the pad row.
    template = ks.children(fp, "pad")[1]  # pad 2, a plain circle
    pads = ks.children(fp, "pad")
    for k in range(2, n):
        fp.append(clone_pad(template, k + 1, 2.54 * k))

    # Stretch silk, courtyard and the value text by the same rule.
    def retarget(node):
        for item in node:
            if isinstance(item, list):
                if item[0] in ("start", "end", "at", "center"):
                    for i in (2,):  # y component
                        if i < len(item):
                            try:
                                v = float(item[i])
                            except ValueError:
                                continue
                            if abs(v - old_silk) < 1e-6:
                                item[i] = str(round(new_silk, 2))
                            elif abs(v - old_crtyd) < 1e-6:
                                item[i] = str(round(new_crtyd, 2))
                            elif abs(v - (old_last + 2.38)) < 1e-6:
                                item[i] = str(round(new_last + 2.38, 2))
                retarget(item)
        return node

    retarget(fp)
    name = f"PinHeader_1x{n:02d}_P2.54mm_Vertical"
    fp[1] = ks.Quoted(name)
    set_property(fp, "Value", name)
    for prop in ks.children(fp, "property"):
        if prop[1] == "Description":
            prop[2] = ks.Quoted(f"Through hole straight pin header, 1x{n:02d}, 2.54mm pitch, single row")
    for tag in ks.children(fp, "tags") or ks.children(fp, "tag"):
        tag[1] = ks.Quoted(f"Through hole pin header THT 1x{n:02d} 2.54mm single row")
    return fp


def make_wire_pad():
    """A single through-hole pad for landing one jumper wire.

    Soldering a wire onto a pin that is already holding a Teensy socket puts two
    joints in one hole and pours heat into the socket. So each jumper gets its
    own pad beside the Teensy, reached by a short F.Cu stub from the pin: the
    socket joint and the wire joint are separate, and the socket never sees the
    iron again.
    """
    fp = ['footprint', ks.Quoted("WirePad_1x01"),
          ["version", "20241229"],
          # These MUST be quoted strings. KiCad's parser rejects an unquoted
          # generator_version with a bare "Expecting 'symbol'" that names a line
          # number and nothing else -- which is how a hand-built node like this
          # one differs from a node extracted from a board KiCad wrote.
          ["generator", ks.Quoted("jaiba-make_library")],
          ["generator_version", ks.Quoted("9.0")],
          ["layer", ks.Quoted("F.Cu")],
          ["descr", ks.Quoted("Single through-hole pad for soldering a wire jumper")],
          ["tags", ks.Quoted("wire pad jumper solder landing")],
          ["attr", "through_hole"]]
    ref_at = ["at", "0", "-2.38", "0"]
    val_at = ["at", "0", "2.38", "0"]
    for key, val, at, layer in (("Reference", "REF**", ref_at, "F.SilkS"),
                                ("Value", "WirePad_1x01", val_at, "F.Fab")):
        fp.append(["property", ks.Quoted(key), ks.Quoted(val), at,
                   ["layer", ks.Quoted(layer)],
                   ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]])
    fp.append(["property", ks.Quoted("Datasheet"), ks.Quoted(""), ["at", "0", "0", "0"],
               ["layer", "F.Fab"], ["hide", "yes"],
               ["effects", ["font", ["size", "1.27", "1.27"], ["thickness", "0.15"]]]])
    fp.append(["property", ks.Quoted("Description"), ks.Quoted(""), ["at", "0", "0", "0"],
               ["layer", "F.Fab"], ["hide", "yes"],
               ["effects", ["font", ["size", "1.27", "1.27"], ["thickness", "0.15"]]]])
    fp.append(["duplicate_pad_numbers_are_jumpers", "no"])
    for lay, w in (("F.SilkS", "0.12"), ("F.CrtYd", "0.05")):
        r = 1.35 if lay == "F.SilkS" else 1.35
        for (x1, y1, x2, y2) in ((-r, -r, r, -r), (r, -r, r, r), (r, r, -r, r), (-r, r, -r, -r)):
            fp.append(["fp_line", ["start", str(x1), str(y1)], ["end", str(x2), str(y2)],
                       ["stroke", ["width", w], ["type", "solid"]],
                       ["layer", ks.Quoted(lay)], ["uuid", new_uuid()]])
    fp.append(["pad", ks.Quoted("1"), "thru_hole", "circle",
               ["at", "0", "0"], ["size", str(L.PAD_DIA), str(L.PAD_DIA)],
               ["drill", "1"], ["layers", ks.Quoted("*.Cu"), ks.Quoted("*.Mask")],
               ["remove_unused_layers", "no"], ["uuid", new_uuid()]])
    fp.append(["embedded_fonts", "no"])
    return fp


def make_solder_pad():
    """A bare rectangular copper pad for landing a drum-pad cable.

    The drum cable takes all the movement, and a 2.2 mm round through-hole pad
    is not much to solder to. This sits just outboard of the cell's connector on
    the same net, so the wire can be soldered along a 4 mm run of copper instead
    of onto a single small pad. Being surface-mount it adds no hole to drill.
    """
    fp = ['footprint', ks.Quoted("SolderPad_1x01"),
          ["version", "20241229"],
          ["generator", ks.Quoted("jaiba-make_library")],
          ["generator_version", ks.Quoted("9.0")],
          ["layer", ks.Quoted("F.Cu")],
          ["descr", ks.Quoted("Bare 4.0 x 2.2 mm copper pad for soldering a drum-pad cable")],
          ["tags", ks.Quoted("solder pad strain relief drum cable")],
          ["attr", "smd"]]
    for key, val, y, layer in (("Reference", "REF**", -2.38, "F.SilkS"),
                               ("Value", "SolderPad_1x01", 2.38, "F.Fab")):
        fp.append(["property", ks.Quoted(key), ks.Quoted(val),
                   ["at", "0", str(y), "0"], ["layer", ks.Quoted(layer)],
                   ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]])
    for key in ("Datasheet", "Description"):
        fp.append(["property", ks.Quoted(key), ks.Quoted(""), ["at", "0", "0", "0"],
                   ["layer", ks.Quoted("F.Fab")], ["hide", "yes"],
                   ["effects", ["font", ["size", "1.27", "1.27"], ["thickness", "0.15"]]]])
    fp.append(["duplicate_pad_numbers_are_jumpers", "no"])
    # 2.0 mm tall inside a 2.4 mm courtyard: adjacent pins are 2.54 mm apart, so
    # anything taller makes neighbouring courtyards overlap.
    for (x1, y1, x2, y2) in ((-2.0, -1.2, 2.0, -1.2), (2.0, -1.2, 2.0, 1.2),
                             (2.0, 1.2, -2.0, 1.2), (-2.0, 1.2, -2.0, -1.2)):
        fp.append(["fp_line", ["start", str(x1), str(y1)], ["end", str(x2), str(y2)],
                   ["stroke", ["width", "0.05"], ["type", "solid"]],
                   ["layer", ks.Quoted("F.CrtYd")], ["uuid", new_uuid()]])
    # F.Cu + F.Mask only: no paste layer, because there is no stencil. A bare
    # exposed copper pad is exactly what a hand-soldered wire wants.
    fp.append(["pad", ks.Quoted("1"), "smd", "rect",
               ["at", "0", "0"], ["size", "4", "2"],
               ["layers", ks.Quoted("F.Cu"), ks.Quoted("F.Mask")],
               ["roundrect_rratio", "0"], ["uuid", new_uuid()]])
    fp.append(["embedded_fonts", "no"])
    return fp


def main():
    root = ks.parse(open(BOARD, encoding="utf-8").read())
    by_name = {}
    for fp in ks.children(root, "footprint"):
        by_name.setdefault(fp[1], fp)

    os.makedirs(LIBDIR, exist_ok=True)
    written = []
    total = 0

    for name in WANTED:
        fp = by_name.get(name)
        if fp is None:
            raise SystemExit(f"footprint {name!r} not found in {BOARD}")
        node = strip_instance(fp)
        node[1] = ks.Quoted(name)
        set_property(node, "Reference", "REF**")
        set_property(node, "Value", name)
        total += resize_tht_pads(node, L.PAD_DIA)
        ks.dump_file(node, os.path.join(LIBDIR, name + ".kicad_mod"))
        written.append(name)

    # The synthesized 1x04 is built from the extracted 1x02, so it inherits the
    # resized pads; resize anyway so the pass is unconditional.
    hdr4 = make_pin_header(4)
    total += resize_tht_pads(hdr4, L.PAD_DIA)
    ks.dump_file(hdr4, os.path.join(LIBDIR, "PinHeader_1x04_P2.54mm_Vertical.kicad_mod"))
    written.append("PinHeader_1x04_P2.54mm_Vertical")

    wp = make_wire_pad()
    ks.dump_file(wp, os.path.join(LIBDIR, "WirePad_1x01.kicad_mod"))
    written.append("WirePad_1x01")

    sp = make_solder_pad()
    ks.dump_file(sp, os.path.join(LIBDIR, "SolderPad_1x01.kicad_mod"))
    written.append("SolderPad_1x01")

    for name in sorted(written):
        print("wrote", os.path.join("kicad-control-board", "jaiba.pretty", name + ".kicad_mod"))
    print(f"plated pads widened to {L.PAD_DIA} mm: {total}")


if __name__ == "__main__":
    main()
