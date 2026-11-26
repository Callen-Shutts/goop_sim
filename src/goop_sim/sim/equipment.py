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
    """Fixed outlet. Everything piped here is counted in `received`.

    With a `spec` of (species, purity), each arriving stream is graded: if it is pure enough,
    its target species counts in `accepted`; otherwise the whole stream is `rejected_gal`.
    """

    n_in: int = 2
    n_out: int = 0
    fixed: bool = True
    spec: tuple[str, float] | None = None
    received: Stream = field(default_factory=Stream)
    accepted: Stream = field(default_factory=Stream)
    accepted_volume: float = 0.0  # total gallons of the accepted streams (for average purity)
    rejected_gal: float = 0.0
    inflow: Stream = field(default_factory=Stream)  # arrived during the last step

    def take_in(self, stream: Stream) -> None:
        self.received.add(stream)
        self.inflow.add(stream)
        if self.spec:
            species, purity = self.spec
            if stream.fraction(species) >= purity - 1e-9:
                self.accepted.add({species: stream.get(species, 0.0)})
                self.accepted_volume += stream.total()
            else:
                self.rejected_gal += stream.total()

    @property
    def accepted_purity(self) -> float:
        """Average purity of everything accepted so far."""
        if not self.spec or self.accepted_volume <= 0:
            return 0.0
        return self.accepted.get(self.spec[0], 0.0) / self.accepted_volume

    def reset(self) -> None:
        self.received = Stream()
        self.accepted = Stream()
        self.accepted_volume = 0.0
        self.rejected_gal = 0.0
        self.inflow = Stream()


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
    """Draws `setpoint_gpm` from a feed or tank on its inlet and pushes it downstream.

    The setpoint can be tuned anywhere in [min_gpm, max_gpm]; it starts mid-range.
    A running pump also passes through whatever is pushed into it.
    """

    min_gpm: float = 50
    max_gpm: float = 300
    setpoint_gpm: float | None = None
    running: bool = True
    flow_gpm: float = 0.0

    def __post_init__(self):
        mid = round((self.min_gpm + self.max_gpm) / 2 / 5) * 5
        self.set_setpoint(mid if self.setpoint_gpm is None else self.setpoint_gpm)

    @property
    def step_gpm(self) -> float:
        return max(5, round((self.max_gpm - self.min_gpm) / 20 / 5) * 5)

    def set_setpoint(self, gpm: float) -> None:
        self.setpoint_gpm = min(self.max_gpm, max(self.min_gpm, gpm))

    def nudge(self, steps: int) -> None:
        self.set_setpoint(self.setpoint_gpm + steps * self.step_gpm)

    def toggle(self) -> None:
        self.running = not self.running

    def reset(self) -> None:
        self.flow_gpm = 0.0


def overload(rated_gpm: float, gpm: float) -> float:
    """1.0 at or under rated flow, falling toward 0 as flow exceeds it."""
    return 1.0 if gpm <= rated_gpm else rated_gpm / gpm


@dataclass(eq=False)
class Reactor(Equipment):
    """Runs one main reaction on what passes through, plus an optional side reaction.

    Above `rated_gpm` there is less residence time, so the main conversion drops.
    """

    reaction: Reaction | None = None
    conversion: float = 0.7
    side: Reaction | None = None
    side_conversion: float = 0.0
    rated_gpm: float = 10_000
    load_gpm: float = 0.0  # flow through during the last step

    def effective_conversion(self, gpm: float) -> float:
        return self.conversion * overload(self.rated_gpm, gpm) ** 0.8

    def react(self, stream: Stream, gpm: float = 0.0) -> None:
        if self.reaction:
            self.reaction.apply(stream, self.effective_conversion(gpm))
        if self.side:
            self.side.apply(stream, self.side_conversion)

    def reset(self) -> None:
        self.load_gpm = 0.0


@dataclass(eq=False)
class Separator(Equipment):
    """Sends `top[species]` of each species to the top outlet (0), the rest to the bottom outlet (1).

    Above `rated_gpm` the column floods and every split smears toward 50/50.
    """

    n_out: int = 2
    top: dict[str, float] = field(default_factory=dict)
    rated_gpm: float = 10_000
    load_gpm: float = 0.0

    def effective_top(self, gpm: float) -> dict[str, float]:
        k = overload(self.rated_gpm, gpm)
        return {s: 0.5 + (f - 0.5) * k for s, f in self.top.items()}

    def split(self, stream: Stream, gpm: float = 0.0) -> tuple[Stream, Stream]:
        fractions = self.effective_top(gpm)
        top = Stream({s: v * fractions.get(s, 0.5) for s, v in stream.items()})
        bottom = Stream({s: v - top[s] for s, v in stream.items()})
        return top, bottom

    def reset(self) -> None:
        self.load_gpm = 0.0


SPLITTER_STEP = 0.05


@dataclass(eq=False)
class Splitter(Equipment):
    """Splits by volume: `ratio` to the top outlet, the rest to the bottom. Tunable 0-100%."""

    n_out: int = 2
    ratio: float = 0.5

    def set_ratio(self, ratio: float) -> None:
        self.ratio = round(min(1.0, max(0.0, ratio)) / SPLITTER_STEP) * SPLITTER_STEP

    def nudge(self, steps: int) -> None:
        self.set_ratio(self.ratio + steps * SPLITTER_STEP)


@dataclass(eq=False)
class Mixer(Equipment):
    """Joins two streams."""

    n_in: int = 2
