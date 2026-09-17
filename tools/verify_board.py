"""
Geometry verification for the Jaiba control board.

Runs a DRC-style check without needing KiCad, so the board can be validated on
any machine. Two modes:

    python3 tools/verify_board.py                  # check the layout plan
    python3 tools/verify_board.py board.kicad_pcb  # check an emitted board

The second mode is the stronger one: it reads the actual .kicad_pcb, so it
verifies the file that would be sent to a fab rather than the intent behind it.

Checks performed:
  * every pad and every footprint courtyard lies inside the board outline
  * no two pads from different footprints physically overlap (shorts)
  * no two footprint courtyards overlap (parts collide)
  * no copper track leaves the board outline
  * tracks do not pass within clearance of a pad on a different net
  * tracks on different nets do not cross or run too close to each other
  * the power bus bars and pads keep clearance from the NPTH mounting holes
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kicad_sexpr as ks  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBDIR = os.path.join(REPO, "kicad-control-board", "jaiba.pretty")

CLEARANCE = 0.2          # netclass clearance, from the .kicad_pro
EDGE_CLEARANCE = 0.5
HOLE_CLEARANCE = 0.25


# --- geometry helpers ------------------------------------------------------

def rot_off(x, y, rot):
    """KiCad rotates counter-clockwise on a Y-down screen."""
    rot = int(rot) % 360
    if rot == 0:
        return (x, y)
    if rot == 90:
        return (y, -x)
    if rot == 180:
        return (-x, -y)
    if rot == 270:
        return (-y, x)
    raise ValueError(f"unsupported rotation {rot}")


def seg_point_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def seg_seg_dist(a, b):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    p1, p2 = (a[0], a[1]), (a[2], a[3])
    p3, p4 = (b[0], b[1]), (b[2], b[3])
    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(seg_point_dist(*p1, *p3, *p4), seg_point_dist(*p2, *p3, *p4),
               seg_point_dist(*p3, *p1, *p2), seg_point_dist(*p4, *p1, *p2))


def circle_rect_gap(cx, cy, r, rx, ry, hx, hy):
    nx = max(rx - hx, min(cx, rx + hx))
    ny = max(ry - hy, min(cy, ry + hy))
    return math.hypot(cx - nx, cy - ny) - r


def pad_pad_gap(a, b):
    """Gap between two pads (negative = copper overlap)."""
    def is_rect(p):
        return p["shape"] in ("rect", "roundrect", "oval") and abs(p["w"] - p["h"]) > 1e-6

    if is_rect(a) and is_rect(b):
        return max(abs(a["gx"] - b["gx"]) - (a["w"] + b["w"]) / 2,
                   abs(a["gy"] - b["gy"]) - (a["h"] + b["h"]) / 2)
    if is_rect(a) or is_rect(b):
        r, c = (b, a) if is_rect(a) else (a, b)
        return circle_rect_gap(c["gx"], c["gy"], max(c["w"], c["h"]) / 2,
                               r["gx"], r["gy"], r["w"] / 2, r["h"] / 2)
    return math.hypot(a["gx"] - b["gx"], a["gy"] - b["gy"]) - (a["w"] + b["w"]) / 2


# --- sources ---------------------------------------------------------------

def _pads_of(fp):
    out = []
    for p in ks.children(fp, "pad"):
        at = ks.child(p, "at")
        size = ks.child(p, "size")
        drill = ks.child(p, "drill")
        net = ks.child(p, "net")
        out.append(dict(num=p[1], x=float(at[1]), y=float(at[2]), shape=p[3],
                        w=float(size[1]) if size else 1.7,
                        h=float(size[2]) if size else 1.7,
                        drill=float(drill[1]) if drill else None,
                        # an np_thru_hole has no annular ring, so it is hole,
                        # not copper -- it must not take part in pad or track
                        # clearance checks
                        plated=(p[2] == "thru_hole"),
                        net_num=net[1] if net else None))
    return out


def _courtyard_local(fp):
    xs, ys = [], []
    for g in ks.children(fp, "fp_line"):
        lay = ks.child(g, "layer")
        if not lay or lay[1] != "F.CrtYd":
            continue
        for key in ("start", "end"):
            pt = ks.child(g, key)
            if pt:
                xs.append(float(pt[1]))
                ys.append(float(pt[2]))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _bbox_abs(bb, ox, oy, rot):
    if not bb:
        return None
    corners = [rot_off(bb[0], bb[1], rot), rot_off(bb[2], bb[1], rot),
               rot_off(bb[0], bb[3], rot), rot_off(bb[2], bb[3], rot)]
    return (ox + min(c[0] for c in corners), oy + min(c[1] for c in corners),
            ox + max(c[0] for c in corners), oy + max(c[1] for c in corners))


def load_library():
    lib = {}
    for fn in sorted(os.listdir(LIBDIR)):
        if fn.endswith(".kicad_mod"):
            fp = ks.parse(open(os.path.join(LIBDIR, fn), encoding="utf-8").read())
            lib[fp[1]] = fp
    return lib


def from_plan():
    import jaiba_board_layout as L
    plan = L.plan()
    lib = load_library()
    extra = {}
    for ref, pin, net in plan["links"]:
        extra.setdefault(ref, {})[pin] = net

    placed = []
    for item in plan["footprints"]:
        fp = lib[item["name"]]
        ox, oy, rot = item["x"], item["y"], item.get("rot", 0)
        nets = {**item["nets"], **extra.get(item["ref"], {})}
        pads = []
        for p in _pads_of(fp):
            dx, dy = rot_off(p["x"], p["y"], rot)
            pads.append(dict(p, gx=ox + dx, gy=oy + dy,
                             ref=item["ref"], net=nets.get(p["num"], "")))
        placed.append(dict(ref=item["ref"], name=item["name"], x=ox, y=oy,
                           rot=rot, pads=pads,
                           bb=_bbox_abs(_courtyard_local(fp), ox, oy, rot)))
    tracks = [dict(t, width=t.get("width", 0.3), layer="F.Cu")
              for t in plan["tracks"] if "x1" in t]
    return placed, tracks, plan["width"], plan["height"], len(plan["links"])


def from_board(path):
    root = ks.parse(open(path, encoding="utf-8").read())
    netname = {n[1]: str(n[2]) for n in ks.children(root, "net") if len(n) > 2}

    placed = []
    for fp in ks.children(root, "footprint"):
        at = ks.child(fp, "at")
        ox, oy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0
        ref = next((str(p[2]) for p in ks.children(fp, "property")
                    if p[1] == "Reference"), "?")
        pads = []
        for p in _pads_of(fp):
            dx, dy = rot_off(p["x"], p["y"], rot)
            pads.append(dict(p, gx=ox + dx, gy=oy + dy, ref=ref,
                             net=netname.get(p["net_num"], "") if p["net_num"] else ""))
        placed.append(dict(ref=ref, name=fp[1], x=ox, y=oy, rot=rot, pads=pads,
                           bb=_bbox_abs(_courtyard_local(fp), ox, oy, rot)))

    tracks = []
    for s in ks.children(root, "segment"):
        st, en = ks.child(s, "start"), ks.child(s, "end")
        net = ks.child(s, "net")
        lay = ks.child(s, "layer")
        tracks.append(dict(x1=float(st[1]), y1=float(st[2]),
                           x2=float(en[1]), y2=float(en[2]),
                           width=float(ks.child(s, "width")[1]),
                           layer=lay[1] if lay else "F.Cu",
                           net=netname.get(net[1], "") if net else ""))

    xs, ys = [], []
    for g in ks.children(root, "gr_line"):
        lay = ks.child(g, "layer")
        if lay and lay[1] == "Edge.Cuts":
            for k in ("start", "end"):
                pt = ks.child(g, k)
                xs.append(float(pt[1]))
                ys.append(float(pt[2]))
    return placed, tracks, max(xs), max(ys), None


# --- checks ----------------------------------------------------------------

def verify(placed, tracks, board_w, board_h, n_links=None):
    issues = []

    def bad(kind, msg):
        issues.append((kind, msg))

    all_pads = [p for fp in placed for p in fp["pads"]]

    for fp in placed:
        for p in fp["pads"]:
            r = max(p["w"], p["h"]) / 2
            if (p["gx"] - r < 0 or p["gy"] - r < 0
                    or p["gx"] + r > board_w or p["gy"] + r > board_h):
                bad("OFFBOARD-PAD", f"{p['ref']}.{p['num']} at ({p['gx']:.2f},{p['gy']:.2f})")
        if fp["bb"]:
            x1, y1, x2, y2 = fp["bb"]
            if x1 < 0 or y1 < 0 or x2 > board_w or y2 > board_h:
                bad("OFFBOARD-FP", f"{fp['ref']} courtyard ({x1:.2f},{y1:.2f})-({x2:.2f},{y2:.2f})")

    for i in range(len(all_pads)):
        for j in range(i + 1, len(all_pads)):
            a, b = all_pads[i], all_pads[j]
            if not a["plated"] or not b["plated"]:
                continue
            # Pads in the same footprint still need checking -- the 2.54 mm
            # header grid leaves the tightest gap on the whole board -- but
            # repeated pad numbers within one footprint are one node.
            if a["ref"] == b["ref"] and a["num"] == b["num"]:
                continue
            if a["net"] and a["net"] == b["net"]:
                continue
            if pad_pad_gap(a, b) < 0:
                bad("PAD-SHORT",
                    f"{a['ref']}.{a['num']}[{a['net'] or '-'}] <-> "
                    f"{b['ref']}.{b['num']}[{b['net'] or '-'}]")

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            a, b = placed[i], placed[j]
            if not a["bb"] or not b["bb"]:
                continue
            ox = min(a["bb"][2], b["bb"][2]) - max(a["bb"][0], b["bb"][0])
            oy = min(a["bb"][3], b["bb"][3]) - max(a["bb"][1], b["bb"][1])
            if ox > 0.05 and oy > 0.05:
                bad("COURTYARD", f"{a['ref']} <-> {b['ref']} overlap {ox:.2f}x{oy:.2f}mm")

    for t in tracks:
        hw = t["width"] / 2
        for x, y in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
            if (x - hw < 0 or y - hw < 0 or x + hw > board_w or y + hw > board_h):
                bad("OFFBOARD-TRACK", f"net {t['net']} endpoint ({x:.2f},{y:.2f})")

    for t in tracks:
        hw = t["width"] / 2
        for p in all_pads:
            if not p["plated"] or p["net"] == t["net"]:
                continue
            gap = seg_point_dist(p["gx"], p["gy"], t["x1"], t["y1"], t["x2"], t["y2"]) \
                - max(p["w"], p["h"]) / 2 - hw
            if gap < CLEARANCE - 1e-9:
                bad("TRACK-PAD",
                    f"net {t['net']} vs {p['ref']}.{p['num']}[{p['net'] or '-'}] gap {gap:+.3f}")

    bcu_crossings = 0
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            a, b = tracks[i], tracks[j]
            # copper on different layers never interacts
            if a["layer"] != b["layer"]:
                continue
            if a["net"] == b["net"]:
                continue
            gap = seg_seg_dist((a["x1"], a["y1"], a["x2"], a["y2"]),
                               (b["x1"], b["y1"], b["x2"], b["y2"])) \
                - a["width"] / 2 - b["width"] / 2
            if gap >= CLEARANCE - 1e-9:
                continue
            if a["layer"] == "B.Cu":
                # The B.Cu layer is the wire-jumper guide, not fabricated. The
                # jumpers are insulated wires, so they cross each other freely --
                # count these rather than calling them shorts.
                bcu_crossings += 1
                continue
            bad("TRACK-TRACK", f"net {a['net']} <-> net {b['net']} gap {gap:+.3f}")

    for fp in placed:
        if not fp["name"].startswith("MountingHole"):
            continue
        for p in fp["pads"]:
            r = (p["drill"] or 3.2) / 2
            for t in tracks:
                gap = seg_point_dist(p["gx"], p["gy"], t["x1"], t["y1"],
                                     t["x2"], t["y2"]) - r - t["width"] / 2
                if gap < HOLE_CLEARANCE - 1e-9:
                    bad("HOLE-CLEARANCE", f"{fp['ref']} hole vs net {t['net']} gap {gap:+.3f}")
            for q in all_pads:
                if q["ref"] == fp["ref"]:
                    continue
                gap = math.hypot(p["gx"] - q["gx"], p["gy"] - q["gy"]) - r - max(q["w"], q["h"]) / 2
                if gap < HOLE_CLEARANCE - 1e-9:
                    bad("HOLE-CLEARANCE", f"{fp['ref']} hole vs {q['ref']}.{q['num']} gap {gap:+.3f}")

    # The plan hardcodes a couple of footprint pin positions, because the
    # layout needs them but the library is generated separately. Check them
    # against the real footprint: getting the module's row order backwards puts
    # every connection on the wrong pin and still looks plausible.
    try:
        import jaiba_board_layout as LB
    except ImportError:
        LB = None
    if LB is not None:
        mux = next((f for f in placed if f["ref"] == "U_MUX"), None)
        if mux is not None:
            want = {"C15": (mux["x"] + LB.MUX_C15_X, mux["y"] - LB.MUX_ROW_Y),
                    "SIG": (mux["x"] + LB.MUX_SIG_X, mux["y"] + LB.MUX_ROW_Y)}
            for num, (wx, wy) in want.items():
                pad = next((p for p in mux["pads"] if p["num"] == num), None)
                if pad is None:
                    bad("PLAN-MISMATCH", f"U_MUX has no pad {num}")
                elif abs(pad["gx"] - wx) > 0.01 or abs(pad["gy"] - wy) > 0.01:
                    bad("PLAN-MISMATCH",
                        f"U_MUX.{num} sits at ({pad['gx']:.2f},{pad['gy']:.2f}) but the "
                        f"plan assumes ({wx:.2f},{wy:.2f}) -- check the row order")

    counts = {}
    for kind, _ in issues:
        counts[kind] = counts.get(kind, 0) + 1
    print(f"footprints      : {len(placed)}")
    print(f"pads            : {len(all_pads)}")
    print(f"copper tracks   : {len(tracks)}")
    if n_links is not None:
        print(f"jumper links    : {n_links}")
    print(f"board outline   : {board_w:.2f} x {board_h:.2f} mm")
    by_layer = {}
    for t in tracks:
        by_layer[t["layer"]] = by_layer.get(t["layer"], 0) + 1
    print("tracks by layer : " + ", ".join(f"{k} {v}" for k, v in sorted(by_layer.items())))
    if bcu_crossings:
        print(f"B.Cu guide crossings: {bcu_crossings} (insulated jumpers may cross; "
              "B.Cu is not fabricated)")
    print()
    if not issues:
        print("RESULT: clean -- no off-board parts, no pad collisions, "
              "no courtyard overlaps, no clearance violations.")
    else:
        print(f"RESULT: {len(issues)} issue(s)")
        for kind in sorted(counts):
            print(f"  {kind:16s} {counts[kind]}")
        print()
        for kind, msg in issues[:80]:
            print(f"  [{kind}] {msg}")
        if len(issues) > 80:
            print(f"  ... and {len(issues) - 80} more")
    return issues


def main():
    if len(sys.argv) > 1:
        placed, tracks, w, h, n = from_board(sys.argv[1])
        print(f"verifying {os.path.relpath(sys.argv[1], REPO) if sys.argv[1].startswith(REPO) else sys.argv[1]}")
        print()
    else:
        placed, tracks, w, h, n = from_plan()
        print("verifying the layout plan (jaiba_board_layout.py)")
        print()
    return 1 if verify(placed, tracks, w, h, n) else 0


if __name__ == "__main__":
    sys.exit(main())
