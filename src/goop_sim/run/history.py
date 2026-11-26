"""Undo/redo for plant layout edits (place, move, pipe, unpipe, return to inventory).

Only the layout is restored: which units are placed and where, the pipes, and the inventory
order. Process state (tank contents, flows) is not rewound; a unit that goes back to the
inventory is emptied, as it would be by hand.
"""

from goop_sim.run.state import RunState

LIMIT = 100


class History:
    def __init__(self, run: RunState, limit: int = LIMIT):
        self.run = run
        self.limit = limit
        self.undo_stack: list = []
        self.redo_stack: list = []

    def snapshot(self):
        net = self.run.net
        return ([(eq, eq.pos) for eq in net.equipment], list(net.pipes), list(self.run.inventory))

    def push(self, snap) -> None:
        """Record `snap` (taken just before an edit) as an undo point."""
        self.undo_stack.append(snap)
        del self.undo_stack[: -self.limit]
        self.redo_stack.clear()

    def record(self) -> None:
        self.push(self.snapshot())

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.snapshot())
        self._restore(self.undo_stack.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.snapshot())
        self._restore(self.redo_stack.pop())
        return True

    def _restore(self, snap) -> None:
        placed, pipes, inventory = snap
        net = self.run.net
        was_placed = set(net.equipment)
        net.equipment = [eq for eq, _pos in placed]
        for eq, pos in placed:
            eq.pos = pos
        net.pipes = list(pipes)
        self.run.inventory[:] = inventory
        for eq in inventory:
            if eq in was_placed:
                eq.reset()
            eq.pos = None
