import math

import pygame

from goop_sim.sim.equipment import Equipment, Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.network import Pipe, Port

PORT_RADIUS = 6
GRID = 20

_SIZES = {
    Tank: (80, 110),
    Pump: (40, 40),
    Reactor: (80, 96),
    Separator: (46, 150),
    Splitter: (44, 30),
    Mixer: (34, 34),
    Feed: (110, 60),
    Outlet: (110, 60),
}


def size_of(eq: Equipment) -> tuple[int, int]:
    return next(size for cls, size in _SIZES.items() if isinstance(eq, cls))


def rect_of(eq: Equipment, pos=None) -> pygame.Rect:
    w, h = size_of(eq)
    cx, cy = pos or eq.pos
    return pygame.Rect(cx - w // 2, cy - h // 2, w, h)


def fit_rect(eq: Equipment, box: pygame.Rect) -> pygame.Rect:
    """The equipment's shape scaled down to fit `box`, centered (for icons)."""
    w, h = size_of(eq)
    scale = min(box.width / w, box.height / h)
    rect = pygame.Rect(0, 0, max(4, round(w * scale)), max(4, round(h * scale)))
    rect.center = box.center
    return rect


def port_pos(port: Port, pos=None) -> tuple[int, int]:
    rect = rect_of(port.equipment, pos)
    count = port.equipment.n_in if port.kind == "in" else port.equipment.n_out
    x = rect.left if port.kind == "in" else rect.right
    y = rect.top + round(rect.height * (port.index + 1) / (count + 1))
    return x, y


def all_ports(eq: Equipment):
    for i in range(eq.n_in):
        yield Port(eq, "in", i)
    for i in range(eq.n_out):
        yield Port(eq, "out", i)


def _simplify(points):
    """Drop repeated points and middle points of straight runs."""
    out = []
    for p in points:
        if out and p == out[-1]:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if (ax == bx == p[0]) or (ay == by == p[1]):
                out[-1] = p
                continue
        out.append(p)
    return out


LANE = 12  # spacing between parallel pipes that would otherwise overlap (pipe wall is 10 px)


def pipe_points(pipe: Pipe, lane: int = 0) -> list[tuple[int, int]]:
    """Orthogonal route. Forward pipes are a Z with the vertical leg near the middle; backward
    (recycle) pipes step out, run below both units, and step back in. `lane` shifts the free
    legs so parallel pipes do not draw on top of each other."""
    x1, y1 = port_pos(pipe.out)
    x2, y2 = port_pos(pipe.into)
    if x2 > x1 + 4:
        offset = (lane + 1) // 2 * LANE * (1 if lane % 2 else -1)  # 0, +12, -12, +24, -24, ...
        mx = min(x2 - 4, max(x1 + 4, (x1 + x2) // 2 + offset))
        return _simplify([(x1, y1), (mx, y1), (mx, y2), (x2, y2)])
    k = lane * LANE
    low = max(rect_of(pipe.out.equipment).bottom, rect_of(pipe.into.equipment).bottom) + GRID + k
    xa, xb = x1 + GRID + k, x2 - GRID - k
    return _simplify([(x1, y1), (xa, y1), (xa, low), (xb, low), (xb, y2), (x2, y2)])


def _segments(points):
    """Split into (vertical, horizontal) lists of (fixed coord, lo, hi)."""
    vert, horiz = [], []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        if ax == bx and ay != by:
            vert.append((ax, min(ay, by), max(ay, by)))
        elif ay == by and ax != bx:
            horiz.append((ay, min(ax, bx), max(ax, bx)))
    return vert, horiz


def _overlap(segs, taken) -> bool:
    """Any segment collinear-ish with a taken one (within a pipe width) and sharing length."""
    return any(abs(c - tc) < LANE - 1 and min(hi, thi) - max(lo, tlo) > 2 for c, lo, hi in segs for tc, tlo, thi in taken)


def lay_out_pipes(pipes: list[Pipe], max_lanes: int = 8) -> dict[Pipe, list[tuple[int, int]]]:
    """Route every pipe, picking the first lane whose free legs don't overlap pipes routed before it."""
    taken_v, taken_h = [], []
    out = {}
    for pipe in pipes:
        choice = None
        for lane in range(max_lanes):
            pts = pipe_points(pipe, lane)
            vert, horiz = _segments(pts)
            # Port stubs are fixed, so only judge the legs a lane can actually move.
            free_v = vert if len(pts) > 2 else []
            free_h = horiz[1:-1] if len(horiz) > 2 else []
            if not _overlap(free_v, taken_v) and not _overlap(free_h, taken_h):
                choice = pts
                break
        choice = choice or pipe_points(pipe)
        vert, horiz = _segments(choice)
        taken_v.extend(vert)
        taken_h.extend(horiz)
        out[pipe] = choice
    return out


HOP_RADIUS = 11
_HOP_STEPS = 10


def route_pipes(pipes: list[Pipe]) -> dict[Pipe, tuple[list, list]]:
    """Drawable path for every pipe, with line jumps where pipes cross.

    Convention: a horizontal run hops over any other pipe's vertical run that crosses it.
    Returns {pipe: (path, hops)}; `path` includes the arc points, `hops` lists each arc so it
    can be redrawn on top of the pipe it jumps.
    """
    base = lay_out_pipes(pipes)
    verticals = []
    for pipe, pts in base.items():
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if x1 == x2 and y1 != y2:
                verticals.append((pipe, x1, min(y1, y2), max(y1, y2)))
    routes = {}
    for pipe, pts in base.items():
        path, hops = [pts[0]], []
        for a, b in zip(pts, pts[1:]):
            if a[1] == b[1] and a[0] != b[0]:
                y = a[1]
                lo, hi = sorted((a[0], b[0]))
                d = 1 if b[0] > a[0] else -1
                xs = sorted(
                    {x for other, x, y0, y1 in verticals if other is not pipe and lo + HOP_RADIUS < x < hi - HOP_RADIUS and y0 < y < y1},
                    reverse=d < 0,
                )
                last = None
                for x in xs:
                    if last is not None and abs(x - last) < 2 * HOP_RADIUS + 2:
                        continue  # too close to the previous jump; that arc already clears it
                    arc = [
                        (x - d * HOP_RADIUS * math.cos(t), y - HOP_RADIUS * math.sin(t))
                        for t in (math.pi * i / _HOP_STEPS for i in range(_HOP_STEPS + 1))
                    ]
                    path.extend(arc)
                    hops.append(arc)
                    last = x
            path.append(b)
        routes[pipe] = (path, hops)
    return routes


def dist_to_segment(p, a, b) -> float:
    p, a, b = pygame.Vector2(p), pygame.Vector2(a), pygame.Vector2(b)
    ab = b - a
    if ab.length_squared() == 0:
        return p.distance_to(a)
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared()))
    return p.distance_to(a + ab * t)


def snap(pos) -> tuple[int, int]:
    return round(pos[0] / GRID) * GRID, round(pos[1] / GRID) * GRID
