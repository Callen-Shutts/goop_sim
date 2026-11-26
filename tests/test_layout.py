import random

import pygame

from goop_sim.sim.equipment import Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.chemistry import parse
from goop_sim.sim.network import Network, Port
from goop_sim.ui.geometry import port_pos, rect_of
from goop_sim.ui.layout import tidy

AREA = pygame.Rect(20, 60, 1000, 572)


def plant(*units):
    net = Network()
    feed = Feed("FEED", pos=(80, 340))
    product = Outlet("PRODUCT", pos=(960, 220))
    waste = Outlet("WASTE", n_in=3, pos=(960, 460))
    for eq in (feed, product, waste, *units):
        net.add(eq)
    return net, feed, product, waste


def apply(net, keep_out=()):
    moves = tidy(net, AREA, list(keep_out))
    for eq, pos in moves.items():
        eq.pos = pos
    return moves


def test_series_chain_is_straight_and_left_to_right():
    tank, pump, reactor = Tank("TK", pos=(500, 600)), Pump("P", pos=(100, 100)), Reactor("R", reaction=parse("A>B"), pos=(300, 500))
    net, feed, product, _waste = plant(tank, pump, reactor)
    net.connect(Port(feed, "out"), Port(tank, "in"))
    net.connect(Port(tank, "out"), Port(pump, "in"))
    net.connect(Port(pump, "out"), Port(reactor, "in"))
    net.connect(Port(reactor, "out"), Port(product, "in"))
    apply(net)
    assert feed.pos[0] < tank.pos[0] < pump.pos[0] < reactor.pos[0] < product.pos[0]
    # Each inline unit's in port lines up with the out port feeding it.
    for pipe in net.pipes[:3]:
        assert port_pos(pipe.out)[1] == port_pos(pipe.into)[1]


def test_recycle_keeps_flow_direction_and_fixed_units_stay():
    tank, pump, column, split = Tank("TK"), Pump("P"), Separator("C", top={"A": 0.9}), Splitter("SP")
    for i, eq in enumerate((split, column, pump, tank)):
        eq.pos = (200 + 150 * i, 300)  # placed backwards
    net, feed, product, waste = plant(tank, pump, column, split)
    fixed_before = {eq: eq.pos for eq in (feed, product, waste)}
    net.connect(Port(feed, "out"), Port(tank, "in", 0))
    net.connect(Port(tank, "out"), Port(pump, "in"))
    net.connect(Port(pump, "out"), Port(column, "in"))
    net.connect(Port(column, "out", 0), Port(product, "in"))
    net.connect(Port(column, "out", 1), Port(split, "in"))
    net.connect(Port(split, "out", 0), Port(tank, "in", 1))  # recycle
    net.connect(Port(split, "out", 1), Port(waste, "in"))
    moves = apply(net)
    assert all(eq not in moves for eq in fixed_before)
    assert {eq: eq.pos for eq in fixed_before} == fixed_before
    assert tank.pos[0] < pump.pos[0] < column.pos[0] < split.pos[0]


def test_unpiped_units_are_parked_at_the_top():
    loose = Mixer("MX", pos=(500, 500))
    net, *_ = plant(loose)
    apply(net)
    assert rect_of(loose).top < AREA.top + 40


def test_random_tangles_do_not_overlap_and_avoid_keep_out():
    legend = pygame.Rect(10, 520, 240, 102)
    for seed in range(40):
        rng = random.Random(seed)
        kinds = [Tank, Pump, Pump, Reactor, Separator, Splitter, Mixer, Pump]
        units = []
        for i, cls in enumerate(rng.sample(kinds, rng.randint(3, len(kinds)))):
            kw = {"reaction": parse("A>B")} if cls is Reactor else {"top": {"A": 0.9}} if cls is Separator else {}
            units.append(cls(f"U{i}", pos=(rng.randint(100, 900), rng.randint(100, 600)), **kw))
        net, feed, product, waste = plant(*units)
        outs = [Port(eq, "out", i) for eq in [feed, *units] for i in range(eq.n_out)]
        ins = [Port(eq, "in", i) for eq in [product, waste, *units] for i in range(eq.n_in)]
        rng.shuffle(outs)
        for out in outs:
            if rng.random() < 0.8:
                net.connect(out, rng.choice(ins))
        apply(net, [legend])
        rects = [rect_of(eq) for eq in net.equipment]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                assert not a.colliderect(b), seed
        for eq in units:
            assert AREA.left <= rect_of(eq).left and rect_of(eq).right <= AREA.right, seed
            assert not rect_of(eq).colliderect(legend), seed
