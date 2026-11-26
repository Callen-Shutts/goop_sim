"""One roguelike run: the chemistry, the plant that persists between contracts, and progression."""

import random

from goop_sim.content.equipment import Namer, draft_options, level_grant, starting_hand
from goop_sim.run.contract import Contract, make_contract
from goop_sim.sim.chemistry import generate_chemistry
from goop_sim.sim.equipment import Equipment, Feed, Outlet
from goop_sim.sim.network import Network

RESTARTS = 2  # per contract: restock the feed and empty the plant
DRAFT_PICKS = 2
DRAFT_OPTIONS = 5


class RunState:
    """The plant runs live; a contract is met as soon as enough on-spec product has arrived.

    Running out of feed without meeting it costs a restart; with none left the run is over.
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
        self.level = 1
        self.start_contract()

    def start_contract(self) -> None:
        self.contract: Contract = make_contract(self.level, self.chem, self.rng)
        self.product.spec = self.contract.spec
        self.restarts_left = RESTARTS
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
    def met(self) -> bool:
        return self.contract.check(self.product)

    @property
    def feed_empty(self) -> bool:
        return self.feed.stock.total() < 1.0

    def restart(self) -> bool:
        if self.restarts_left <= 0:
            return False
        self.restarts_left -= 1
        self.reset_plant()
        return True

    def draft_options(self) -> list[Equipment]:
        return draft_options(self.rng, self.chem, self.namer, self.level + 1, DRAFT_OPTIONS)

    def next_grant(self) -> list[Equipment]:
        return level_grant(self.rng, self.chem, self.namer, self.level + 1)

    def advance(self, picks: list[Equipment], grant: list[Equipment]) -> None:
        """Move to the next contract, keeping the plant and adding the new equipment."""
        self.inventory.extend(grant + picks)
        self.level += 1
        self.start_contract()
