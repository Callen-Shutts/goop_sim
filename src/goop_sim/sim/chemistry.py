"""Species and reactions. Each run rolls its own reaction chain from templates."""

import random
from dataclasses import dataclass

from goop_sim.sim.stream import Stream

SPECIES = "ABCDE"
FEED_SPECIES = "A"
WASTE_SPECIES = "E"  # side reactions make this; never a contract target

# Templates for each step of the chain. "A+B>C" means 1 gal A + 1 gal B -> 1 gal C.
# Each step's product is the next contract's target, and it is always made from species
# the plant already handles, so a plant built for one contract can be extended for the next.
STEP_TEMPLATES = [
    ["A>B", "2A>B"],
    ["B>C", "A+B>C", "2B>C"],
    ["C>D", "B+C>D", "A+C>D"],
]


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
    chain: list[Reaction]

    def target(self, level: int) -> str:
        """Species a contract at `level` asks for. Past the end of the chain it stays on the last one."""
        reaction = self.chain[min(level, len(self.chain)) - 1]
        return next(iter(reaction.products))

    def known(self, level: int) -> list[Reaction]:
        return self.chain[: min(level, len(self.chain))]


def generate_chemistry(rng: random.Random) -> Chemistry:
    return Chemistry([parse(rng.choice(options)) for options in STEP_TEMPLATES])


def side_reaction_for(rng: random.Random, main: Reaction) -> Reaction:
    """A side reaction that degrades one of the main reaction's species into waste."""
    involved = sorted(set(main.reactants) | set(main.products))
    return parse(f"{rng.choice(involved)}>{WASTE_SPECIES}")
