import random

from goop_sim.sim.equipment import Equipment, Pump, Tank


def deal_hand(rng: random.Random, size: int = 6) -> list[Equipment]:
    """Random starting equipment. Always includes at least one pump so a run is winnable."""
    kinds = ["pump"] + rng.choices(["pump", "tank"], k=size - 1)
    counts = {"pump": 0, "tank": 0}
    hand: list[Equipment] = []
    for kind in kinds:
        counts[kind] += 1
        n = counts[kind]
        if kind == "pump":
            hand.append(Pump(f"PMP{n}", max_gpm=rng.choice([100, 150, 200, 300, 400])))
        else:
            hand.append(
                Tank(
                    f"TNK{n}",
                    capacity_gal=rng.choice([10_000, 25_000, 50_000, 100_000]),
                    diameter_ft=rng.choice([15, 20, 30]),
                )
            )
    return hand
