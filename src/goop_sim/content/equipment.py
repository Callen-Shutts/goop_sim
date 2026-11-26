"""What a run can deal you, and what it costs. All randomness goes through the run's `random.Random`."""

import random

from goop_sim.sim.chemistry import Chemistry, Reaction, side_reaction_for
from goop_sim.sim.equipment import Equipment, Mixer, Pump, Reactor, Separator, Splitter, Tank

SIDE_REACTION_CHANCE = 0.35


class Namer:
    """HMI-style tags: P101, P102, TK101, ..."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}{100 + self.counts[prefix]}"


def make_pump(rng: random.Random, namer: Namer, chem: Chemistry) -> Pump:
    """Random turndown range; the player tunes the setpoint inside it."""
    max_gpm = rng.choice([150, 200, 300, 400, 600])
    min_gpm = round(max_gpm * rng.choice([0.1, 0.2, 0.3]) / 5) * 5
    return Pump(namer("P"), min_gpm=min_gpm, max_gpm=max_gpm)


def make_tank(rng: random.Random, namer: Namer, chem: Chemistry) -> Tank:
    return Tank(namer("TK"), capacity_gal=rng.choice([2_000, 5_000, 10_000, 20_000]))


def make_reactor(rng: random.Random, namer: Namer, chem: Chemistry, reaction: Reaction) -> Reactor:
    reactor = Reactor(
        namer("R"),
        reaction=reaction,
        conversion=round(rng.uniform(0.45, 0.9), 2),
        rated_gpm=rng.choice([80, 120, 160, 200, 250]),
    )
    if rng.random() < SIDE_REACTION_CHANCE:
        reactor.side = side_reaction_for(rng, reaction, chem.waste)
        reactor.side_conversion = round(rng.uniform(0.03, 0.15), 2)
    return reactor


def make_separator(rng: random.Random, namer: Namer, chem: Chemistry, apart: Reaction | None = None) -> Separator:
    """Sharp for a random subset of species: those mostly go top, the rest mostly go bottom.

    With `apart`, the column is guaranteed to send that reaction's product one way and all of
    its reactants the other (which way is random), so the product can be purified.
    """
    species = chem.all_species
    if apart:
        product = next(iter(apart.products))
        others = [s for s in species if s != product and s not in apart.reactants]
        tag_along = set(rng.sample(others, rng.randint(0, min(2, len(others)))))
        lights = {product} | tag_along
        if rng.random() < 0.5:  # flip: product to the bottom instead
            lights = set(species) - lights
    else:
        lights = set(rng.sample(species, rng.randint(1, min(3, len(species) - 1))))
    leak = (0.01, 0.05) if apart else (0.02, 0.15)  # the guaranteed column is a high-purity one
    top = {s: round(1 - rng.uniform(*leak) if s in lights else rng.uniform(*leak), 2) for s in species}
    return Separator(namer("C"), top=top, rated_gpm=rng.choice([100, 150, 200, 300]))


def make_splitter(rng: random.Random, namer: Namer, chem: Chemistry) -> Splitter:
    return Splitter(namer("SP"))


def make_mixer(rng: random.Random, namer: Namer, chem: Chemistry) -> Mixer:
    return Mixer(namer("MX"))


_MAKERS = {
    "pump": make_pump,
    "tank": make_tank,
    "separator": make_separator,
    "splitter": make_splitter,
    "mixer": make_mixer,
}

# Shop weights. "reactor" is handled separately since it needs a reaction.
_SHOP_WEIGHTS = {"pump": 3, "tank": 2, "separator": 3, "splitter": 2, "mixer": 2, "reactor": 3}


def price_of(eq: Equipment) -> int:
    """Store price from stats, so a bigger tank or sharper column is worth paying more for."""
    if isinstance(eq, Pump):
        turndown = 1 - eq.min_gpm / eq.max_gpm  # wider range = more room to tune
        value = 80 + 0.6 * eq.max_gpm + 120 * turndown
    elif isinstance(eq, Tank):
        value = 60 + eq.capacity_gal / 50
    elif isinstance(eq, Reactor):
        value = 150 + 600 * eq.conversion + 1.5 * eq.rated_gpm - (130 if eq.side else 0)
    elif isinstance(eq, Separator):
        sharpness = sum(abs(f - 0.5) * 2 for f in eq.top.values()) / max(1, len(eq.top))
        value = 100 + 450 * sharpness + 1.0 * eq.rated_gpm
    elif isinstance(eq, Splitter):
        value = 120
    elif isinstance(eq, Mixer):
        value = 80
    else:
        value = 0
    return int(round(value / 10) * 10)


def starting_hand(rng: random.Random, chem: Chemistry, namer: Namer) -> list[Equipment]:
    """Enough to make contract 1's product, plus two random extras."""
    hand = [
        make_reactor(rng, namer, chem, chem.chain[0]),
        make_pump(rng, namer, chem),
        make_pump(rng, namer, chem),
        make_tank(rng, namer, chem),
        make_separator(rng, namer, chem, apart=chem.chain[0]),
        make_splitter(rng, namer, chem),
    ]
    if len(chem.feed) > 1:
        hand.append(make_separator(rng, namer, chem))  # two feeds: one more column to sort them
    for kind in rng.choices(list(_MAKERS), k=2):
        hand.append(_MAKERS[kind](rng, namer, chem))
    return hand


def level_grant(rng: random.Random, chem: Chemistry, namer: Namer, level: int) -> list[Equipment]:
    """Free equipment for reaching `level`: for a new reaction, its reactor and a column that can
    separate its product from its reactants (so no run is unwinnable on luck)."""
    if 1 < level <= len(chem.chain):
        reaction = chem.chain[level - 1]
        return [make_reactor(rng, namer, chem, reaction), make_separator(rng, namer, chem, apart=reaction)]
    return []


def shop_offers(rng: random.Random, chem: Chemistry, namer: Namer, level: int, k: int = 6) -> list[Equipment]:
    kinds = rng.choices(list(_SHOP_WEIGHTS), weights=list(_SHOP_WEIGHTS.values()), k=k)
    offers = []
    for kind in kinds:
        if kind == "reactor":
            offers.append(make_reactor(rng, namer, chem, rng.choice(chem.known(level))))
        else:
            offers.append(_MAKERS[kind](rng, namer, chem))
    return offers
