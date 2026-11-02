import math
from dataclasses import dataclass

GAL_PER_FT3 = 7.48052


@dataclass(eq=False)
class Equipment:
    """A placeable piece of process equipment. pos is the canvas center, None while in the inventory."""

    name: str
    n_in: int = 1
    n_out: int = 1
    pos: tuple[int, int] | None = None
    fixed: bool = False


@dataclass(eq=False)
class Tank(Equipment):
    capacity_gal: float = 50_000
    diameter_ft: float = 20.0
    volume_gal: float = 0.0

    @property
    def level_ft(self) -> float:
        area_ft2 = math.pi * (self.diameter_ft / 2) ** 2
        return self.volume_gal / GAL_PER_FT3 / area_ft2

    @property
    def fraction(self) -> float:
        return self.volume_gal / self.capacity_gal

    @property
    def free_gal(self) -> float:
        return self.capacity_gal - self.volume_gal


@dataclass(eq=False)
class Pump(Equipment):
    max_gpm: float = 300
    running: bool = False
    flow_gpm: float = 0.0

    def toggle(self) -> None:
        self.running = not self.running


@dataclass(eq=False)
class Source(Equipment):
    """Unlimited raw supply."""

    n_in: int = 0
    fixed: bool = True


@dataclass(eq=False)
class Sink(Equipment):
    """Product outlet. Whatever reaches it counts as produced."""

    n_out: int = 0
    fixed: bool = True
