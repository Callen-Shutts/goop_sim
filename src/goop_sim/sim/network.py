from dataclasses import dataclass
from typing import NamedTuple

from goop_sim.sim.equipment import Equipment, Pump, Sink, Tank


class Port(NamedTuple):
    equipment: Equipment
    kind: str  # "in" or "out"
    index: int = 0


@dataclass(eq=False)
class Pipe:
    out: Port
    into: Port


class Network:
    """Placed equipment plus the pipes between it. Pumps are the only things that move liquid."""

    def __init__(self, target_gal: float = 5000):
        self.equipment: list[Equipment] = []
        self.pipes: list[Pipe] = []
        self.produced_gal = 0.0
        self.target_gal = target_gal

    @property
    def complete(self) -> bool:
        return self.produced_gal >= self.target_gal

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

    def step(self, dt: float) -> None:
        for pump in self.equipment:
            if not isinstance(pump, Pump):
                continue
            moved = 0.0
            up_pipe = self.pipe_at(Port(pump, "in"))
            down_pipe = self.pipe_at(Port(pump, "out"))
            if pump.running and up_pipe and down_pipe:
                up = up_pipe.out.equipment
                down = down_pipe.into.equipment
                if not isinstance(up, Pump) and not isinstance(down, Pump):
                    moved = pump.max_gpm * dt / 60
                    if isinstance(up, Tank):
                        moved = min(moved, up.volume_gal)
                        up.volume_gal -= moved
                    if isinstance(down, Tank):
                        moved = min(moved, down.free_gal)
                        down.volume_gal += moved
                    elif isinstance(down, Sink):
                        self.produced_gal += moved
            pump.flow_gpm = moved * 60 / dt if dt > 0 else 0.0
