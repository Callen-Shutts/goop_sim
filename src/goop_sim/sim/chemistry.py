"""Species and reactions. Every run rolls its own species names, feed and reaction chain."""

import random
from dataclasses import dataclass

from goop_sim.sim.stream import Stream

# Species are single letters, picked fresh each run (I and O left out: they read like 1 and 0).
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
CHAIN_LENGTH = 3
TWO_FEED_CHANCE = 0.4


@dataclass(eq=False)
class Reaction:
    reactants: dict[str, float]
    products: dict[str, float]

    @property
    def label(self) -> str:
        def side(terms):
            return " + ".join(f"{'' if c == 1 else f'{c:g}'}{s}" for s, c in terms.items())

        return f"{side(self.reactants)} → {side(self.products)}"

    def apply(self, stream: Stream, conversion: float) -> None:
        """Convert `conversion` of the limiting reactant in place."""
        extent = conversion * min(stream.get(s, 0.0) / c for s, c in self.reactants.items())
        if extent <= 0:
            return
        for s, c in self.reactants.items():
            stream[s] = max(0.0, stream[s] - extent * c)
        for s, c in self.products.items():
            stream[s] = stream.get(s, 0.0) + extent * c


def parse(spec: str) -> Reaction:
    """'A+2B>C' -> Reaction({'A': 1, 'B': 2}, {'C': 1})."""

    def terms(text):
        out = {}
        for term in text.split("+"):
            term = term.strip()
            coef = float(term[:-1]) if len(term) > 1 else 1.0
            out[term[-1]] = coef
        return out

    left, right = spec.split(">")
    return Reaction(terms(left), terms(right))


@dataclass(eq=False)
class Chemistry:
    """One run's chemistry.

    `feed` is the raw material's composition (fractions summing to 1; one or two species).
    `chain[n]` makes the product contract n+1 asks for, from species the plant already has.
    `waste` is what side reactions make; never a target.
    """

    chain: list[Reaction]
    feed: dict[str, float]
    waste: str

    @property
    def species(self) -> list[str]:
        """Feed species, then each chain product in order. Excludes waste."""
        out = list(self.feed)
        for reaction in self.chain:
            out += [s for s in reaction.products if s not in out]
        return out

    @property
    def all_species(self) -> list[str]:
        return self.species + [self.waste]

    def target(self, level: int) -> str:
        """Species a contract at `level` asks for. Past the end of the chain it stays on the last one."""
        reaction = self.chain[min(level, len(self.chain)) - 1]
        return next(iter(reaction.products))

    def known(self, level: int) -> list[Reaction]:
        return self.chain[: min(level, len(self.chain))]

    def feed_per_gal(self, species: str) -> float:
        """Rough gallons of feed stream needed per gallon of `species` at 100% conversion.

        Conservative (adds up every reactant's cost as if made separately); used to keep
        contract sizes achievable for whatever chain was rolled.
        """
        if species in self.feed:
            return 1.0 / self.feed[species]
        for reaction in self.chain:
            if species in reaction.products:
                made = reaction.products[species]
                return sum(c * self.feed_per_gal(s) for s, c in reaction.reactants.items()) / made
        raise KeyError(species)


def generate_chemistry(rng: random.Random) -> Chemistry:
    names = rng.sample(LETTERS, CHAIN_LENGTH + 3)
    waste = names.pop()
    if rng.random() < TWO_FEED_CHANCE:
        major = rng.choice([0.5, 0.6, 0.7])
        feed = {names[0]: major, names[1]: round(1 - major, 2)}
        products = names[2 : 2 + CHAIN_LENGTH]
    else:
        feed = {names[0]: 1.0}
        products = names[1 : 1 + CHAIN_LENGTH]

    known = list(feed)
    chain = []
    for step, product in enumerate(products):
        # The newest species always takes part, so each contract builds on the last one's product.
        anchor = known[-1] if step else rng.choice(list(feed))
        reactants = {anchor: rng.choice([1, 1, 2])}
        others = [s for s in known if s != anchor]
        if step == 0 and len(feed) == 2 and rng.random() < 0.6:
            reactants[others[0]] = 1  # the two feeds combine
        elif others and rng.random() < 0.5:
            reactants[rng.choice(others)] = 1
        chain.append(Reaction(reactants, {product: 1}))
        known.append(product)
    return Chemistry(chain, feed, waste)


def side_reaction_for(rng: random.Random, main: Reaction, waste: str) -> Reaction:
    """A side reaction that degrades one of the main reaction's species into waste."""
    involved = sorted(set(main.reactants) | set(main.products))
    return Reaction({rng.choice(involved): 1}, {waste: 1})
