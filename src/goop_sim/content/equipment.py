"""What a run can deal you. All randomness goes through the run's `random.Random`."""

import random

from goop_sim.sim.chemistry import SPECIES, Chemistry, Reaction, side_reaction_for
from goop_sim.sim.equipment import Equipment, Mixer, Pump, Reactor, Separator, Splitter, Tank

SIDE_REACTION_CHANCE = 0.35


class Namer:
    """HMI-style tags: P101, P102, TK101, ..."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}{100 + self.counts[prefix]}"


def make_pump(rng: random.Random, namer: Namer) -> Pump:
    """Random turndown range; the player tunes the setpoint inside it."""
    max_gpm = rng.choice([150, 200, 300, 400, 600])
    min_gpm = round(max_gpm * rng.choice([0.1, 0.2, 0.3]) / 5) * 5
    return Pump(namer("P"), min_gpm=min_gpm, max_gpm=max_gpm)


def make_tank(rng: random.Random, namer: Namer) -> Tank:
    return Tank(namer("TK"), capacity_gal=rng.choice([2_000, 5_000, 10_000, 20_000]))


def make_reactor(rng: random.Random, namer: Namer, reaction: Reaction) -> Reactor:
    reactor = Reactor(
        namer("R"),
        reaction=reaction,
        conversion=round(rng.uniform(0.45, 0.9), 2),
        rated_gpm=rng.choice([80, 120, 160, 200, 250]),
    )
    if rng.random() < SIDE_REACTION_CHANCE:
        reactor.side = side_reaction_for(rng, reaction)
        reactor.side_conversion = round(rng.uniform(0.03, 0.15), 2)
    return reactor


def make_separator(rng: random.Random, namer: Namer) -> Separator:
    """Sharp for a random subset of species: those mostly go top, the rest mostly go bottom."""
    lights = set(rng.sample(SPECIES, rng.randint(1, 3)))
    top = {
        s: round(rng.uniform(0.85, 0.98) if s in lights else rng.uniform(0.02, 0.15), 2)
        for s in SPECIES
    }
    return Separator(namer("C"), top=top, rated_gpm=rng.choice([100, 150, 200, 300]))


def make_splitter(rng: random.Random, namer: Namer) -> Splitter:
    return Splitter(namer("SP"))


def make_mixer(rng: random.Random, namer: Namer) -> Mixer:
    return Mixer(namer("MX"))


_MAKERS = {
    "pump": make_pump,
    "tank": make_tank,
    "separator": make_separator,
    "splitter": make_splitter,
    "mixer": make_mixer,
}

# Draft pool weights. "reactor" is handled separately since it needs a reaction.
_DRAFT_WEIGHTS = {"pump": 3, "tank": 2, "separator": 3, "splitter": 2, "mixer": 2, "reactor": 2}


def starting_hand(rng: random.Random, chem: Chemistry, namer: Namer) -> list[Equipment]:
    """Enough to make contract 1's product, plus two random extras."""
    hand = [
        make_reactor(rng, namer, chem.chain[0]),
        make_pump(rng, namer),
        make_pump(rng, namer),
        make_tank(rng, namer),
        make_separator(rng, namer),
        make_splitter(rng, namer),
    ]
    for kind in rng.choices(list(_MAKERS), k=2):
        hand.append(_MAKERS[kind](rng, namer))
    return hand


def level_grant(rng: random.Random, chem: Chemistry, namer: Namer, level: int) -> list[Equipment]:
    """Free equipment for reaching `level`: a reactor for the new reaction, if there is one."""
    if level <= len(chem.chain) and level > 1:
        return [make_reactor(rng, namer, chem.chain[level - 1])]
    return []


def draft_options(rng: random.Random, chem: Chemistry, namer: Namer, level: int, k: int = 5) -> list[Equipment]:
    kinds = rng.choices(list(_DRAFT_WEIGHTS), weights=list(_DRAFT_WEIGHTS.values()), k=k)
    options = []
    for kind in kinds:
        if kind == "reactor":
            options.append(make_reactor(rng, namer, rng.choice(chem.known(level))))
        else:
            options.append(_MAKERS[kind](rng, namer))
    return options
