from goop_sim.run.history import History
from goop_sim.run.state import RunState
from goop_sim.sim.equipment import Pump, Tank
from goop_sim.sim.network import Port
from goop_sim.sim.stream import Stream


def place(run, eq, pos):
    run.inventory.remove(eq)
    run.net.add(eq)
    eq.pos = pos


def first(run, kind):
    return next(e for e in run.inventory if isinstance(e, kind))


def test_undo_and_redo_place_pipe_and_move():
    run = RunState(seed=5)
    hist = History(run)
    pump = first(run, Pump)

    hist.record()
    place(run, pump, (200, 300))
    hist.record()
    pipe = run.net.connect(Port(run.feed, "out"), Port(pump, "in"))
    hist.record()
    pump.pos = (260, 300)

    assert hist.undo()  # move
    assert pump.pos == (200, 300)
    assert hist.undo()  # pipe
    assert run.net.pipes == []
    assert hist.undo()  # place
    assert pump in run.inventory and pump not in run.net.equipment and pump.pos is None
    assert not hist.undo()

    assert hist.redo() and pump in run.net.equipment and pump.pos == (200, 300)
    assert hist.redo() and run.net.pipes == [pipe]
    assert hist.redo() and pump.pos == (260, 300)
    assert not hist.redo()


def test_undo_brings_removed_unit_back_with_its_pipes_but_empty():
    run = RunState(seed=5)
    hist = History(run)
    tank = first(run, Tank)
    place(run, tank, (300, 300))
    run.net.connect(Port(run.feed, "out"), Port(tank, "in"))
    tank.content.add({"A": 500})

    hist.record()
    run.net.remove(tank)
    tank.pos = None
    tank.reset()
    run.inventory.append(tank)

    assert hist.undo()
    assert tank in run.net.equipment and tank.pos == (300, 300)
    assert len(run.net.pipes) == 1
    assert tank.volume_gal == 0


def test_undo_of_placement_empties_the_unit():
    run = RunState(seed=5)
    hist = History(run)
    tank = first(run, Tank)
    hist.record()
    place(run, tank, (300, 300))
    tank.content = Stream(A=100)
    hist.undo()
    assert tank in run.inventory and tank.volume_gal == 0


def test_new_edit_clears_redo_and_limit_applies():
    run = RunState(seed=5)
    hist = History(run, limit=3)
    for _ in range(5):
        hist.record()
    assert len(hist.undo_stack) == 3
    hist.undo()
    assert hist.redo_stack
    hist.record()
    assert not hist.redo_stack
