"""Species and reactions. Letters are fixed (feed A or A+B, products in alphabetical order after
the feed, waste W); every run rolls its own feed mix and reaction stoichiometry."""

import math
import random
from dataclasses import dataclass

from goop_sim.sim.stream import Stream

LETTERS = "ABCDEFGH"  # feed species first, then each new product in the order it is unlocked
WASTE = "W"
CHAIN_LENGTH = 4
TWO_FEED_CHANCE = 0.4
COEFFICIENTS = [1, 1, 2, 2, 3]
SECOND_REACTANT_CHANCE = 0.65


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
    """A run's chemistry. The chain is fixed for the whole run and unlocks one reaction per level.

    Reaction 1 makes the first product from the feed. Every later reaction uses at least one
    product the plant already makes (any earlier one, newer ones likelier), maybe with one more
    species it has, so each level builds on the plant from before. Stoichiometric coefficients
    are random (1-3).
    """
    if rng.random() < TWO_FEED_CHANCE:
        major = rng.choice([0.5, 0.6, 0.7])
        feed = {"A": major, "B": round(1 - major, 2)}
    else:
        feed = {"A": 1.0}
    products = list(LETTERS[len(feed) : len(feed) + CHAIN_LENGTH])

    known = list(feed)
    made: list[str] = []
    chain: list[Reaction] = []
    for product in products:
        for _try in range(20):
            if not made:
                if len(feed) == 2 and rng.random() < 0.6:
                    reactants = {"A": rng.choice(COEFFICIENTS), "B": rng.choice(COEFFICIENTS)}  # the two feeds combine
                else:
                    reactants = {rng.choice(list(feed)): rng.choice([1, 2, 2, 3])}
            else:
                anchor = rng.choices(made, weights=range(1, len(made) + 1))[0]
                reactants = {anchor: rng.choice(COEFFICIENTS)}
                others = [s for s in known if s != anchor]
                if rng.random() < SECOND_REACTANT_CHANCE:
                    reactants[rng.choice(others)] = rng.choice(COEFFICIENTS)
            if all(set(reactants) != set(r.reactants) for r in chain):
                break  # each reaction uses a different set of species
        g = math.gcd(*reactants.values()) if len(reactants) > 1 else 1  # 2A + 2B -> A + B; 2C -> D stays
        chain.append(Reaction({sp: c // g for sp, c in sorted(reactants.items())}, {product: 1}))
        known.append(product)
        made.append(product)
    return Chemistry(chain, feed, WASTE)


def side_reaction_for(rng: random.Random, main: Reaction, waste: str) -> Reaction:
    """A side reaction that degrades one of the main reaction's species into waste."""
    involved = sorted(set(main.reactants) | set(main.products))
    return Reaction({rng.choice(involved): 1}, {waste: 1})
