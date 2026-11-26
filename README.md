# goop_sim

A 2D game built with Python and pygame-ce.

See `CLAUDE.md` and `docs/` for design, architecture and session logs.

## Concept

A roguelike chemical-engineering game with an HMI/SCADA-style interface. Each run
rolls its own reaction stoichiometry (letters stay A, B, C...; waste is W) and deals random equipment (reactors,
columns, splitters, mixers, pumps, tanks). Build a plant that turns the feed into each
contract's products (up to three at once, each at its own purity, each into its own PRODUCT outlet), get paid (more for purer product, less for
off-spec and spills), spend it in the store, and keep extending the plant.

## Controls

- Drag equipment from the right-hand panel onto the canvas
- Send a unit back to the inventory: right-click it, press Delete/Backspace (selected unit, or the one under the mouse), use the faceplate's TO INV button, or drag it onto the panel (its pipes and contents are removed; settings are kept)
- Ctrl+Z undoes layout edits (place, move, pipe, remove); Ctrl+Y or Ctrl+Shift+Z redoes. Also UNDO/REDO softkeys
- T or the TIDY softkey auto-arranges the plant into tidy left-to-right columns (undoable)
- Click an out port, then an in port, to run a pipe between them (Esc or right-click cancels)
- Right-click a pipe to delete it
- Click a unit to open its faceplate: start/stop pumps, drag the setpoint slider, +/- buttons
- Mouse wheel over a pump or splitter (or arrow keys on the selected one) tunes it
- Hover anything for details (column splits, ratings, reactions, contents); hover a pipe to see its flow and composition
- Starts fullscreen: F11 toggles fullscreen, Ctrl+Q quits
- Space or RUN/PAUSE runs the plant live; F cycles speed 1x/4x/16x; RESTART restocks the feed
- PRODUCT only counts streams at spec purity; reactors and columns lose performance above their rated GPM
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
- `src/goop_sim/scenes/` - screens (play, store)
- `src/goop_sim/game.py` - window, main loop, scene switching
- `tests/` - pytest, mostly for `sim/`
