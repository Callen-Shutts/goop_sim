import random
from dataclasses import dataclass

from goop_sim.sim.chemistry import FEED_SPECIES, WASTE_SPECIES, Chemistry
from goop_sim.sim.stream import Stream

# Base delivery per chain step (later steps take more feed per gallon of product).
BASE_QUANTITY = {1: 3000, 2: 1500, 3: 1000}
BASE_PURITY = 0.75
FEED_GAL = 15_000  # generous: tuning a plant live wastes feed


@dataclass
class Contract:
    """Deliver `quantity_gal` of `species` into PRODUCT in streams at least `purity` pure.

    Grading happens per stream at the outlet (see Outlet.take_in): off-spec product does not count.
    """

    level: int
    species: str
    quantity_gal: float
    purity: float
    feed: Stream

    @property
    def spec(self) -> tuple[str, float]:
        return self.species, self.purity

    def delivered(self, outlet) -> float:
        return outlet.accepted.get(self.species, 0.0)

    def check(self, outlet) -> bool:
        return self.delivered(outlet) >= self.quantity_gal - 1e-6

    @property
    def summary(self) -> str:
        return f"{self.quantity_gal:,.0f} GAL {self.species} AT {self.purity:.0%}+ PURITY"


def make_contract(level: int, chem: Chemistry, rng: random.Random) -> Contract:
    """Contracts walk down the reaction chain, then get bigger, purer and dirtier past its end."""
    step = min(level, len(chem.chain))
    extra = level - step  # contracts past the end of the chain
    quantity = BASE_QUANTITY[step] * (1 + 0.25 * extra) * rng.uniform(0.9, 1.1)
    purity = min(0.95, BASE_PURITY + 0.05 * extra)
    feed_gal = FEED_GAL + 1000 * (level - 1)
    impurity = rng.uniform(0.05, 0.15) if extra > 0 else 0.0
    feed = Stream({FEED_SPECIES: feed_gal * (1 - impurity)})
    if impurity:
        feed[WASTE_SPECIES] = feed_gal * impurity
    return Contract(level, chem.target(level), round(quantity, -2), purity, feed)
