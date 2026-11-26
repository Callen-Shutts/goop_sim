import pytest

from goop_sim.sim.equipment import Mixer, Outlet, Pump
from goop_sim.sim.network import Network, Port
from goop_sim.ui.geometry import HOP_RADIUS, LANE, route_pipes


def placed(eq, pos):
    eq.pos = pos
    return eq


def test_horizontal_run_jumps_over_crossing_vertical():
    # Pumps have centered ports (width 40). Pipe 1 runs straight along y=300 from x=120 to 680.
    # Pipe 2 runs (320,100) -> (500,500), so its vertical leg is at x=410 from y=100 to 500.
    a, b = placed(Pump("A"), (100, 300)), placed(Pump("B"), (700, 300))
    c, d = placed(Pump("C"), (300, 100)), placed(Pump("D"), (520, 500))
    net = Network()
    for eq in (a, b, c, d):
        net.add(eq)
    flat = net.connect(Port(a, "out"), Port(b, "in"))
    tall = net.connect(Port(c, "out"), Port(d, "in"))
    routes = route_pipes(net.pipes)

    path, hops = routes[flat]
    assert len(hops) == 1
    xs = [p[0] for p in hops[0]]
    assert min(xs) == pytest.approx(410 - HOP_RADIUS) and max(xs) == pytest.approx(410 + HOP_RADIUS)
    assert min(p[1] for p in hops[0]) < 300  # arcs up over the other pipe
    assert routes[tall][1] == []  # the vertical pipe does not jump


def test_parallel_pipes_get_separate_lanes():
    # Two forward pipes whose middle legs would land on the same x.
    a, b = placed(Pump("A"), (100, 200)), placed(Pump("B"), (700, 400))
    c, d = placed(Pump("C"), (100, 260)), placed(Pump("D"), (700, 460))
    net = Network()
    for eq in (a, b, c, d):
        net.add(eq)
    p1 = net.connect(Port(a, "out"), Port(b, "in"))
    p2 = net.connect(Port(c, "out"), Port(d, "in"))
    routes = route_pipes(net.pipes)
    leg = lambda pipe: next(x1 for (x1, y1), (x2, y2) in zip(routes[pipe][0], routes[pipe][0][1:]) if x1 == x2 and y1 != y2)
    assert abs(leg(p1) - leg(p2)) >= LANE


def test_no_jumps_without_crossings():
    a, b = placed(Mixer("A"), (100, 300)), placed(Outlet("B"), (700, 300))
    net = Network()
    net.add(a)
    net.add(b)
    pipe = net.connect(Port(a, "out"), Port(b, "in"))
    path, hops = route_pipes(net.pipes)[pipe]
    assert hops == []
    assert path[0][0] < path[-1][0]
