"""Automatic plant layout ("tidy"): turn a hand-built tangle into left-to-right columns.

A simple layered (Sugiyama-style) layout:

1. Recycle pipes are found with a depth-first search from FEED and ignored while layering, so
   the rest of the plant is a DAG.
2. Each unit goes in the column of its longest path from a source. FEED keeps column 0 and the
   outlets (PRODUCT, WASTE) the last column; both keep their positions, since they are fixed.
3. Columns are spread evenly between FEED and the outlets.
4. Inside each column, units are moved to line their in port up with the out port feeding them
   (so pipes in series are straight), sorted by that height, and pushed apart so none overlap.
   A second pass from the right places units nothing feeds next to what they feed.

Units with no pipes at all are parked in a row along the top of the canvas.
"""

import pygame

from goop_sim.sim.equipment import Equipment, Feed, Outlet
from goop_sim.sim.network import Network, Port
from goop_sim.ui.geometry import GRID, port_pos, size_of

V_GAP = 50  # between one unit's readouts and the next unit's tag in a column
TAG_ROOM = 24  # the name tag drawn above a unit
READOUT_ROOM = 48  # value boxes drawn below a unit
PARK_GAP = 30
MIN_COL_GAP = 30
GAP = READOUT_ROOM + V_GAP // 2 + TAG_ROOM  # edge to edge between units stacked in a column


def _port_dy(port: Port) -> int:
    """Port height relative to its unit's center."""
    return port_pos(port, (0, 0))[1]


def _back_edges(net: Network) -> set:
    """Pipes that close a loop, found by DFS from FEED first (so recycles point backward)."""
    succ = {eq: [] for eq in net.equipment}
    for pipe in net.pipes:
        succ[pipe.out.equipment].append(pipe)
    for edges in succ.values():
        edges.sort(key=lambda p: p.out.index)
    state, back = {}, set()

    def visit(eq):
        state[eq] = "open"
        for pipe in succ[eq]:
            nxt = pipe.into.equipment
            if state.get(nxt) == "open":
                back.add(pipe)
            elif nxt not in state:
                visit(nxt)
        state[eq] = "done"

    roots = sorted(net.equipment, key=lambda e: not isinstance(e, Feed))
    for eq in roots:
        if eq not in state:
            visit(eq)
    return back


def _layers(net: Network, units: list[Equipment], forward: list) -> dict[Equipment, int]:
    """Longest path from a source over forward pipes. Only FEED sits in column 0."""
    preds = {eq: [p.out.equipment for p in forward if p.into.equipment is eq] for eq in units}
    layer: dict[Equipment, int] = {}

    def depth(eq):
        if eq not in layer:
            layer[eq] = 0  # guard; forward pipes have no cycles
            base = 0 if isinstance(eq, Feed) else 1
            layer[eq] = max([base] + [depth(p) + 1 for p in preds[eq]])
        return layer[eq]

    for eq in units:
        depth(eq)
    inner = [layer[eq] for eq in units if not isinstance(eq, (Feed, Outlet))]
    last = max(inner, default=0) + 1
    for eq in units:
        if isinstance(eq, Outlet):
            layer[eq] = last
    return layer


def _spread(items, top: float, bottom: float) -> dict:
    """items: [(eq, desired_y, height)] in order. Push apart by V_GAP, keeping within [top, bottom]
    when they fit (if not, they run off the bottom rather than the top)."""
    ys = []
    for i, (_eq, want, h) in enumerate(items):
        y = max(want, top + h / 2)
        if i:
            y = max(y, ys[-1] + items[i - 1][2] / 2 + GAP + h / 2)
        ys.append(y)
    for i in range(len(items) - 1, -1, -1):
        h = items[i][2]
        limit = bottom - h / 2 if i == len(items) - 1 else ys[i + 1] - items[i + 1][2] / 2 - GAP - h / 2
        ys[i] = min(ys[i], limit)
    for i, (_eq, _want, h) in enumerate(items):
        floor = top + h / 2 if i == 0 else ys[i - 1] + items[i - 1][2] / 2 + GAP + h / 2
        ys[i] = max(ys[i], floor)
    return {eq: y for (eq, _w, _h), y in zip(items, ys)}


def tidy(net: Network, area: pygame.Rect, keep_out: list[pygame.Rect] = ()) -> dict[Equipment, tuple[int, int]]:
    """New centers for every movable placed unit (fixed units stay put). Does not move anything;
    the caller applies the result (so it can record an undo point first).

    `area` is the canvas region units may use; `keep_out` rects (e.g. the legend) shrink the
    usable height of any column they overlap.
    """
    piped = {p.out.equipment for p in net.pipes} | {p.into.equipment for p in net.pipes}
    loose = [eq for eq in net.equipment if eq not in piped and not eq.fixed]
    units = [eq for eq in net.equipment if eq in piped or eq.fixed]
    out: dict[Equipment, tuple[int, int]] = {}

    # Park unpiped units in a row along the top; columns under them start below them.
    parked: list[pygame.Rect] = []
    x = area.left
    feed_rects = [pygame.Rect(0, 0, *size_of(eq)) for eq in units if eq.fixed]
    for rect, eq in zip(feed_rects, [eq for eq in units if eq.fixed]):
        rect.center = eq.pos
    for eq in loose:
        w, h = size_of(eq)
        spot = pygame.Rect(x, area.top + TAG_ROOM, w, h)
        while any(spot.colliderect(r.inflate(PARK_GAP, PARK_GAP)) for r in feed_rects) and spot.right < area.right:
            spot.x += GRID
        out[eq] = (spot.centerx, spot.centery)
        x = spot.right + PARK_GAP
        parked.append(spot)

    back = _back_edges(net)
    forward = [p for p in net.pipes if p not in back and p.out.equipment in units and p.into.equipment in units]
    layer = _layers(net, units, forward)
    n_cols = max(layer.values(), default=0) + 1
    columns = [[eq for eq in units if layer[eq] == i] for i in range(n_cols)]

    # Column x: FEED's and the outlets' columns are anchored where they are.
    widths = [max((size_of(eq)[0] for eq in col), default=0) for col in columns]
    feed = next((eq for eq in units if isinstance(eq, Feed)), None)
    outlets = [eq for eq in units if isinstance(eq, Outlet)]
    left = feed.pos[0] if feed else area.left + widths[0] // 2
    right = min(eq.pos[0] for eq in outlets) if outlets else area.right - widths[-1] // 2
    xs = [left]
    if n_cols > 1:
        span = right - left - widths[0] / 2 - widths[-1] / 2 - sum(widths[1:-1])
        gap = max(MIN_COL_GAP, span / (n_cols - 1))
        cursor = left + widths[0] / 2
        for i in range(1, n_cols):
            cursor += gap + widths[i] / 2
            xs.append(right if i == n_cols - 1 else round(cursor / GRID) * GRID)
            cursor += widths[i] / 2

    ins = {eq: [p for p in forward if p.into.equipment is eq] for eq in units}
    outs = {eq: [p for p in forward if p.out.equipment is eq] for eq in units}
    pos = {eq: tuple(eq.pos) for eq in units if eq.fixed}
    mid = feed.pos[1] if feed else area.centery

    def bounds(i):
        col = pygame.Rect(xs[i] - widths[i] // 2, area.top, widths[i], area.height)
        top = max([area.top] + [r.bottom + READOUT_ROOM for r in parked if r.colliderect(col.inflate(PARK_GAP, 0))])
        bottom = min([area.bottom] + [r.top - 10 for r in keep_out if r.colliderect(col)])
        return top + TAG_ROOM, bottom - READOUT_ROOM

    def place(i, wants):
        col = [eq for eq in columns[i] if not eq.fixed]
        if not col:
            return
        order = sorted(col, key=lambda eq: (wants.get(eq, mid), columns[i].index(eq)))
        ys = _spread([(eq, wants.get(eq, mid), size_of(eq)[1]) for eq in order], *bounds(i))
        for eq in order:
            pos[eq] = (xs[i], round(ys[eq]))

    def from_preds(eq):
        ys = [pos[p.out.equipment][1] + _port_dy(p.out) - _port_dy(p.into) for p in ins[eq] if p.out.equipment in pos]
        return sum(ys) / len(ys) if ys else None

    def from_succs(eq):
        ys = [pos[p.into.equipment][1] + _port_dy(p.into) - _port_dy(p.out) for p in outs[eq] if p.into.equipment in pos]
        return sum(ys) / len(ys) if ys else None

    # Left to right: line up with what feeds each unit.
    for i in range(1, n_cols):
        wants = {}
        for eq in columns[i]:
            y = from_preds(eq)
            if y is not None:
                wants[eq] = y
        place(i, wants)
    # Right to left: units nothing feeds follow what they feed; others keep their height.
    for i in range(n_cols - 2, 0, -1):
        wants = {}
        for eq in columns[i]:
            if eq.fixed:
                continue
            y = from_preds(eq) if ins[eq] else from_succs(eq)
            wants[eq] = pos[eq][1] if y is None else y
        place(i, wants)

    for eq in units:
        if not eq.fixed:
            out[eq] = pos[eq]
    return out
