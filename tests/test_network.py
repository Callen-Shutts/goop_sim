import random

from goop_sim.content.equipment import deal_hand
from goop_sim.sim.equipment import Pump, Sink, Source, Tank
from goop_sim.sim.network import Network, Port


def build(*equipment):
    net = Network(target_gal=100)
    for eq in equipment:
        net.add(eq)
    return net


def link(net, a, b):
    return net.connect(Port(a, "out"), Port(b, "in"))


def test_connect_rejects_invalid_pipes():
    src, pump, sink = Source("S"), Pump("P"), Sink("K")
    net = build(src, pump, sink)
    assert link(net, src, pump)
    assert link(net, src, sink) is None  # source out port already used
    assert net.connect(Port(pump, "out"), Port(pump, "in")) is None  # same equipment
    assert net.connect(Port(pump, "in"), Port(src, "out")) is None  # port already used
    assert net.connect(Port(src, "in"), Port(pump, "in")) is None  # source has no in port


def test_connect_accepts_either_click_order():
    pump, tank = Pump("P"), Tank("T")
    net = build(pump, tank)
    assert net.connect(Port(tank, "in"), Port(pump, "out"))


def test_pump_fills_tank_from_source():
    src, pump, tank = Source("S"), Pump("P", max_gpm=60, running=True), Tank("T")
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1.0)
    assert tank.volume_gal == 1.0
    assert pump.flow_gpm == 60


def test_unconnected_or_stopped_pump_moves_nothing():
    src, pump, tank = Source("S"), Pump("P", running=False), Tank("T")
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1.0)
    assert tank.volume_gal == 0
    pump.running = True
    net.disconnect(net.pipe_at(Port(pump, "out")))
    net.step(1.0)
    assert tank.volume_gal == 0


def test_pump_stops_at_full_tank():
    src, pump, tank = Source("S"), Pump("P", max_gpm=600, running=True), Tank("T", capacity_gal=10, volume_gal=10)
    net = build(src, pump, tank)
    link(net, src, pump)
    link(net, pump, tank)
    net.step(1.0)
    assert tank.volume_gal == 10
    assert pump.flow_gpm == 0


def test_full_chain_produces_and_completes():
    src, p1, tank, p2, sink = Source("S"), Pump("P1", max_gpm=6000, running=True), Tank("T"), Pump("P2", max_gpm=6000, running=True), Sink("K")
    net = build(src, p1, tank, p2, sink)
    for a, b in [(src, p1), (p1, tank), (tank, p2), (p2, sink)]:
        link(net, a, b)
    net.step(1.0)  # p1 fills tank 100 gal, p2 drains it to product
    assert net.produced_gal == 100
    assert net.complete


def test_removing_equipment_removes_its_pipes():
    src, pump = Source("S"), Pump("P")
    net = build(src, pump)
    link(net, src, pump)
    net.remove(pump)
    assert net.pipes == []


def test_deal_hand_has_a_pump_and_is_seeded():
    hand = deal_hand(random.Random(1))
    assert any(isinstance(e, Pump) for e in hand)
    again = deal_hand(random.Random(1))
    assert [(type(e), e.name) for e in hand] == [(type(e), e.name) for e in again]
