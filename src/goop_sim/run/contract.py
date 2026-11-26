import random
from dataclasses import dataclass

from goop_sim.sim.chemistry import Chemistry
from goop_sim.sim.stream import Stream

# Target delivery of the level's new product, before capping to what the rolled chemistry can yield.
BASE_QUANTITY = {1: 3000, 2: 1500, 3: 1000, 4: 800}
MAX_YIELD_SHARE = 0.35  # never ask for more than this share of the theoretical max yield (all orders together)
BASE_PURITY = 0.75
SIDE_ORDER_PURITIES = [0.6, 0.65, 0.7, 0.8, 0.85, 0.9]  # extra orders can be looser or stricter than the main one
SIDE_ORDER_SHARE = (0.3, 0.6)  # extra order size relative to the main one
FEED_GAL = 15_000  # generous: tuning a plant live wastes feed

# Money. Pay rewards purity above spec, never extra quantity. Waste costs money, time doesn't,
# so slow or odd settings are safe to explore; sloppy product is what hurts.
BASE_PAY = 600
PAY_PER_LEVEL = 300
PAY_PER_EXTRA_ORDER = 0.35  # base pay multiplier added for each order beyond the first
PURITY_BONUS = 1.5  # bonus = base * PURITY_BONUS * (how far from spec toward 100% pure)
OFFSPEC_FEE = 0.08  # $ per gallon rejected at a PRODUCT outlet
SPILL_FEE = 0.15  # $ per gallon spilled
PAY_FLOOR = 0.2  # completing a contract always pays at least this share of base


@dataclass
class Order:
    """Deliver `quantity_gal` of `species` in streams at least `purity` pure, to one PRODUCT outlet.

    Grading happens per stream at the outlet (see Outlet.take_in): off-spec product does not count.
    """

    species: str
    quantity_gal: float
    purity: float

    @property
    def spec(self) -> tuple[str, float]:
        return self.species, self.purity

    def delivered(self, outlet) -> float:
        return outlet.accepted.get(self.species, 0.0)

    def met(self, outlet) -> bool:
        return self.delivered(outlet) >= self.quantity_gal - 1e-6

    @property
    def summary(self) -> str:
        return f"{self.quantity_gal:,.0f} GAL {self.species} AT {self.purity:.0%}+"


@dataclass
class Contract:
    """One or more orders, each graded at its own PRODUCT outlet (order i -> outlet i)."""

    level: int
    orders: list[Order]
    feed: Stream
    base_pay: float

    def check(self, outlets) -> bool:
        return all(order.met(outlet) for order, outlet in zip(self.orders, outlets))

    @property
    def summary(self) -> str:
        return " + ".join(order.summary for order in self.orders)


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


def settle(contract: Contract, purities: list[float], offspec_gal: float, spill_gal: float) -> Payout:
    """`purities[i]` is the average purity of what order i accepted. Each order's bonus share is
    weighted by its size."""
    total_qty = sum(o.quantity_gal for o in contract.orders) or 1.0
    above = avg = 0.0
    for order, purity in zip(contract.orders, purities):
        headroom = max(1e-9, 1 - order.purity)
        weight = order.quantity_gal / total_qty
        above += weight * max(0.0, min(1.0, (purity - order.purity) / headroom))
        avg += weight * purity
    return Payout(
        base=contract.base_pay,
        purity_bonus=contract.base_pay * PURITY_BONUS * above,
        offspec_fee=offspec_gal * OFFSPEC_FEE,
        spill_fee=spill_gal * SPILL_FEE,
        avg_purity=avg,
        floor=contract.base_pay * PAY_FLOOR,
    )


def order_count(level: int, rng: random.Random) -> int:
    """How many products a contract asks for: one at first, up to three later."""
    if level <= 1:
        return 1
    if level == 2:
        return rng.choice([1, 2])
    if level == 3:
        return 2
    return rng.choice([2, 3])


def make_contract(level: int, chem: Chemistry, rng: random.Random, min_orders: int = 1) -> Contract:
    """The main order is the level's new product; extra orders ask for earlier products at their
    own purity. Past the end of the chain, contracts get bigger, purer and dirtier."""
    step = min(level, len(chem.chain))
    extra = level - step  # contracts past the end of the chain
    feed_gal = FEED_GAL + 1000 * (level - 1)
    main = chem.target(level)
    earlier = [chem.target(n) for n in range(1, step) if chem.target(n) != main]
    n_orders = min(max(order_count(level, rng), min_orders), 1 + len(earlier))

    main_qty = BASE_QUANTITY[step] * (1 + 0.25 * extra)
    orders = [Order(main, main_qty, min(0.95, BASE_PURITY + 0.05 * extra))]
    for species in rng.sample(earlier, n_orders - 1):
        purity = min(0.95, rng.choice(SIDE_ORDER_PURITIES) + 0.03 * extra)
        orders.append(Order(species, main_qty * rng.uniform(*SIDE_ORDER_SHARE), purity))

    # Keep the whole contract achievable for whatever chain was rolled.
    cost = sum(o.quantity_gal * chem.feed_per_gal(o.species) for o in orders)
    scale = min(1.0, MAX_YIELD_SHARE * feed_gal / cost)
    for o in orders:
        o.quantity_gal = max(100, round(o.quantity_gal * scale * rng.uniform(0.9, 1.1), -2))

    impurity = rng.uniform(0.05, 0.15) if extra > 0 else 0.0
    feed = Stream({s: feed_gal * (1 - impurity) * f for s, f in chem.feed.items()})
    if impurity:
        feed[chem.waste] = feed_gal * impurity
    base = (BASE_PAY + PAY_PER_LEVEL * (level - 1)) * (1 + PAY_PER_EXTRA_ORDER * (len(orders) - 1))
    return Contract(level, orders, feed, round(base, -1))
