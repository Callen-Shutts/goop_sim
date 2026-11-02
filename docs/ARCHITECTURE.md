# Architecture

Python 3.11, pygame-ce. Package in `src/goop_sim/`, installed editable into `.venv`.

## Layers (dependencies point downward only)

```
scenes/   input handling, per-screen state, drawing order
  |
ui/       HMI look: theme.py (colors/sizes), geometry.py (rects, port positions, hit-test math), widgets.py (draw functions)
  |
content/  what a run can deal (random equipment)
  |
sim/      pure simulation, NO pygame import. Unit-tested.
```

`sim/` must stay free of pygame so it can be tested headlessly and reasoned about alone.

## sim/

- `equipment.py`: dataclasses, all `eq=False` (identity comparison, hashable).
  - `Equipment` base: `name`, `n_in`, `n_out` (port counts), `pos` (canvas center, `None` while in inventory), `fixed` (not draggable).
  - `Tank` (capacity_gal, diameter_ft, volume_gal; level_ft computed from diameter), `Pump` (max_gpm, running, flow_gpm), `Source` (unlimited supply, no in port), `Sink` (product outlet, no out port).
- `network.py`:
  - `Port(equipment, kind "in"|"out", index)`, `Pipe(out, into)`.
  - `Network` holds *placed* equipment and pipes, `produced_gal`, `target_gal`, `complete`.
  - `connect(a, b)` accepts either click order, rejects same-equipment, wrong kinds, already-used ports, equipment not on the canvas.
  - `step(dt)`: **pumps are the only things that move liquid.** A running pump with both pipes moves `max_gpm*dt/60`, limited by upstream tank volume and downstream tank free space. Liquid reaching a `Sink` adds to `produced_gal`. Pump-to-pump directly moves nothing (known limitation).

## content/

- `equipment.py`: `deal_hand(rng, size=6)` returns random pumps/tanks, always at least one pump. Takes a `random.Random` so runs are seedable.

## scenes/

- `base.py`: `Scene` interface (`handle_event`, `update(dt)`, `draw(surface)`).
- `play.py`: `PlayScene`. Owns `Network`, the `inventory` list (unplaced equipment), `pending` (first-clicked port while piping) and `drag` state. Fixed Source/Sink are placed at start. Inventory lives in the scene, placed equipment lives in the network; moving between them is done in `on_left_up`.

## game.py / main.py

`Game` owns the window, clock and current scene; `change_scene()` swaps scenes. `python -m goop_sim` -> `__main__.py` -> `main.main()`.

## Where things go next

- New equipment type: dataclass in `sim/equipment.py`, behavior in `Network.step`, size in `ui/geometry._SIZES`, drawing branch in `ui/widgets.draw_equipment`, card text in `widgets.describe`, add to the pool in `content/equipment.py`.
- Run structure (levels, rewards, draft, menu): new `run/` package plus new scenes. Not built.

## Tests

`tests/test_network.py` covers connection rules, flow, tank limits, production/completion, equipment removal, seeded dealing. Run `pytest` (config in `pyproject.toml`). UI is checked manually or by driving `PlayScene` with synthetic pygame events under `SDL_VIDEODRIVER=dummy`.
