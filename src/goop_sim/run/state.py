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
        self.products: list[Outlet] = []  # one PRODUCT outlet per order; more are added as contracts grow
        self.waste = Outlet("WASTE", n_in=3)
        for fixture in (self.feed, self.waste):
            self.net.add(fixture)
        self.inventory: list[Equipment] = starting_hand(self.rng, self.chem, self.namer)
        self.money = START_MONEY
        self.earned = 0
        self.level = 1
        self.last_payout: Payout | None = None
        self.offers: list[Equipment] = []
        self.reroll_cost = REROLL_COST
        self.next_contract: Contract | None = None  # rolled when a contract is paid, shown in the store
        self.start_contract(make_contract(self.level, self.chem, self.rng))

    # -- contract ---------------------------------------------------------

    @property
    def product(self) -> Outlet:
        """The first PRODUCT outlet (the level's main order)."""
        return self.products[0]

    def start_contract(self, contract: Contract) -> None:
        self.contract = contract
        while len(self.products) < len(contract.orders):
            n = len(self.products) + 1
            outlet = Outlet("PRODUCT" if n == 1 else f"PRODUCT {n}")
            self.products.append(outlet)
            self.net.add(outlet)
        for outlet, order in zip(self.products, contract.orders):
            outlet.spec = order.spec
        for outlet in self.products[len(contract.orders) :]:
            outlet.spec = None  # not used by this contract
        self.restarts_left = RESTARTS
        self.carried_offspec = 0.0
        self.carried_spill = 0.0
        self.reset_plant()

    def reset_plant(self) -> None:
        """Restock the feed, empty tanks and outlets. Layout and settings are kept."""
        for eq in self.net.equipment + self.inventory:
            eq.reset()
        self.feed.stock = self.contract.feed.copy()
        self.net.clear_spills()
        for pipe in self.net.pipes:
            pipe.empty()

    @property
    def offspec_total(self) -> float:
        return self.carried_offspec + sum(o.rejected_gal for o in self.products)

    @property
    def spill_total(self) -> float:
        return self.carried_spill + self.net.spilled_gal

    @property
    def met(self) -> bool:
        return self.contract.check(self.products)

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
        purities = [o.accepted_purity for o in self.products[: len(self.contract.orders)]]
        return settle(self.contract, purities, self.offspec_total, self.spill_total)

    def complete_contract(self) -> Payout:
        """Pay out the met contract and stock the store. Call once per contract."""
        payout = self.preview_payout()
        self.money += payout.total
        self.earned += payout.total
        self.last_payout = payout
        self.reroll_cost = REROLL_COST
        self.offers = shop_offers(self.rng, self.chem, self.namer, self.level + 1, SHOP_OFFERS)
        self.next_contract = make_contract(self.level + 1, self.chem, self.rng, min_orders=len(self.products))
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
        contract = self.next_contract or make_contract(self.level, self.chem, self.rng, min_orders=len(self.products))
        self.next_contract = None
        self.start_contract(contract)
