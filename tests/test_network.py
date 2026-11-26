import pytest

from goop_sim.sim.chemistry import parse
from goop_sim.sim.equipment import Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.network import Network, Port
from goop_sim.sim.stream import Stream


def build(*equipment):
    net = Network()
    for eq in equipment:
        net.add(eq)
    return net


def link(net, a, b, out=0, into=0):
    pipe = net.connect(Port(a, "out", out), Port(b, "in", into))
    assert pipe is not None
    return pipe


def feed(gal=1000, **extra):
    return Feed("F", stock=Stream({"A": gal, **extra}))


# -- streams and reactions --------------------------------------------------


def test_stream_take_keeps_composition():
    s = Stream(A=30, B=10)
    part = s.take(20)
    assert part == pytest.approx({"A": 15, "B": 5})
    assert s == pytest.approx({"A": 15, "B": 5})
    assert s.take(1000) == pytest.approx({"A": 15, "B": 5})
    assert s.total() == pytest.approx(0)


def test_reaction_uses_limiting_reactant():
    s = Stream(A=10, B=4)
    parse("A+B>C").apply(s, 0.5)  # limiting B=4 -> extent 2
    assert s == pytest.approx({"A": 8, "B": 2, "C": 2})


def test_reaction_coefficients_and_label():
    r = parse("2A>B")
    assert r.label == "2A → B"
    s = Stream(A=10)
    r.apply(s, 1.0)
    assert s == pytest.approx({"A": 0, "B": 5})


# -- connections ------------------------------------------------------------


def test_connect_rejects_invalid_pipes():
    src, pump, sink = feed(), Pump("P"), Outlet("O")
    net = build(src, pump, sink)
    assert net.connect(Port(src, "out"), Port(pump, "in"))
    assert net.connect(Port(src, "out"), Port(sink, "in")) is None  # out port already used
    assert net.connect(Port(pump, "out"), Port(pump, "in")) is None  # same equipment
    assert net.connect(Port(src, "in"), Port(pump, "in")) is None  # two in ports
    assert net.connect(Port(sink, "in"), Port(pump, "out"))  # either click order


def test_removing_equipment_removes_its_pipes():
    src, pump = feed(), Pump("P")
    net = build(src, pump)
    link(net, src, pump)
    net.remove(pump)
    assert net.pipes == []


# -- flow ---------------------------------------------------------------------


def test_pump_draws_feed_through_reactor_to_outlet():
    src, pump, reactor, out = feed(), Pump("P", max_gpm=60), Reactor("R", reaction=parse("A>B"), conversion=0.5), Outlet("O")
    net = build(src, pump, reactor, out)
    link(net, src, pump)
    link(net, pump, reactor)
    link(net, reactor, out)
    net.step(10)  # 60 gpm for 10 s = 10 gal
    assert out.received == pytest.approx({"A": 5, "B": 5})
    assert src.stock["A"] == pytest.approx(990)
    assert pump.flow_gpm == pytest.approx(60)
    assert net.moved_gal == pytest.approx(10)


def test_separator_and_splitter_route_by_fraction():
    src, pump = Feed("F", stock=Stream(A=50, B=50)), Pump("P", max_gpm=6000)
    sep = Separator("C", top={"A": 0.1, "B": 0.9})
    split = Splitter("S", ratio=0.25)
    top, purge, recycle = Outlet("T"), Outlet("U"), Outlet("V")
    net = build(src, pump, sep, split, top, purge, recycle)
    link(net, src, pump)
    link(net, pump, sep)
    link(net, sep, top, out=0)
    link(net, sep, split, out=1)
    link(net, split, purge, out=0)
    link(net, split, recycle, out=1)
    net.step(1)
    assert top.received == pytest.approx({"A": 5, "B": 45})
    assert purge.received == pytest.approx({"A": 11.25, "B": 1.25})
    assert recycle.received == pytest.approx({"A": 33.75, "B": 3.75})


def test_splitter_cycles_ratios():
    s = Splitter("S")
    seen = []
    for _ in range(3):
        s.cycle()
        seen.append(s.ratio)
    assert seen == [0.75, 0.25, 0.5]


def test_mixer_joins_streams():
    f1, f2 = feed(100), Feed("G", stock=Stream(B=100))
    p1, p2, mix, out = Pump("P1", max_gpm=60), Pump("P2", max_gpm=60), Mixer("M"), Outlet("O")
    net = build(f1, f2, p1, p2, mix, out)
    link(net, f1, p1)
    link(net, f2, p2)
    link(net, p1, mix, into=0)
    link(net, p2, mix, into=1)
    link(net, mix, out)
    net.step(1)
    assert out.received == pytest.approx({"A": 1, "B": 1})


def test_full_tank_spills_the_excess():
    src, pump, tank = feed(), Pump("P", max_gpm=600), Tank("T", capacity_gal=4)
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1)  # 10 gal into a 4 gal tank
    assert tank.volume_gal == pytest.approx(4)
    assert net.spilled_gal == pytest.approx(6)


def test_open_port_and_stopped_pump_spill():
    src, p1, reactor, p2 = feed(), Pump("P1", max_gpm=60), Reactor("R", reaction=parse("A>B")), Pump("P2", running=False)
    net = build(src, p1, reactor, p2)
    link(net, src, p1)
    link(net, p1, reactor)
    net.step(1)
    assert net.spilled_gal == pytest.approx(1)  # reactor outlet is open
    link(net, reactor, p2)
    net.step(1)
    assert net.spilled_gal == pytest.approx(2)  # stopped pump blocks


def test_pump_without_outlet_draws_nothing():
    src, pump = feed(), Pump("P")
    net = build(src, pump)
    link(net, src, pump)
    net.step(1)
    assert src.stock["A"] == 1000
    assert pump.flow_gpm == 0


def test_loop_without_tank_spills_instead_of_hanging():
    src, pump, mix, reactor = feed(), Pump("P", max_gpm=60), Mixer("M"), Reactor("R", reaction=parse("A>B"))
    net = build(src, pump, mix, reactor)
    link(net, src, pump)
    link(net, pump, mix, into=0)
    link(net, mix, reactor)
    link(net, reactor, mix, into=1)  # closed loop, no exit
    net.step(1)
    assert net.spilled_gal == pytest.approx(1)


def test_recycle_through_tank_beats_single_pass():
    """feed -> P1 -> tank -> P2 -> reactor -> separator: B top to product, A bottom back to the tank."""

    def plant(recycle):
        src = feed(1000)
        p1, tank, p2 = Pump("P1", max_gpm=600), Tank("T", capacity_gal=5000), Pump("P2", max_gpm=600)
        reactor = Reactor("R", reaction=parse("A>B"), conversion=0.5)
        sep = Separator("C", top={"A": 0.0, "B": 1.0})
        product, waste = Outlet("O"), Outlet("W")
        net = build(src, p1, tank, p2, reactor, sep, product, waste)
        link(net, src, p1)
        link(net, p1, tank)
        link(net, tank, p2)
        link(net, p2, reactor)
        link(net, reactor, sep)
        link(net, sep, product, out=0)
        if recycle:
            link(net, sep, tank, out=1, into=1)
        else:
            link(net, sep, waste, out=1)
        for _ in range(2000):
            net.step(1)
        return product, tank, net

    single, _, _ = plant(False)
    product, tank, net = plant(True)
    assert single.received["B"] == pytest.approx(500)
    assert product.received["B"] > 990
    assert product.received.total() + tank.volume_gal + net.spilled_gal == pytest.approx(1000)
