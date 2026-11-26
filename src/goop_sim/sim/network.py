from dataclasses import dataclass, field
from typing import NamedTuple

from goop_sim.sim.equipment import Equipment, Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.stream import Stream

# A pump's push passes through at most this many pipes. Only a loop with no tank in it gets
# this deep; whatever is still circulating then is spilled.
MAX_DEPTH = 64


class Port(NamedTuple):
    equipment: Equipment
    kind: str  # "in" or "out"
    index: int = 0


@dataclass(eq=False)
class Pipe:
    out: Port
    into: Port
    carried: Stream = field(default_factory=Stream)  # what flowed through during the last step


class Network:
    """Placed equipment plus the pipes between it.

    Flow model: each step, every running pump draws from the feed or tank on its inlet and
    pushes that liquid downstream. It passes instantly through reactors, separators, splitters,
    mixers and other running pumps until it lands in a tank or an outlet. Liquid with nowhere to
    go (open port, full tank, stopped pump, loop with no tank) is spilled.
    """

    def __init__(self):
        self.equipment: list[Equipment] = []
        self.pipes: list[Pipe] = []
        self.spilled_gal = 0.0
        self.moved_gal = 0.0  # drawn by pumps during the last step
        self._dt = 0.0

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
        """Advance `dt` simulated seconds."""
        self.moved_gal = 0.0
        self._dt = dt
        for pipe in self.pipes:
            pipe.carried = Stream()
        pumps = [eq for eq in self.equipment if isinstance(eq, Pump)]
        for pump in pumps:
            pump.flow_gpm = 0.0
        if dt <= 0:
            return
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
            drawn = holdup.take(pump.max_gpm * dt / 60)
            if drawn.total() <= 0:
                continue
            self.moved_gal += drawn.total()
            up.carried.add(drawn)
            pump.flow_gpm += drawn.total() * 60 / dt
            self._forward(pump, 0, drawn, 0)

    def _forward(self, eq: Equipment, index: int, stream: Stream, depth: int) -> None:
        if stream.total() <= 1e-9:
            return
        pipe = self.pipe_at(Port(eq, "out", index))
        if pipe is None:
            self.spilled_gal += stream.total()
            return
        pipe.carried.add(stream)
        self._deliver(pipe.into.equipment, stream, depth + 1)

    def _deliver(self, eq: Equipment, stream: Stream, depth: int) -> None:
        if depth > MAX_DEPTH:
            self.spilled_gal += stream.total()
        elif isinstance(eq, Tank):
            total = stream.total()
            keep = min(1.0, eq.free_gal / total) if total > 0 else 0.0
            eq.content.add(stream.scaled(keep))
            self.spilled_gal += total * (1 - keep)
        elif isinstance(eq, Outlet):
            eq.received.add(stream)
        elif isinstance(eq, Pump):
            if eq.running:
                eq.flow_gpm += stream.total() * 60 / self._dt
                self._forward(eq, 0, stream, depth)
            else:
                self.spilled_gal += stream.total()
        elif isinstance(eq, Reactor):
            out = stream.copy()
            eq.react(out)
            self._forward(eq, 0, out, depth)
        elif isinstance(eq, Separator):
            top, bottom = eq.split(stream)
            self._forward(eq, 0, top, depth)
            self._forward(eq, 1, bottom, depth)
        elif isinstance(eq, Splitter):
            self._forward(eq, 0, stream.scaled(eq.ratio), depth)
            self._forward(eq, 1, stream.scaled(1 - eq.ratio), depth)
        elif isinstance(eq, Mixer):
            self._forward(eq, 0, stream, depth)
        else:
            self.spilled_gal += stream.total()
