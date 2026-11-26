import random
from dataclasses import dataclass

from goop_sim.sim.chemistry import Chemistry
from goop_sim.sim.stream import Stream

# Target delivery per chain step, before capping to what the rolled chemistry can yield.
BASE_QUANTITY = {1: 3000, 2: 1500, 3: 1000}
MAX_YIELD_SHARE = 0.35  # never ask for more than this share of the theoretical max yield
BASE_PURITY = 0.75
FEED_GAL = 15_000  # generous: tuning a plant live wastes feed

# Money. Pay rewards purity above spec, never extra quantity. Waste costs money, time doesn't,
# so slow or odd settings are safe to explore; sloppy product is what hurts.
BASE_PAY = 600
PAY_PER_LEVEL = 300
PURITY_BONUS = 1.5  # bonus = base * PURITY_BONUS * (how far from spec toward 100% pure)
OFFSPEC_FEE = 0.08  # $ per gallon rejected at PRODUCT
SPILL_FEE = 0.15  # $ per gallon spilled
PAY_FLOOR = 0.2  # completing a contract always pays at least this share of base


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
    base_pay: float

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


@dataclass
class Payout:
    base: float
    purity_bonus: float
    offspec_fee: float
    spill_fee: float
    avg_purity: float
    floor: float

    @property
    def total(self) -> int:
        raw = self.base + self.purity_bonus - self.offspec_fee - self.spill_fee
        return round(max(self.floor, raw))


def settle(contract: Contract, avg_purity: float, offspec_gal: float, spill_gal: float) -> Payout:
    headroom = max(1e-9, 1 - contract.purity)
    above = max(0.0, min(1.0, (avg_purity - contract.purity) / headroom))
    return Payout(
        base=contract.base_pay,
        purity_bonus=contract.base_pay * PURITY_BONUS * above,
        offspec_fee=offspec_gal * OFFSPEC_FEE,
        spill_fee=spill_gal * SPILL_FEE,
        avg_purity=avg_purity,
        floor=contract.base_pay * PAY_FLOOR,
    )


def make_contract(level: int, chem: Chemistry, rng: random.Random) -> Contract:
    """Contracts walk down the reaction chain, then get bigger, purer and dirtier past its end."""
    step = min(level, len(chem.chain))
    extra = level - step  # contracts past the end of the chain
    feed_gal = FEED_GAL + 1000 * (level - 1)
    species = chem.target(level)
    max_yield = feed_gal / chem.feed_per_gal(species)
    quantity = min(BASE_QUANTITY[step] * (1 + 0.25 * extra), MAX_YIELD_SHARE * max_yield)
    quantity = max(100, round(quantity * rng.uniform(0.9, 1.1), -2))
    purity = min(0.95, BASE_PURITY + 0.05 * extra)
    impurity = rng.uniform(0.05, 0.15) if extra > 0 else 0.0
    feed = Stream({s: feed_gal * (1 - impurity) * f for s, f in chem.feed.items()})
    if impurity:
        feed[chem.waste] = feed_gal * impurity
    return Contract(level, species, quantity, purity, feed, BASE_PAY + PAY_PER_LEVEL * (level - 1))
