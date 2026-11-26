import random
from dataclasses import dataclass

from goop_sim.sim.chemistry import FEED_SPECIES, WASTE_SPECIES, Chemistry
from goop_sim.sim.stream import Stream

# Base delivery per chain step (later steps take more feed per gallon of product).
BASE_QUANTITY = {1: 3000, 2: 1500, 3: 1000}
BASE_PURITY = 0.75
FEED_GAL = 10_000


@dataclass
class Contract:
    level: int
    species: str
    quantity_gal: float
    purity: float
    feed: Stream

    def delivered(self, received: Stream) -> float:
        return received.get(self.species, 0.0)

    def check(self, received: Stream) -> bool:
        return (
            self.delivered(received) >= self.quantity_gal - 1e-6
            and received.fraction(self.species) >= self.purity - 1e-9
        )

    @property
    def summary(self) -> str:
        return f"DELIVER {self.quantity_gal:,.0f} GAL {self.species} @ {self.purity:.0%} PURE"


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
