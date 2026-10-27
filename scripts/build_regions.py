#!/usr/bin/env python3
"""India state/UT polygons + ghat road list for routemates-backend pkg/region (P3-GAM, backend#7).

Input: GeoJSON sequences exported by osmium from the Geofabrik India extract (see build-regions.sh).
Output: <out>/states/IN-XX.poly (osmosis .poly, simplified) and <out>/ghats.json.
Data © OpenStreetMap contributors, ODbL. Stdlib only, so CI needs nothing but osmium.
"""
import json
import math
import os
import re
import sys
from collections import defaultdict

STATE_TOL = 0.002  # degrees (~200 m): river borders are wiggly; this keeps all 36 polys ~1 MB embedded
GHAT_MIN_M = 1500  # shorter named stretches are town streets
GHAT_MIN_TURN = 85  # degrees of heading change per km at 200 m spacing: hill roads 100-380, plains "Ghat Road"
#                     to a river ghat 1-75 (measured on the 2026-10 extract). No elevation data is used.
PASS_RADIUS_M = 2000  # a mountain pass near a road becomes the road stretch within this distance
PASS_SNAP_M = 300  # passes further than this from a motorable road are trekking passes
GENERIC = re.compile(r"(mountain )?pass|ghat|ghati|la", re.I)  # unnamed features carry a type word as name
GHAT_STEP_M = 200  # resample spacing of ghat pts
ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
         "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "track", "road"}
GHAT_RE = re.compile(r"\bghat\b|घाट", re.I)


def read_seq(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("\x1e")
            if line:
                yield json.loads(line)


def dp(pts, tol):
    """Douglas-Peucker, iterative; keeps first/last point."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / n if n else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def states(path):
    out = {}
    for f in read_seq(path):
        p = f["properties"]
        code = p.get("ISO3166-2", "")
        if p.get("admin_level") != "4" or not re.fullmatch(r"IN-[A-Z]{2}", code):
            continue
        code = {"IN-TS": "IN-TG"}.get(code, code)  # OSM still has Telangana's pre-2023 ISO code
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            for ring in poly:
                r = dp(ring, STATE_TOL)
                if len(r) >= 4:
                    rings.append(r)
        out[code] = (p.get("name:en") or p.get("name", code), rings)
    return out


def write_poly(path, name, rings):
    with open(path, "w") as f:
        f.write(f"{name}\n")
        for i, r in enumerate(rings, 1):
            f.write(f"{i}\n")
            for x, y in r:
                f.write(f"{x:.4f} {y:.4f}\n")
            f.write("END\n")
        f.write("END\n")


def in_rings(rings, x, y):
    inside = False
    for r in rings:
        j = len(r) - 1
        for i in range(len(r)):
            if (r[i][1] > y) != (r[j][1] > y) and x < (r[j][0] - r[i][0]) * (y - r[i][1]) / (r[j][1] - r[i][1]) + r[i][0]:
                inside = not inside
            j = i
    return inside


def metres(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * k, a[1] - b[1]) * 111_320


def resample(line, step):
    out, carry = [line[0]], 0.0
    for a, b in zip(line, line[1:]):
        d = metres(a, b)
        t = step - carry
        while t <= d:
            out.append((a[0] + (b[0] - a[0]) * t / d, a[1] + (b[1] - a[1]) * t / d))
            t += step
        carry = (carry + d) % step
    if line[-1] != out[-1]:
        out.append(line[-1])
    return out


def ghats(path, st):
    ways = []
    for f in read_seq(path):
        p = f["properties"]
        name = (p.get("name:en") or p.get("name", "")).strip()
        if not name or name[0].islower() or GENERIC.fullmatch(name):
            continue  # "ghat", "its a ghat section ..." are notes, not names
        if p.get("highway") not in ROADS or f["geometry"]["type"] != "LineString":
            continue
        if not (GHAT_RE.search(name) or GHAT_RE.search(p.get("name", ""))):
            continue
        ways.append((f["id"], name, [tuple(c) for c in f["geometry"]["coordinates"]]))
    # union ways of one name that share a node: one physical ghat road
    parent = list(range(len(ways)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, (_, name, line) in enumerate(ways):
        for c in line:
            j = seen.setdefault((name.lower(), c), i)
            if j != i:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(ways)):
        groups[find(i)].append(ways[i])
    out = []
    for g in groups.values():
        lines = [l for _, _, l in g]
        length = sum(metres(a, b) for l in lines for a, b in zip(l, l[1:]))
        if length < GHAT_MIN_M or not winding(lines, length):
            continue
        ids = sorted(int(i[1:]) for i, _, _ in g)
        out.append(entry(f"osm-w{ids[0]}", g[0][1], lines, length, st))
    return out


def turning(line):
    p = resample(line, GHAT_STEP_M)
    t = 0.0
    for a, b, c in zip(p, p[1:], p[2:]):
        h1 = math.atan2(b[1] - a[1], (b[0] - a[0]) * math.cos(math.radians(a[1])))
        h2 = math.atan2(c[1] - b[1], (c[0] - b[0]) * math.cos(math.radians(a[1])))
        d = abs(math.degrees(h2 - h1)) % 360
        d = min(d, 360 - d)
        t += d if d < 150 else 0  # a reversal is a resampling artefact at a way's end, not a bend
    return t


def winding(lines, length):
    return sum(turning(l) for l in lines) / (length / 1000) >= GHAT_MIN_TURN


def entry(gid, name, lines, length, st):
    pts = [p for l in lines for p in resample(l, GHAT_STEP_M)]
    mid = pts[len(pts) // 2]
    state = next((c for c, (_, r) in st.items() if in_rings(r, *mid)), "")
    return {"id": gid, "name": name, "state": state, "len_m": round(length),
            "pts": [[round(y, 5), round(x, 5)] for x, y in pts]}


def passes(pass_path, roads_path, st, named):
    """Named mountain passes (natural=mountain_pass / mountain_pass=yes) within PASS_SNAP_M of a motorable
    road: the ghat is that road's stretch within PASS_RADIUS_M of the pass."""
    nodes = []
    for f in read_seq(pass_path):
        p = f["properties"]
        name = (p.get("name:en") or p.get("name", "")).strip()
        if name and not GENERIC.fullmatch(name):
            nodes.append((f["id"], name, tuple(f["geometry"]["coordinates"])))
    taken = [q for x in named for q in x["pts"]]
    nodes = [n for n in nodes if not any(metres(n[2], (q[1], q[0])) < 1000 for q in taken)]
    grid = defaultdict(list)  # 0.02° cells (~2 km) -> pass index
    for i, (_, _, c) in enumerate(nodes):
        grid[(int(c[0] // 0.02), int(c[1] // 0.02))].append(i)
    lines = defaultdict(list)
    for f in read_seq(roads_path):
        w = f["geometry"]["coordinates"]
        hit = set()
        for x, y in w:
            cx, cy = int(x // 0.02), int(y // 0.02)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    hit.update(grid.get((cx + dx, cy + dy), ()))
        for i in hit:
            c = nodes[i][2]
            if min(metres(tuple(q), c) for q in w) <= PASS_SNAP_M:
                seg = [tuple(q) for q in w if metres(tuple(q), c) <= PASS_RADIUS_M]
                if len(seg) > 1:
                    lines[i].append(seg)
    out = []
    for i, ls in lines.items():
        length = sum(metres(a, b) for l in ls for a, b in zip(l, l[1:]))
        if length >= GHAT_MIN_M and winding(ls, length):
            out.append(entry(f"osm-{nodes[i][0]}", nodes[i][1], ls, length, st))
    return out


def main():
    if len(sys.argv) != 6:
        sys.exit("usage: build_regions.py states ghatroads passes roads outdir (all .geojsonseq)")
    st = states(sys.argv[1])
    os.makedirs(f"{sys.argv[5]}/states", exist_ok=True)
    for code, (name, rings) in sorted(st.items()):
        write_poly(f"{sys.argv[5]}/states/{code}.poly", name, rings)
    gh = ghats(sys.argv[2], st)
    gh = sorted(gh + passes(sys.argv[3], sys.argv[4], st, gh), key=lambda x: x["id"])
    gh = [g for g in gh if g["state"]]  # passes beyond the Indian state polygons (e.g. Aksai Chin)
    with open(f"{sys.argv[5]}/ghats.json", "w", encoding="utf-8") as f:
        json.dump(gh, f, ensure_ascii=False, separators=(",", ":"))
    print(f"states={len(st)} ghats={len(gh)}", file=sys.stderr)
    if len(st) != 36 or not gh:  # 28 states + 8 UTs
        sys.exit(f"unexpected output: {sorted(st)}")


if __name__ == "__main__":
    main()
