import pygame

from goop_sim.sim.equipment import Equipment, Pump, Sink, Source, Tank
from goop_sim.sim.network import Pipe, Port

PORT_RADIUS = 7
GRID = 20

_SIZES = {Tank: (100, 120), Pump: (44, 44), Source: (90, 50), Sink: (90, 50)}


def rect_of(eq: Equipment, pos=None) -> pygame.Rect:
    w, h = next(size for cls, size in _SIZES.items() if isinstance(eq, cls))
    cx, cy = pos or eq.pos
    return pygame.Rect(cx - w // 2, cy - h // 2, w, h)


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


def pipe_points(pipe: Pipe) -> list[tuple[int, int]]:
    x1, y1 = port_pos(pipe.out)
    x2, y2 = port_pos(pipe.into)
    mx = (x1 + x2) // 2
    return [(x1, y1), (mx, y1), (mx, y2), (x2, y2)]


def dist_to_segment(p, a, b) -> float:
    p, a, b = pygame.Vector2(p), pygame.Vector2(a), pygame.Vector2(b)
    ab = b - a
    if ab.length_squared() == 0:
        return p.distance_to(a)
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared()))
    return p.distance_to(a + ab * t)


def snap(pos) -> tuple[int, int]:
    return round(pos[0] / GRID) * GRID, round(pos[1] / GRID) * GRID
