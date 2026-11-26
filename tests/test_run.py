import random

import pytest

from goop_sim.content.equipment import Namer, level_grant, make_pump, price_of, shop_offers, starting_hand
from goop_sim.run.contract import MAX_YIELD_SHARE, make_contract, settle
from goop_sim.run.state import RESTARTS, START_MONEY, RunState
from goop_sim.sim.chemistry import generate_chemistry, parse
from goop_sim.sim.equipment import Outlet, Pump, Reactor, Separator, Tank
from goop_sim.sim.stream import Stream

SEEDS = range(60)


# -- chemistry ----------------------------------------------------------------


def test_chemistry_is_seeded():
    for seed in SEEDS:
        a, b = generate_chemistry(random.Random(seed)), generate_chemistry(random.Random(seed))
        assert [r.label for r in a.chain] == [r.label for r in b.chain]
        assert a.feed == b.feed and a.waste == b.waste


def test_each_step_builds_on_what_the_plant_already_makes():
    for seed in SEEDS:
        chem = generate_chemistry(random.Random(seed))
        assert sum(chem.feed.values()) == pytest.approx(1.0)
        known = list(chem.feed)
        for level, reaction in enumerate(chem.chain, start=1):
            assert set(reaction.reactants) <= set(known)
            if level > 1:
                assert known[-1] in reaction.reactants  # newest product is always used
            target = chem.target(level)
            assert target not in known and target != chem.waste
            known.append(target)
        assert chem.waste not in chem.species
        assert chem.target(len(chem.chain) + 3) == chem.target(len(chem.chain))


def test_runs_get_different_chemistry():
    chains = {tuple(r.label for r in generate_chemistry(random.Random(s)).chain) for s in SEEDS}
    feeds = {tuple(generate_chemistry(random.Random(s)).feed) for s in SEEDS}
    assert len(chains) > 50  # nearly every run is different
    assert len(feeds) > 30  # feed species vary too
    assert any(len(f) == 2 for f in feeds) and any(len(f) == 1 for f in feeds)


def test_feed_per_gal_follows_stoichiometry():
    chem = generate_chemistry(random.Random(0))
    chem.feed = {"A": 1.0}
    chem.chain = [parse("2A>B"), parse("A+B>C")]
    assert chem.feed_per_gal("A") == 1
    assert chem.feed_per_gal("B") == 2
    assert chem.feed_per_gal("C") == 3


# -- dealing and pricing ----------------------------------------------------------


def test_starting_hand_can_make_the_first_product():
    for seed in range(10):
        chem = generate_chemistry(random.Random(seed))
        hand = starting_hand(random.Random(seed), chem, Namer())
        assert any(isinstance(e, Reactor) and e.reaction is chem.chain[0] for e in hand)
        assert sum(isinstance(e, Pump) for e in hand) >= 2
        assert any(isinstance(e, Separator) for e in hand)
        assert any(isinstance(e, Tank) for e in hand)
        assert len({e.name for e in hand}) == len(hand)
        for sep in (e for e in hand if isinstance(e, Separator)):
            assert set(sep.top) == set(chem.all_species)


def test_every_new_reaction_comes_with_a_column_that_can_purify_it():
    for seed in SEEDS:
        rng = random.Random(seed)
        chem = generate_chemistry(rng)
        namer = Namer()
        columns = [[e for e in starting_hand(rng, chem, namer) if isinstance(e, Separator)]]
        for level in range(2, len(chem.chain) + 1):
            columns.append([e for e in level_grant(rng, chem, namer, level) if isinstance(e, Separator)])
        for reaction, options in zip(chem.chain, columns):
            product = next(iter(reaction.products))
            assert any(
                all((c.top[product] > 0.5) != (c.top[r] > 0.5) for r in reaction.reactants) for c in options
            ), (seed, reaction.label)


def test_dealt_pumps_have_a_tunable_range():
    rng, namer, chem = random.Random(0), Namer(), generate_chemistry(random.Random(0))
    for _ in range(50):
        p = make_pump(rng, namer, chem)
        assert 0 < p.min_gpm < p.max_gpm
        assert p.min_gpm <= p.setpoint_gpm <= p.max_gpm


def test_better_stats_cost_more():
    assert price_of(Tank("a", capacity_gal=20_000)) > price_of(Tank("b", capacity_gal=2_000))
    assert price_of(Pump("a", min_gpm=40, max_gpm=400)) > price_of(Pump("b", min_gpm=40, max_gpm=150))
    assert price_of(Pump("a", min_gpm=30, max_gpm=300)) > price_of(Pump("b", min_gpm=90, max_gpm=300))
    rxn = parse("A>B")
    assert price_of(Reactor("a", reaction=rxn, conversion=0.9, rated_gpm=200)) > price_of(
        Reactor("b", reaction=rxn, conversion=0.5, rated_gpm=200)
    )
    assert price_of(Reactor("a", reaction=rxn, conversion=0.7, rated_gpm=250)) > price_of(
        Reactor("b", reaction=rxn, conversion=0.7, rated_gpm=80)
    )
    assert price_of(Reactor("a", reaction=rxn, conversion=0.7)) > price_of(
        Reactor("b", reaction=rxn, conversion=0.7, side=parse("A>E"), side_conversion=0.1)
    )
    sharp = Separator("a", top={"A": 0.98, "B": 0.02}, rated_gpm=200)
    dull = Separator("b", top={"A": 0.85, "B": 0.15}, rated_gpm=200)
    assert price_of(sharp) > price_of(dull)


def test_grant_and_shop_only_use_known_reactions():
    rng = random.Random(2)
    chem = generate_chemistry(rng)
    namer = Namer()
    reactor, column = level_grant(rng, chem, namer, 2)
    assert reactor.reaction is chem.chain[1]
    assert isinstance(column, Separator)
    assert level_grant(rng, chem, namer, 1) == []
    assert level_grant(rng, chem, namer, len(chem.chain) + 1) == []
    for _ in range(20):
        for eq in shop_offers(rng, chem, namer, 2):
            if isinstance(eq, Reactor):
                assert eq.reaction in chem.chain[:2]


# -- contracts and money --------------------------------------------------------------


def test_contracts_escalate_and_stay_achievable():
    for seed in range(20):
        rng = random.Random(seed)
        chem = generate_chemistry(rng)
        contracts = [make_contract(level, chem, rng) for level in range(1, 7)]
        assert [c.species for c in contracts[:3]] == [chem.target(1), chem.target(2), chem.target(3)]
        assert contracts[5].purity > contracts[2].purity
        assert contracts[5].feed.get(chem.waste, 0) > 0 and contracts[0].feed.get(chem.waste, 0) == 0
        assert contracts[5].base_pay > contracts[0].base_pay
        for c in contracts:
            max_yield = c.feed.total() / chem.feed_per_gal(c.species)
            assert c.quantity_gal <= MAX_YIELD_SHARE * max_yield * 1.1 + 100


def test_contract_counts_only_on_spec_product():
    contract = make_contract(1, generate_chemistry(random.Random(0)), random.Random(0))
    sp, qty = contract.species, contract.quantity_gal
    out = Outlet("O", spec=contract.spec)
    out.take_in(Stream({sp: qty, "zz": qty}))  # 50% pure: rejected
    assert not contract.check(out)
    out.take_in(Stream({sp: qty - 1}))
    assert not contract.check(out)
    out.take_in(Stream({sp: 1}))
    assert contract.check(out)


def test_outlet_tracks_average_purity_of_accepted_product():
    out = Outlet("O", spec=("B", 0.8))
    out.take_in(Stream(B=90, A=10))
    out.take_in(Stream(B=100))
    out.take_in(Stream(B=10, A=90))  # rejected, does not drag the average down
    assert out.accepted_purity == pytest.approx(190 / 200)


def test_payout_rewards_purity_not_quantity_and_charges_waste():
    contract = make_contract(1, generate_chemistry(random.Random(0)), random.Random(0))
    at_spec = settle(contract, contract.purity, 0, 0)
    purer = settle(contract, (contract.purity + 1) / 2, 0, 0)
    perfect = settle(contract, 1.0, 0, 0)
    assert at_spec.total == contract.base_pay
    assert at_spec.total < purer.total < perfect.total
    sloppy = settle(contract, contract.purity, 2000, 500)
    assert sloppy.total < at_spec.total
    assert settle(contract, contract.purity, 1e9, 1e9).total == round(contract.base_pay * 0.2)


def test_run_meets_contract_and_gets_paid():
    run = RunState(seed=1)
    assert run.money == START_MONEY
    assert run.product.spec == run.contract.spec
    assert not run.met
    run.product.take_in(Stream({run.contract.species: run.contract.quantity_gal}))
    assert run.met
    payout = run.complete_contract()
    assert payout.purity_bonus > 0  # 100% pure product
    assert run.money == START_MONEY + payout.total
    assert len(run.offers) == 6


def test_fees_survive_restarts():
    run = RunState(seed=1)
    run.product.rejected_gal = 1000
    run.net.spilled_gal = 200
    assert run.restart()
    assert run.product.rejected_gal == 0
    assert run.offspec_total == 1000 and run.spill_total == 200


def test_restarts_restock_and_run_out():
    run = RunState(seed=1)
    run.feed.stock.take(1e9)
    assert run.feed_empty
    for _ in range(RESTARTS):
        assert run.restart()
        assert not run.feed_empty
        run.feed.stock.take(1e9)
    assert not run.restart()


# -- store -------------------------------------------------------------------------------


def test_buying_and_rerolling():
    run = RunState(seed=4)
    run.product.take_in(Stream({run.contract.species: run.contract.quantity_gal}))
    run.complete_contract()
    run.money = 10_000
    item = run.offers[0]
    cost = price_of(item)
    assert run.buy(item)
    assert item in run.inventory and item not in run.offers
    assert run.money == 10_000 - cost
    assert not run.buy(item)  # already bought

    run.money = 0
    assert not run.buy(run.offers[0])
    assert not run.reroll()
    run.money = 1000
    first_cost = run.reroll_cost
    assert run.reroll()
    assert run.money == 1000 - first_cost and run.reroll_cost > first_cost


def test_advance_keeps_the_plant_and_restocks():
    run = RunState(seed=3)
    pump = next(e for e in run.inventory if isinstance(e, Pump))
    run.inventory.remove(pump)
    pump.pos = (300, 300)
    pump.set_setpoint(pump.max_gpm)
    run.net.add(pump)
    run.feed.stock.take(5000)
    run.product.take_in(Stream({run.contract.species: run.contract.quantity_gal}))
    run.complete_contract()
    money = run.money

    grant = run.next_grant()
    run.advance(grant)

    assert run.level == 2
    assert pump in run.net.equipment
    assert pump.setpoint_gpm == pump.max_gpm  # settings carry over
    assert all(e in run.inventory for e in grant)
    assert run.money == money
    assert run.product.received.total() == 0
    assert run.product.spec == run.contract.spec
    assert run.feed.stock.total() == pytest.approx(run.contract.feed.total())
    assert run.restarts_left == RESTARTS
    assert run.offspec_total == 0
