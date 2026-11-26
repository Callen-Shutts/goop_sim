import random

from goop_sim.content.equipment import Namer, draft_options, level_grant, make_pump, starting_hand
from goop_sim.run.contract import make_contract
from goop_sim.run.state import RESTARTS, RunState
from goop_sim.sim.chemistry import FEED_SPECIES, WASTE_SPECIES, generate_chemistry
from goop_sim.sim.equipment import Outlet, Pump, Reactor, Separator, Tank
from goop_sim.sim.stream import Stream


def test_chemistry_is_seeded_and_each_step_builds_on_earlier_species():
    for seed in range(30):
        chem = generate_chemistry(random.Random(seed))
        again = generate_chemistry(random.Random(seed))
        assert [r.label for r in chem.chain] == [r.label for r in again.chain]
        known = {FEED_SPECIES}
        for level, reaction in enumerate(chem.chain, start=1):
            assert set(reaction.reactants) <= known
            assert chem.target(level) not in known
            known |= set(reaction.products)
        assert chem.target(len(chem.chain) + 3) == chem.target(len(chem.chain))


def test_runs_differ_between_seeds():
    labels = {tuple(r.label for r in generate_chemistry(random.Random(s)).chain) for s in range(30)}
    assert len(labels) > 3


def test_starting_hand_can_make_the_first_product():
    chem = generate_chemistry(random.Random(4))
    hand = starting_hand(random.Random(4), chem, Namer())
    assert any(isinstance(e, Reactor) and e.reaction is chem.chain[0] for e in hand)
    assert sum(isinstance(e, Pump) for e in hand) >= 2
    assert any(isinstance(e, Separator) for e in hand)
    assert any(isinstance(e, Tank) for e in hand)
    assert len({e.name for e in hand}) == len(hand)


def test_dealt_pumps_have_a_tunable_range():
    rng, namer = random.Random(0), Namer()
    for _ in range(50):
        p = make_pump(rng, namer)
        assert 0 < p.min_gpm < p.max_gpm
        assert p.min_gpm <= p.setpoint_gpm <= p.max_gpm


def test_grant_gives_the_new_reaction_and_draft_only_known_reactions():
    rng = random.Random(2)
    chem = generate_chemistry(rng)
    namer = Namer()
    (reactor,) = level_grant(rng, chem, namer, 2)
    assert reactor.reaction is chem.chain[1]
    assert level_grant(rng, chem, namer, 1) == []
    assert level_grant(rng, chem, namer, len(chem.chain) + 1) == []
    for _ in range(20):
        for eq in draft_options(rng, chem, namer, 2):
            if isinstance(eq, Reactor):
                assert eq.reaction in chem.chain[:2]


def test_contracts_escalate():
    rng = random.Random(0)
    chem = generate_chemistry(rng)
    contracts = [make_contract(level, chem, rng) for level in range(1, 7)]
    assert [c.species for c in contracts[:3]] == [chem.target(1), chem.target(2), chem.target(3)]
    assert contracts[5].purity > contracts[2].purity
    assert contracts[5].feed.get(WASTE_SPECIES, 0) > 0
    assert contracts[0].feed.get(WASTE_SPECIES, 0) == 0


def test_contract_counts_only_on_spec_product():
    contract = make_contract(1, generate_chemistry(random.Random(0)), random.Random(0))
    sp, qty = contract.species, contract.quantity_gal
    out = Outlet("O", spec=contract.spec)
    out.take_in(Stream({sp: qty, "A": qty}))  # 50% pure: rejected
    assert not contract.check(out)
    out.take_in(Stream({sp: qty - 1}))
    assert not contract.check(out)
    out.take_in(Stream({sp: 1}))
    assert contract.check(out)


def test_run_sets_product_spec_and_meets_contract():
    run = RunState(seed=1)
    assert run.product.spec == run.contract.spec
    assert not run.met
    run.product.take_in(Stream({run.contract.species: run.contract.quantity_gal}))
    assert run.met


def test_restarts_restock_and_run_out():
    run = RunState(seed=1)
    run.feed.stock.take(1e9)
    assert run.feed_empty
    for _ in range(RESTARTS):
        assert run.restart()
        assert not run.feed_empty
        run.feed.stock.take(1e9)
    assert not run.restart()


def test_advance_keeps_the_plant_and_restocks():
    run = RunState(seed=3)
    pump = next(e for e in run.inventory if isinstance(e, Pump))
    run.inventory.remove(pump)
    pump.pos = (300, 300)
    pump.set_setpoint(pump.max_gpm)
    run.net.add(pump)
    run.feed.stock.take(5000)
    run.product.take_in(Stream({run.contract.species: 99}))

    grant, picks = run.next_grant(), run.draft_options()[:2]
    run.advance(picks, grant)

    assert run.level == 2
    assert pump in run.net.equipment
    assert pump.setpoint_gpm == pump.max_gpm  # settings carry over
    assert all(e in run.inventory for e in grant + picks)
    assert run.product.received.total() == 0
    assert run.product.spec == run.contract.spec
    assert run.feed.stock.total() == run.contract.feed.total()
    assert run.restarts_left == RESTARTS
