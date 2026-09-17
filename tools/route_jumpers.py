"""
Pre-route the board's wire jumpers onto B.Cu, as a guide.

This board is single-sided: only F.Cu is etched, and the ~60 connections the
generator leaves as ratsnest are insulated wires soldered on the component side.
KiCad draws those as straight lines from pad to pad, which for this many links
is an unreadable spider web.

This tool lays a plausible *path* for each of them on B.Cu. That layer is not
fabricated, so it is free to use as a map:

  * every jumper ends on a through-hole pad, and THT pads exist on all copper
    layers, so no vias are ever needed;
  * a B.Cu track cannot clash with the F.Cu copper, which is exactly right --
    the real wires are insulated and cross traces freely;
  * B.Cu coordinates map 1:1 onto the component side, so what you see on screen
    in the normal top view is where the wire physically goes.

The result is a starting point to fine-tune in KiCad, not a finished layout.
Runs are routed as orthogonal paths on a 0.635 mm lattice with A*, avoiding
pads of other nets, mounting holes, the board edge, and each other. Anything it
cannot find a path for is left unrouted and reported.

REMEMBER when plotting for etching: select F.Cu only. B.Cu now has copper in it
and must not be fabricated.

Run (after tools/emit_board.py):
    python3 tools/route_jumpers.py [board.kicad_pcb]
"""

import heapq
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kicad_sexpr as ks          # noqa: E402
import jaiba_board_layout as L    # noqa: E402
import verify_board as V          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BOARD = os.path.join(REPO, "kicad-control-board", "kicad-control-board.kicad_pcb")

PITCH = 0.635                      # routing lattice, mm (0.025 in)
# A* only tests the cells it steps on, so a straight run can pass up to half a
# cell diagonal closer to a pad than the blocked cells imply. Inflate every
# keepout by that much or the route comes out marginally too close.
CELL_SLACK = PITCH * 0.71
EDGE_KEEPOUT = 0.6                 # track edge to board edge
HOLE_KEEPOUT = 0.25                # from the hole wall (matches prefs)
TURN_COST = 1.2                    # discouraged but allowed, to reduce zigzag


def pad_gap(a, b):
    return V.pad_pad_gap(a, b)


# ---------------------------------------------------------------------------
# net connectivity -- which copper is already joined
# ---------------------------------------------------------------------------

def islands(pads, segs, net):
    """Group a net's copper into electrically joined islands."""
    items = [p for p in pads if p["net"] == net] + [s for s in segs if s["net"] == net]
    n = len(items)
    if n == 0:
        return []
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            joined = False
            if a["kind"] == "pad" and b["kind"] == "pad":
                # same footprint + same pad number == one node, no copper needed
                if a.get("ref") == b.get("ref") and a.get("num") == b.get("num"):
                    joined = True
                else:
                    joined = math.hypot(a["gx"] - b["gx"], a["gy"] - b["gy"]) <= a["r"] + b["r"] + 0.01
            elif a["kind"] == "pad":
                joined = V.seg_point_dist(a["gx"], a["gy"], b["x1"], b["y1"],
                                          b["x2"], b["y2"]) <= a["r"] + 0.01
            elif b["kind"] == "pad":
                joined = V.seg_point_dist(b["gx"], b["gy"], a["x1"], a["y1"],
                                          a["x2"], a["y2"]) <= b["r"] + 0.01
            else:
                for p in ((a["x1"], a["y1"]), (a["x2"], a["y2"])):
                    for q in ((b["x1"], b["y1"]), (b["x2"], b["y2"])):
                        if math.hypot(p[0] - q[0], p[1] - q[1]) < 0.01:
                            joined = True
            if joined:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    # a group is represented by one of its pads, so routes start on copper
    out = []
    for grp in groups.values():
        # Prefer a wire landing pad as the representative. It and the Teensy pin
        # it feeds are one island (a short F.Cu stub joins them), and the wire is
        # meant to land on the pad -- so that is where the guide should aim,
        # rather than adding a second run to the pin itself.
        p = next((g for g in grp if g["kind"] == "pad"
                  and str(g.get("ref", "")).startswith("W_")), None) \
            or next((g for g in grp if g["kind"] == "pad"), None)
        out.append(p if p else grp[0])
    return out


# ---------------------------------------------------------------------------
# grid + A*
# ---------------------------------------------------------------------------

class Grid:
    def __init__(self, w, h):
        self.nx = int(w / PITCH) + 1
        self.ny = int(h / PITCH) + 1
        self.blocked = bytearray(self.nx * self.ny)

    def idx(self, ix, iy):
        return iy * self.nx + ix

    def to_cell(self, x, y):
        return int(round(x / PITCH)), int(round(y / PITCH))

    def to_mm(self, ix, iy):
        return ix * PITCH, iy * PITCH

    def block_circle(self, cx, cy, rad, value=1):
        x0, y0 = self.to_cell(cx - rad, cy - rad)
        x1, y1 = self.to_cell(cx + rad, cy + rad)
        for iy in range(max(0, y0), min(self.ny - 1, y1) + 1):
            for ix in range(max(0, x0), min(self.nx - 1, x1) + 1):
                mx, my = self.to_mm(ix, iy)
                if math.hypot(mx - cx, my - cy) <= rad:
                    self.blocked[self.idx(ix, iy)] = value


def astar(grid, start, goal, box):
    """Orthogonal A* from start to goal, restricted to a cell bounding box."""
    sx, sy = start
    gx, gy = goal
    x0, y0, x1, y1 = box
    if not (x0 <= sx <= x1 and y0 <= sy <= y1 and x0 <= gx <= x1 and y0 <= gy <= y1):
        return None

    best = {}
    start_state = (sx, sy, 0)
    pq = [(abs(gx - sx) + abs(gy - sy), 0.0, start_state, None)]
    came = {}
    best[start_state] = 0.0
    found = None

    while pq:
        _, g, state, parent = heapq.heappop(pq)
        if state in came:
            continue
        came[state] = parent
        x, y, d = state
        if x == gx and y == gy:
            found = state
            break
        for nd, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
            nx_, ny_ = x + dx, y + dy
            if not (x0 <= nx_ <= x1 and y0 <= ny_ <= y1):
                continue
            if grid.blocked[grid.idx(nx_, ny_)]:
                continue
            cost = 1.0 + (TURN_COST if d and nd != d else 0.0)
            ng = g + cost
            key = (nx_, ny_, nd)
            if ng < best.get(key, 1e18):
                best[key] = ng
                h = abs(gx - nx_) + abs(gy - ny_)
                heapq.heappush(pq, (ng + h, ng, key, state))

    if found is None:
        return None
    path = []
    s = found
    while s is not None:
        path.append(s[:2])
        s = came[s]
    return path[::-1]


def simplify(path):
    """Collapse a cell path into corner points."""
    if len(path) < 2:
        return path
    pts = [path[0]]
    for i in range(1, len(path) - 1):
        ax, ay = path[i - 1]
        bx, by = path[i]
        cx, cy = path[i + 1]
        if (bx - ax, by - ay) != (cx - bx, cy - by):
            pts.append(path[i])
    pts.append(path[-1])
    return pts


# ---------------------------------------------------------------------------

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BOARD
    board = ks.parse(open(path, encoding="utf-8").read())
    netname = {n[1]: str(n[2]) for n in ks.children(board, "net") if len(n) > 2}

    # drop any routes from a previous run so this is idempotent
    removed = 0
    keep = []
    for item in board:
        if isinstance(item, list) and item and item[0] == "segment":
            lay = ks.child(item, "layer")
            if lay and lay[1] == "B.Cu":
                removed += 1
                continue
        keep.append(item)
    board[:] = keep

    placed, tracks, W, H, _ = V.from_board(path) if removed == 0 else (None, None, None, None, None)
    if placed is None:
        # re-read after stripping so counts match what we route
        tmp = path + ".stripped"
        ks.dump_file(board, tmp)
        placed, tracks, W, H, _ = V.from_board(tmp)
        os.remove(tmp)

    pads = []
    for f in placed:
        for p in f["pads"]:
            if not p["plated"]:
                continue
            pads.append(dict(p, kind="pad", gx=p["gx"], gy=p["gy"],
                             r=max(p["w"], p["h"]) / 2, ref=p["ref"], num=p["num"]))
    segs = [dict(t, kind="seg") for t in tracks]
    holes = [p for f in placed if f["name"].startswith("MountingHole")
             for p in f["pads"]]

    grid = Grid(W, H)
    # board edge
    for iy in range(grid.ny):
        for ix in range(grid.nx):
            mx, my = grid.to_mm(ix, iy)
            if (mx < EDGE_KEEPOUT or my < EDGE_KEEPOUT
                    or mx > W - EDGE_KEEPOUT or my > H - EDGE_KEEPOUT):
                grid.blocked[grid.idx(ix, iy)] = 1
    for h in holes:
        grid.block_circle(h["gx"], h["gy"],
                         (h["drill"] or 3.2) / 2 + L.TRACK_W / 2 + HOLE_KEEPOUT
                         + 0.6 + CELL_SLACK)

    # Block every pad for every net; a net's own pads are unblocked as it routes.
    pad_cells = {}
    for p in pads:
        rad = p["r"] + L.TRACK_W / 2 + 0.2 + CELL_SLACK
        cells = []
        x0, y0 = grid.to_cell(p["gx"] - rad, p["gy"] - rad)
        x1, y1 = grid.to_cell(p["gx"] + rad, p["gy"] + rad)
        for iy in range(max(0, y0), min(grid.ny - 1, y1) + 1):
            for ix in range(max(0, x0), min(grid.nx - 1, x1) + 1):
                mx, my = grid.to_mm(ix, iy)
                if math.hypot(mx - p["gx"], my - p["gy"]) <= rad:
                    cells.append((ix, iy))
        pad_cells[id(p)] = (cells, p["net"])
        for c in cells:
            grid.blocked[grid.idx(*c)] = 1

    nets = sorted({p["net"] for p in pads if p["net"]} - {"GND", "3V3"})
    routed = 0
    failed = []

    for net in nets:
        isl = islands(pads, segs, net)
        if len(isl) < 2:
            continue
        # unblock this net's own pads
        touched = []
        mine = [p for p in pads if p["net"] == net]
        for p in mine:
            for c in pad_cells[id(p)][0]:
                if not grid.blocked[grid.idx(*c)]:
                    continue
                mx, my = grid.to_mm(*c)
                # A cell can sit in this net's pad AND in a neighbouring pad's
                # keepout. Re-opening it there would route straight through a
                # foreign pad, so only open cells that are genuinely ours.
                if any(math.hypot(mx - q["gx"], my - q["gy"])
                       <= q["r"] + L.TRACK_W / 2 + 0.2 + CELL_SLACK
                       for q in pads if q["net"] != net):
                    continue
                grid.blocked[grid.idx(*c)] = 0
                touched.append(c)

        base = isl[0]
        base_cell = grid.to_cell(base["gx"], base["gy"])
        for other in isl[1:]:
            goal_cell = grid.to_cell(other["gx"], other["gy"])
            # No bounding box: a B.Cu track cannot pass between two pads on the
            # 2.54 mm grid, so every Teensy pad row is a wall and routes have to
            # go around whole modules. Clipping the search to the endpoints'
            # neighbourhood made most of them unreachable.
            p = astar(grid, base_cell, goal_cell, (0, 0, grid.nx - 1, grid.ny - 1))
            if p is None:
                failed.append((net, f"{base['ref']}.{base['num']}",
                               f"{other['ref']}.{other['num']}"))
                continue
            pts = simplify(p)
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                m1x, m1y = grid.to_mm(ax, ay)
                m2x, m2y = grid.to_mm(bx, by)
                board.append(["segment",
                              ["start", f"{m1x:.3f}", f"{m1y:.3f}"],
                              ["end", f"{m2x:.3f}", f"{m2y:.3f}"],
                              ["width", f"{L.TRACK_W}"],
                              ["layer", "B.Cu"],
                              ["net", next(n[1] for n in ks.children(board, "net")
                                           if len(n) > 2 and str(n[2]) == net)],
                              ["uuid", ks.Quoted(str(uuid.uuid4()))]])
            # Deliberately NOT blocked for later routes: insulated wires may
            # cross, so crossings in this guide are meaningful, not errors.
            routed += 1

        for c in touched:
            grid.blocked[grid.idx(*c)] = 1

    ks.dump_file(board, path)
    print(f"stripped {removed} previous B.Cu route(s)")
    print(f"routed  {routed} link(s) on B.Cu")
    if failed:
        print(f"left for manual routing: {len(failed)}")
        for net, a, b in failed[:15]:
            print(f"   {net}: {a} -> {b}")
        if len(failed) > 15:
            print(f"   ... and {len(failed) - 15} more")
    print()
    print("Now verify with tools/verify_board.py, then open in KiCad and tidy.")
    print("WHEN PLOTTING FOR ETCHING: F.Cu only. B.Cu is a guide and must not be made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
