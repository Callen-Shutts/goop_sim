from dataclasses import dataclass, field
from typing import NamedTuple

from goop_sim.sim.equipment import Equipment, Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.stream import Stream


class Port(NamedTuple):
    equipment: Equipment
    kind: str  # "in" or "out"
    index: int = 0


GAL_PER_PX = 0.18  # pipe holdup per pixel of run between the two units
MIN_PIPE_GAL = 4.0
MAX_SLUGS = 48


@dataclass(eq=False)
class Pipe:
    """Plug flow: liquid enters at the out-port end as a slug and only leaves the far end once
    the pipe is full, pushed out by what enters behind it. Between units without positions
    (tests) a pipe holds nothing and passes liquid straight through."""

    out: Port
    into: Port
    carried: Stream = field(default_factory=Stream)  # what entered during the last step
    slugs: list[Stream] = field(default_factory=list)  # oldest (far end) first

    @property
    def capacity_gal(self) -> float:
        a, b = self.out.equipment.pos, self.into.equipment.pos
        if a is None or b is None:
            return 0.0
        return max(MIN_PIPE_GAL, (abs(a[0] - b[0]) + abs(a[1] - b[1])) * GAL_PER_PX)

    @property
    def held_gal(self) -> float:
        return sum(s.total() for s in self.slugs)

    @property
    def fill(self) -> float:
        cap = self.capacity_gal
        return min(1.0, self.held_gal / cap) if cap else 0.0

    def push(self, stream: Stream) -> Stream:
        """Put `stream` in at the near end; return what comes out of the far end."""
        self.carried.add(stream)
        cap = self.capacity_gal
        if cap <= 0:
            return stream
        self.slugs.append(stream.copy())
        out = Stream()
        excess = self.held_gal - cap
        while excess > 1e-9 and self.slugs:
            front = self.slugs[0]
            if front.total() <= excess + 1e-9:
                excess -= front.total()
                out.add(self.slugs.pop(0))
            else:
                out.add(front.take(excess))
                excess = 0
        if len(self.slugs) > MAX_SLUGS:  # keep it bounded: merge the two oldest
            first = self.slugs.pop(0)
            self.slugs[0].add(first)
        return out

    def empty(self) -> None:
        self.carried = Stream()
        self.slugs = []


class Network:
    """Placed equipment plus the pipes between it.

    Flow model: each step, every running pump draws its setpoint from the feed or tank on its inlet.
    That liquid passes instantly through reactors, separators, splitters, mixers and other running
    pumps until it lands in a tank or an outlet; each of those units processes the combined flow
    from all pumps once per step. Liquid with nowhere to go (open port, full tank, stopped pump,
    loop with no tank) is spilled.
    """

    def __init__(self):
        self.equipment: list[Equipment] = []
        self.pipes: list[Pipe] = []
        self.spilled_gal = 0.0
        # Where liquid was spilled, keyed by an open out `Port` or by the unit (full tank,
        # stopped pump, unit on a loop with no tank): what spilled during the last step, and
        # gallons since the last reset.
        self.spills: dict = {}
        self.spill_totals: dict = {}
        self.moved_gal = 0.0  # drawn by pumps during the last step
        self.last_dt = 0.0
        self._inbox: dict[Equipment, Stream] = {}  # per step: what reached each inline unit
        self._looped: set[Equipment] = set()  # per step: inline units on a loop with no tank

    def clear_spills(self) -> None:
        self.spilled_gal = 0.0
        self.spills = {}
        self.spill_totals = {}

    def spilled_by(self, eq: Equipment) -> float:
        """Gallons spilled at this unit or its open ports since the last reset."""
        return sum(gal for key, gal in self.spill_totals.items() if key is eq or (isinstance(key, Port) and key.equipment is eq))

    def spill_reason(self, key) -> str:
        if isinstance(key, Port):
            return "OUTLET NOT PIPED"
        if isinstance(key, Tank):
            return "TANK FULL"
        if isinstance(key, Pump) and not key.running:
            return "PUMP STOPPED"
        return "LOOP NEEDS A TANK"

    def _spill(self, key, stream: Stream) -> None:
        gal = stream.total()
        if gal <= 1e-9:
            return
        self.spilled_gal += gal
        self.spills.setdefault(key, Stream()).add(stream)
        self.spill_totals[key] = self.spill_totals.get(key, 0.0) + gal

    def add(self, eq: Equipment) -> None:
        self.equipment.append(eq)

    def remove(self, eq: Equipment) -> None:
        self.equipment.remove(eq)
        self.pipes = [p for p in self.pipes if eq not in (p.out.equipment, p.into.equipment)]

    def pipe_at(self, port: Port) -> Pipe | None:
        for pipe in self.pipes:
            if port in (pipe.out, pipe.into):
                return pipe
        return None

    def connect(self, a: Port, b: Port) -> Pipe | None:
        """Pipe an out port to an in port (given in either order). Returns None if not allowed."""
        if a.kind == "in" and b.kind == "out":
            a, b = b, a
        if a.kind != "out" or b.kind != "in" or a.equipment is b.equipment:
            return None
        if a.equipment not in self.equipment or b.equipment not in self.equipment:
            return None
        if self.pipe_at(a) or self.pipe_at(b):
            return None
        pipe = Pipe(a, b)
        self.pipes.append(pipe)
        return pipe

    def disconnect(self, pipe: Pipe) -> None:
        self.pipes.remove(pipe)

    # -- flow -------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance `dt` simulated seconds.

        Pumps on a feed or tank draw first. Then every inline unit (pump, reactor, column,
        splitter, mixer) is processed once, upstream before downstream, on everything that
        reached it this step from all pumps combined, so streams really mix and reactors and
        columns see their true total load. Units on a loop with no tank in it spill what reaches them.
        """
        self.moved_gal = 0.0
        self.last_dt = dt
        self.spills = {}
        for pipe in self.pipes:
            pipe.carried = Stream()
        for eq in self.equipment:
            if isinstance(eq, Outlet):
                eq.inflow = Stream()
            elif isinstance(eq, (Reactor, Separator)):
                eq.load_gpm = 0.0
        pumps = [eq for eq in self.equipment if isinstance(eq, Pump)]
        for pump in pumps:
            pump.flow_gpm = 0.0
        if dt <= 0:
            return
        order, self._looped = self._inline_order()
        self._inbox: dict[Equipment, Stream] = {}
        for pump in pumps:
            if not pump.running:
                continue
            up = self.pipe_at(Port(pump, "in"))
            if not up or not self.pipe_at(Port(pump, "out")):
                continue
            source = up.out.equipment
            if isinstance(source, Feed):
                holdup = source.stock
            elif isinstance(source, Tank):
                holdup = source.content
            else:
                continue  # fed by inline equipment: it only boosts what is pushed into it
            drawn = holdup.take(pump.setpoint_gpm * dt / 60)
            if drawn.total() <= 0:
                continue
            self.moved_gal += drawn.total()
            self._deliver(pump, up.push(drawn))
        for eq in order:
            stream = self._inbox.pop(eq, Stream())
            if stream.total() > 1e-9 or isinstance(eq, Reactor):
                self._process(eq, stream)

    def _inline_order(self) -> tuple[list[Equipment], set[Equipment]]:
        """Inline units upstream-first, and the set of those sitting on a loop with no tank."""
        inline = [eq for eq in self.equipment if isinstance(eq, _INLINE)]
        succ = {eq: [] for eq in inline}
        for pipe in self.pipes:
            a, b = pipe.out.equipment, pipe.into.equipment
            if a in succ and b in succ:
                succ[a].append(b)

        def reaches(start, goal):
            seen, todo = set(), list(succ[start])
            while todo:
                eq = todo.pop()
                if eq is goal:
                    return True
                if eq not in seen:
                    seen.add(eq)
                    todo.extend(succ[eq])
            return False

        looped = {eq for eq in inline if reaches(eq, eq)}
        indeg = {eq: 0 for eq in inline if eq not in looped}
        for eq in indeg:
            for nxt in succ[eq]:
                if nxt in indeg:
                    indeg[nxt] += 1
        ready = [eq for eq, n in indeg.items() if n == 0]
        order = []
        while ready:
            eq = ready.pop(0)
            order.append(eq)
            for nxt in succ[eq]:
                if nxt in indeg:
                    indeg[nxt] -= 1
                    if indeg[nxt] == 0:
                        ready.append(nxt)
        return order, looped

    def _forward(self, eq: Equipment, index: int, stream: Stream) -> None:
        if stream.total() <= 1e-9:
            return
        pipe = self.pipe_at(Port(eq, "out", index))
        if pipe is None:
            self._spill(Port(eq, "out", index), stream)
            return
        arrived = pipe.push(stream)
        if arrived.total() > 1e-9:
            self._deliver(pipe.into.equipment, arrived)

    def _deliver(self, eq: Equipment, stream: Stream) -> None:
        """Tanks and outlets take liquid now; inline units collect it until their turn."""
        if isinstance(eq, Tank):
            total = stream.total()
            keep = min(1.0, eq.free_gal / total) if total > 0 else 0.0
            eq.content.add(stream.scaled(keep))
            if keep < 1:
                self._spill(eq, stream.scaled(1 - keep))
        elif isinstance(eq, Outlet):
            eq.take_in(stream)
        elif isinstance(eq, _INLINE) and eq not in self._looped:
            self._inbox.setdefault(eq, Stream()).add(stream)
        else:
            self._spill(eq, stream)

    def _process(self, eq: Equipment, stream: Stream) -> None:
        """Run one inline unit on everything that reached it this step."""
        gpm = stream.total() * 60 / self.last_dt
        if isinstance(eq, Pump):
            if eq.running:
                eq.flow_gpm += gpm
                self._forward(eq, 0, stream)
            else:
                self._spill(eq, stream)
        elif isinstance(eq, Reactor):
            eq.load_gpm += gpm
            self._forward(eq, 0, eq.run(stream, gpm, self.last_dt))
        elif isinstance(eq, Separator):
            eq.load_gpm += gpm
            top, bottom = eq.split(stream, gpm)
            self._forward(eq, 0, top)
            self._forward(eq, 1, bottom)
        elif isinstance(eq, Splitter):
            self._forward(eq, 0, stream.scaled(eq.ratio))
            self._forward(eq, 1, stream.scaled(1 - eq.ratio))
        elif isinstance(eq, Mixer):
            self._forward(eq, 0, stream)


_INLINE = (Pump, Reactor, Separator, Splitter, Mixer)
