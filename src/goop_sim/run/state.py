"""One roguelike run: the chemistry, the plant that persists between contracts, and progression."""

import random

from goop_sim.content.equipment import Namer, draft_options, level_grant, starting_hand
from goop_sim.run.contract import Contract, make_contract
from goop_sim.sim.chemistry import generate_chemistry
from goop_sim.sim.equipment import Equipment, Feed, Outlet
from goop_sim.sim.network import Network

ATTEMPTS = 3
DRAFT_PICKS = 2
DRAFT_OPTIONS = 5


class RunState:
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
        self.over = False
        self.start_contract()

    def start_contract(self) -> None:
        self.contract: Contract = make_contract(self.level, self.chem, self.rng)
        self.attempts_left = ATTEMPTS
        self.reset_plant()

    def reset_plant(self) -> None:
        """Back to a fresh attempt: restock the feed, empty tanks and outlets. Layout is kept."""
        for eq in self.net.equipment + self.inventory:
            eq.reset()
        self.feed.stock = self.contract.feed.copy()
        self.net.spilled_gal = 0.0
        for pipe in self.net.pipes:
            pipe.carried.clear()

    def finish_attempt(self) -> bool:
        """Score the attempt that just ran. A failure costs an attempt; running out ends the run."""
        if self.contract.check(self.product.received):
            return True
        self.attempts_left -= 1
        if self.attempts_left <= 0:
            self.over = True
        return False

    def draft_options(self) -> list[Equipment]:
        return draft_options(self.rng, self.chem, self.namer, self.level + 1, DRAFT_OPTIONS)

    def next_grant(self) -> list[Equipment]:
        return level_grant(self.rng, self.chem, self.namer, self.level + 1)

    def advance(self, picks: list[Equipment], grant: list[Equipment]) -> None:
        """Move to the next contract, keeping the plant and adding the new equipment."""
        self.inventory.extend(grant + picks)
        self.level += 1
        self.start_contract()
