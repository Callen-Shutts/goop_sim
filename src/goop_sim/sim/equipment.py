from dataclasses import dataclass, field

from goop_sim.sim.chemistry import Reaction
from goop_sim.sim.stream import Stream


@dataclass(eq=False)
class Equipment:
    """A placeable piece of process equipment. pos is the canvas center, None while in the inventory."""

    name: str
    n_in: int = 1
    n_out: int = 1
    pos: tuple[int, int] | None = None
    fixed: bool = False

    def reset(self) -> None:
        """Clear anything the process left behind (contents, readings)."""


@dataclass(eq=False)
class Feed(Equipment):
    """Fixed raw-material supply, restocked at the start of every attempt."""

    n_in: int = 0
    fixed: bool = True
    stock: Stream = field(default_factory=Stream)


@dataclass(eq=False)
class Outlet(Equipment):
    """Fixed outlet. Everything piped here is counted in `received`."""

    n_in: int = 2
    n_out: int = 0
    fixed: bool = True
    received: Stream = field(default_factory=Stream)

    def reset(self) -> None:
        self.received = Stream()


@dataclass(eq=False)
class Tank(Equipment):
    """Holds liquid. Two inlets so a recycle can join; a pump draws from the outlet."""

    n_in: int = 2
    capacity_gal: float = 10_000
    content: Stream = field(default_factory=Stream)

    @property
    def volume_gal(self) -> float:
        return self.content.total()

    @property
    def free_gal(self) -> float:
        return max(0.0, self.capacity_gal - self.volume_gal)

    def reset(self) -> None:
        self.content = Stream()


@dataclass(eq=False)
class Pump(Equipment):
    """Draws from a feed or tank on its inlet and pushes it downstream. Also boosts flow passing through."""

    max_gpm: float = 300
    running: bool = True
    flow_gpm: float = 0.0

    def toggle(self) -> None:
        self.running = not self.running

    def reset(self) -> None:
        self.flow_gpm = 0.0


@dataclass(eq=False)
class Reactor(Equipment):
    """Runs one main reaction on what passes through, plus an optional side reaction."""

    reaction: Reaction | None = None
    conversion: float = 0.7
    side: Reaction | None = None
    side_conversion: float = 0.0

    def react(self, stream: Stream) -> None:
        if self.reaction:
            self.reaction.apply(stream, self.conversion)
        if self.side:
            self.side.apply(stream, self.side_conversion)


@dataclass(eq=False)
class Separator(Equipment):
    """Sends `top[species]` of each species to the top outlet (0), the rest to the bottom outlet (1)."""

    n_out: int = 2
    top: dict[str, float] = field(default_factory=dict)

    def split(self, stream: Stream) -> tuple[Stream, Stream]:
        top = Stream({s: v * self.top.get(s, 0.5) for s, v in stream.items()})
        bottom = Stream({s: v - top[s] for s, v in stream.items()})
        return top, bottom


SPLITTER_RATIOS = (0.25, 0.5, 0.75)


@dataclass(eq=False)
class Splitter(Equipment):
    """Splits by volume: `ratio` to the top outlet, the rest to the bottom. Click to cycle the ratio."""

    n_out: int = 2
    ratio: float = 0.5

    def cycle(self) -> None:
        i = SPLITTER_RATIOS.index(self.ratio) if self.ratio in SPLITTER_RATIOS else -1
        self.ratio = SPLITTER_RATIOS[(i + 1) % len(SPLITTER_RATIOS)]


@dataclass(eq=False)
class Mixer(Equipment):
    """Joins two streams."""

    n_in: int = 2
