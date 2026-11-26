# goop_sim

A 2D game built with Python and pygame-ce.

See `CLAUDE.md` and `docs/` for design, architecture and session logs.

## Concept

A roguelike chemical-engineering game with an HMI/SCADA-style interface. Each run
rolls a random reaction chain and deals random equipment (reactors, columns, splitters,
mixers, pumps, tanks). Build a plant that turns the feed into each contract's product
at the required purity, then keep extending it as contracts escalate.

## Controls

- Drag equipment from the right-hand panel onto the canvas; drag it back to the panel to remove it
- Click an out port, then an in port, to run a pipe between them (Esc or right-click cancels)
- Right-click a pipe to delete it
- Click a pump to start/stop it, click a splitter to change its split
- Hover anything for details (column splits, reactions, contents)
- Space or RUN to process the feed; F cycles speed 1x/4x/16x; STOP scores early
- Recycle loops need a tank in them; liquid with nowhere to go is spilled

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

- `src/goop_sim/sim/` - pure simulation (streams, reactions, equipment, pipes, flow). No pygame; unit-testable
- `src/goop_sim/content/` - what a run can deal you (random equipment)
- `src/goop_sim/run/` - one roguelike run: contracts, attempts, progression
- `src/goop_sim/ui/` - HMI look: theme and drawing widgets (tanks, pumps, value boxes)
- `src/goop_sim/scenes/` - screens (play, draft)
- `src/goop_sim/game.py` - window, main loop, scene switching
- `tests/` - pytest, mostly for `sim/`
