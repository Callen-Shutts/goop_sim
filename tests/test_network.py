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


def fixed_pump(name, gpm=60, **kw):
    """A pump fixed at `gpm` (range collapsed to one value)."""
    return Pump(name, min_gpm=gpm, max_gpm=gpm, **kw)


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
    src, pump, sink = feed(), fixed_pump("P"), Outlet("O")
    net = build(src, pump, sink)
    assert net.connect(Port(src, "out"), Port(pump, "in"))
    assert net.connect(Port(src, "out"), Port(sink, "in")) is None  # out port already used
    assert net.connect(Port(pump, "out"), Port(pump, "in")) is None  # same equipment
    assert net.connect(Port(src, "in"), Port(pump, "in")) is None  # two in ports
    assert net.connect(Port(sink, "in"), Port(pump, "out"))  # either click order


def test_removing_equipment_removes_its_pipes():
    src, pump = feed(), fixed_pump("P")
    net = build(src, pump)
    link(net, src, pump)
    net.remove(pump)
    assert net.pipes == []


# -- flow ---------------------------------------------------------------------


def test_pump_draws_feed_through_reactor_to_outlet():
    src, pump, reactor, out = feed(), fixed_pump("P", 60), Reactor("R", reaction=parse("A>B"), conversion=0.5), Outlet("O")
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
    src, pump = Feed("F", stock=Stream(A=50, B=50)), fixed_pump("P", 6000)
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


def test_splitter_ratio_tunes_in_steps_and_clamps():
    s = Splitter("S")
    s.nudge(3)
    assert s.ratio == pytest.approx(0.65)
    s.nudge(-20)
    assert s.ratio == 0.0
    s.set_ratio(1.7)
    assert s.ratio == 1.0
    s.set_ratio(0.33)
    assert s.ratio == pytest.approx(0.35)


def test_pump_setpoint_starts_mid_range_and_clamps():
    p = Pump("P", min_gpm=50, max_gpm=300)
    assert p.setpoint_gpm == 175
    assert p.step_gpm == 10
    p.nudge(100)
    assert p.setpoint_gpm == 300
    p.set_setpoint(0)
    assert p.setpoint_gpm == 50


def test_pump_draws_its_setpoint():
    src, p, out = feed(), Pump("P", min_gpm=10, max_gpm=600, setpoint_gpm=120), Outlet("O")
    net = build(src, p, out)
    link(net, src, p)
    link(net, p, out)
    net.step(60)
    assert out.received["A"] == pytest.approx(120)
    p.set_setpoint(30)
    net.step(60)
    assert out.received["A"] == pytest.approx(150)


def test_overloaded_reactor_converts_less():
    r = Reactor("R", reaction=parse("A>B"), conversion=0.8, rated_gpm=100)
    assert r.effective_conversion(100) == pytest.approx(0.8)
    assert r.effective_conversion(200) < 0.8 * 0.6
    src, p, out = feed(), Pump("P", min_gpm=10, max_gpm=600, setpoint_gpm=200), Outlet("O")
    net = build(src, p, r, out)
    link(net, src, p)
    link(net, p, r)
    link(net, r, out)
    net.step(60)
    assert r.load_gpm == pytest.approx(200)
    assert out.received["B"] < 0.8 * 200 * 0.6


def test_flooded_column_smears_toward_half():
    c = Separator("C", top={"A": 0.9, "B": 0.1}, rated_gpm=100)
    assert c.effective_top(50) == pytest.approx({"A": 0.9, "B": 0.1})
    assert c.effective_top(200) == pytest.approx({"A": 0.7, "B": 0.3})
    top, bottom = c.split(Stream(A=10, B=10), 200)
    assert top == pytest.approx({"A": 7, "B": 3})


def test_outlet_grades_each_stream_against_spec():
    out = Outlet("O", spec=("B", 0.8))
    out.take_in(Stream(B=90, A=10))
    out.take_in(Stream(B=50, A=50))
    assert out.accepted == pytest.approx({"B": 90})
    assert out.rejected_gal == pytest.approx(100)
    assert out.received.total() == pytest.approx(200)
    out.reset()
    assert out.accepted.total() == 0 and out.rejected_gal == 0


def test_mixer_joins_streams():
    f1, f2 = feed(100), Feed("G", stock=Stream(B=100))
    p1, p2, mix, out = fixed_pump("P1", 60), fixed_pump("P2", 60), Mixer("M"), Outlet("O")
    net = build(f1, f2, p1, p2, mix, out)
    link(net, f1, p1)
    link(net, f2, p2)
    link(net, p1, mix, into=0)
    link(net, p2, mix, into=1)
    link(net, mix, out)
    net.step(1)
    assert out.received == pytest.approx({"A": 1, "B": 1})


def test_full_tank_spills_the_excess():
    src, pump, tank = feed(), fixed_pump("P", 600), Tank("T", capacity_gal=4)
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1)  # 10 gal into a 4 gal tank
    assert tank.volume_gal == pytest.approx(4)
    assert net.spilled_gal == pytest.approx(6)


def test_open_port_and_stopped_pump_spill():
    src, p1, reactor, p2 = feed(), fixed_pump("P1", 60), Reactor("R", reaction=parse("A>B")), fixed_pump("P2", running=False)
    net = build(src, p1, reactor, p2)
    link(net, src, p1)
    link(net, p1, reactor)
    net.step(1)
    assert net.spilled_gal == pytest.approx(1)  # reactor outlet is open
    link(net, reactor, p2)
    net.step(1)
    assert net.spilled_gal == pytest.approx(2)  # stopped pump blocks


def test_pump_without_outlet_draws_nothing():
    src, pump = feed(), fixed_pump("P")
    net = build(src, pump)
    link(net, src, pump)
    net.step(1)
    assert src.stock["A"] == 1000
    assert pump.flow_gpm == 0


def test_loop_without_tank_spills_instead_of_hanging():
    src, pump, mix, reactor = feed(), fixed_pump("P", 60), Mixer("M"), Reactor("R", reaction=parse("A>B"))
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
        p1, tank, p2 = fixed_pump("P1", 600), Tank("T", capacity_gal=5000), fixed_pump("P2", 600)
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


def test_streams_from_different_pumps_mix_before_reacting():
    """Pure Z and pure K from two pumps meet at a mixer; the K+Z reactor must see them together."""
    tz, tk = Tank("TZ", capacity_gal=5000), Tank("TK", capacity_gal=5000)
    tz.content = Stream(Z=1000.0)
    tk.content = Stream(K=1000.0)
    pz, pk = fixed_pump("PZ", 60), fixed_pump("PK", 60)
    mix, boost = Mixer("M"), fixed_pump("PB", 60)
    reactor = Reactor("R", reaction=parse("K+Z>T"), conversion=0.5, rated_gpm=500)
    out = Outlet("O")
    net = build(tz, tk, pz, pk, mix, boost, reactor, out)
    link(net, tz, pz)
    link(net, tk, pk)
    link(net, pz, mix, into=0)
    link(net, pk, mix, into=1)
    link(net, mix, boost)
    link(net, boost, reactor)
    link(net, reactor, out)
    net.step(1)  # 1 gal of each
    assert out.received["T"] == pytest.approx(0.5)
    assert out.received["Z"] == pytest.approx(0.5)
    assert reactor.load_gpm == pytest.approx(120)  # both pumps' flow counts toward the rating
    assert boost.flow_gpm == pytest.approx(120)


# -- holdup: pipes and reactors take time to fill ------------------------------


def test_pipe_is_plug_flow():
    a, b = fixed_pump("A"), fixed_pump("B")
    a.pos, b.pos = (0, 0), (100, 0)
    net = build(a, b)
    pipe = link(net, a, b)
    cap = pipe.capacity_gal
    assert cap > 0
    first = pipe.push(Stream(A=cap * 0.6))
    assert first.total() == 0 and pipe.fill == pytest.approx(0.6)
    out = pipe.push(Stream(B=cap * 0.6))  # fills it; 0.2 of the A leaves the far end first
    assert out["A"] == pytest.approx(cap * 0.2) and "B" not in out
    out = pipe.push(Stream(B=cap * 0.5))  # rest of the A, then some B
    assert out["A"] == pytest.approx(cap * 0.4) and out["B"] == pytest.approx(cap * 0.1)


def test_placed_plant_takes_time_to_deliver():
    src, pump, out = feed(), fixed_pump("P", 60), Outlet("O")
    src.pos, pump.pos, out.pos = (0, 0), (200, 0), (400, 0)
    net = build(src, pump, out)
    link(net, src, pump)
    link(net, pump, out)
    hold = sum(p.capacity_gal for p in net.pipes)
    net.step(hold * 60 / 60 * 0.9)  # not enough to fill both pipes
    assert out.received.total() == 0
    for _ in range(10):
        net.step(1)
    assert out.received.total() > 0


def test_reactor_holds_liquid_then_overflows_at_listed_conversion():
    src, pump, out = feed(10_000), fixed_pump("P", 60), Outlet("O")
    reactor = Reactor("R", reaction=parse("A>B"), conversion=0.6, rated_gpm=500, volume_gal=100)
    net = build(src, pump, reactor, out)
    link(net, src, pump)
    link(net, pump, reactor)
    link(net, reactor, out)
    for _ in range(90):  # 90 gal in at 1 gal/s
        net.step(1)
    assert out.received.total() == 0 and reactor.level == pytest.approx(0.9)
    for _ in range(1000):
        net.step(1)
    out.reset()
    net.step(1)
    assert out.inflow.total() == pytest.approx(1)
    assert out.inflow["B"] == pytest.approx(0.6, abs=0.02)


def test_reactants_arriving_at_different_times_still_react_in_the_vessel():
    reactor = Reactor("R", reaction=parse("K+Z>T"), conversion=0.8, rated_gpm=500, volume_gal=100)
    reactor.run(Stream(Z=50.0), 60, 1)
    reactor.run(Stream(K=50.0), 60, 1)
    for _ in range(20):
        reactor.run(Stream(), 60, 1)  # keeps reacting while stirred at that rate
    assert reactor.content.get("T", 0) > 5


def test_restart_empties_pipes_and_reactors():
    from goop_sim.run.state import RunState

    run = RunState(seed=3)
    reactor = next(eq for eq in run.inventory if isinstance(eq, Reactor))
    run.inventory.remove(reactor)
    reactor.pos = (300, 300)
    run.net.add(reactor)
    run.feed.pos = (80, 300)
    pipe = run.net.connect(Port(run.feed, "out"), Port(reactor, "in"))
    pipe.push(Stream(A=5.0))
    reactor.content = Stream(A=50.0)
    run.restart()
    assert pipe.held_gal == 0 and reactor.content.total() == 0


def test_spills_are_tracked_where_they_happen():
    src, pump, col, stopped = feed(), fixed_pump("P", 60), Separator("C", top={"A": 0.5}), fixed_pump("S", running=False)
    net = build(src, pump, col, stopped)
    link(net, src, pump)
    link(net, pump, col)
    link(net, col, stopped, out=1)  # top left open; bottom into a stopped pump
    net.step(1)
    top = Port(col, "out", 0)
    assert net.spills[top].total() == pytest.approx(0.5)
    assert net.spills[stopped].total() == pytest.approx(0.5)
    assert net.spill_reason(top) == "OUTLET NOT PIPED" and net.spill_reason(stopped) == "PUMP STOPPED"
    assert net.spilled_by(col) == pytest.approx(0.5) and net.spilled_gal == pytest.approx(1)
    net.step(1)
    assert net.spilled_by(col) == pytest.approx(1.0)  # totals accumulate; last-step dict is fresh
    net.clear_spills()
    assert net.spilled_gal == 0 and not net.spills and not net.spill_totals


def test_full_tank_spill_is_on_the_tank():
    src, pump, tank = feed(), fixed_pump("P", 60), Tank("T", capacity_gal=0.4)
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1)
    assert net.spills[tank].total() == pytest.approx(0.6)
    assert net.spill_reason(tank) == "TANK FULL"
