# goop_sim

A 2D game built with Python and pygame-ce.

See `CLAUDE.md` and `docs/` for design, architecture and session logs.

## Concept

A roguelike chemical-engineering game with an HMI/SCADA-style interface. Each run
hands you random equipment (pumps, splitters, tanks, ...) and you wire up a process
that produces enough product.

## Controls

- Drag equipment from the right-hand panel onto the canvas; drag it back to the panel to remove it
- Click an out port, then an in port, to run a pipe between them (Esc or right-click cancels)
- Right-click a pipe to delete it
- Click a pump (without dragging) to start or stop it

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```
python -m goop_sim
```

## Test

```
pytest
```

## Layout

- `src/goop_sim/sim/` - pure simulation (equipment, ports, pipes, flow). No pygame; unit-testable
- `src/goop_sim/content/` - what a run can deal you (random equipment)
- `src/goop_sim/ui/` - HMI look: theme and drawing widgets (tanks, pumps, value boxes)
- `src/goop_sim/scenes/` - screens (play, later menu / equipment draft / run summary)
- `src/goop_sim/game.py` - window, main loop, scene switching
- `tests/` - pytest, mostly for `sim/`
