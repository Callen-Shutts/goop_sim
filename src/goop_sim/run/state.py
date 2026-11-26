"""One roguelike run: the chemistry, the plant that persists between contracts, money and progression."""

import random

from goop_sim.content.equipment import Namer, level_grant, price_of, shop_offers, starting_hand
from goop_sim.run.contract import Contract, Payout, make_contract, settle
from goop_sim.sim.chemistry import generate_chemistry
from goop_sim.sim.equipment import Equipment, Feed, Outlet
from goop_sim.sim.network import Network

RESTARTS = 2  # per contract: restock the feed and empty the plant
START_MONEY = 250
SHOP_OFFERS = 6
REROLL_COST = 50
REROLL_STEP = 25  # each reroll in the same store costs this much more


class RunState:
    """The plant runs live; a contract is met as soon as enough on-spec product has arrived.

    Running out of feed without meeting it costs a restart; with none left the run is over.
    Off-spec product and spills are tallied across restarts and charged at payout.
    """

    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else random.randrange(2**31)
        self.rng = random.Random(self.seed)
        self.chem = generate_chemistry(self.rng)
        self.namer = Namer()
        self.net = Network()
        self.feed = Feed("FEED")
        self.product = Outlet("PRODUCT")
        self.waste = Outlet("WASTE", n_in=3)
        for fixture in (self.feed, self.product, self.waste):
            self.net.add(fixture)
        self.inventory: list[Equipment] = starting_hand(self.rng, self.chem, self.namer)
        self.money = START_MONEY
        self.earned = 0
        self.level = 1
        self.last_payout: Payout | None = None
        self.offers: list[Equipment] = []
        self.reroll_cost = REROLL_COST
        self.start_contract()

    # -- contract ---------------------------------------------------------

    def start_contract(self) -> None:
        self.contract: Contract = make_contract(self.level, self.chem, self.rng)
        self.product.spec = self.contract.spec
        self.restarts_left = RESTARTS
        self.carried_offspec = 0.0
        self.carried_spill = 0.0
        self.reset_plant()

    def reset_plant(self) -> None:
        """Restock the feed, empty tanks and outlets. Layout and settings are kept."""
        for eq in self.net.equipment + self.inventory:
            eq.reset()
        self.feed.stock = self.contract.feed.copy()
        self.net.spilled_gal = 0.0
        for pipe in self.net.pipes:
            pipe.carried.clear()

    @property
    def offspec_total(self) -> float:
        return self.carried_offspec + self.product.rejected_gal

    @property
    def spill_total(self) -> float:
        return self.carried_spill + self.net.spilled_gal

    @property
    def met(self) -> bool:
        return self.contract.check(self.product)

    @property
    def feed_empty(self) -> bool:
        return self.feed.stock.total() < 1.0

    def restart(self) -> bool:
        if self.restarts_left <= 0:
            return False
        self.restarts_left -= 1
        self.carried_offspec = self.offspec_total
        self.carried_spill = self.spill_total
        self.reset_plant()
        return True

    def preview_payout(self) -> Payout:
        return settle(self.contract, self.product.accepted_purity, self.offspec_total, self.spill_total)

    def complete_contract(self) -> Payout:
        """Pay out the met contract and stock the store. Call once per contract."""
        payout = self.preview_payout()
        self.money += payout.total
        self.earned += payout.total
        self.last_payout = payout
        self.reroll_cost = REROLL_COST
        self.offers = shop_offers(self.rng, self.chem, self.namer, self.level + 1, SHOP_OFFERS)
        return payout

    # -- store ------------------------------------------------------------

    def price(self, eq: Equipment) -> int:
        return price_of(eq)

    def buy(self, eq: Equipment) -> bool:
        cost = price_of(eq)
        if eq not in self.offers or cost > self.money:
            return False
        self.money -= cost
        self.offers.remove(eq)
        self.inventory.append(eq)
        return True

    def reroll(self) -> bool:
        if self.reroll_cost > self.money:
            return False
        self.money -= self.reroll_cost
        self.reroll_cost += REROLL_STEP
        self.offers = shop_offers(self.rng, self.chem, self.namer, self.level + 1, SHOP_OFFERS)
        return True

    def next_grant(self) -> list[Equipment]:
        return level_grant(self.rng, self.chem, self.namer, self.level + 1)

    def advance(self, grant: list[Equipment]) -> None:
        """Move to the next contract, keeping the plant and adding the free equipment."""
        self.inventory.extend(grant)
        self.offers = []
        self.level += 1
        self.start_contract()
