# Architecture

Python 3.11+ (venv uses 3.12), pygame-ce. Package in `src/goop_sim/`, installed editable into `.venv`.

## Layers (dependencies point downward only)

```
scenes/   input handling, per-screen state, drawing order
  |
ui/       HMI look: theme.py (colors/sizes), geometry.py (rects, port positions, pipe routing, hit-test math), widgets.py (draw functions, card/tooltip text)
  |
run/      one roguelike run: contracts, attempts, progression. No pygame.
  |
content/  what a run can deal (random equipment cards)
  |
sim/      pure simulation, NO pygame import. Unit-tested.
```

`sim/`, `content/` and `run/` stay free of pygame so they can be tested headlessly.

## sim/

- `stream.py`: `Stream`, a `dict` of species -> gallons with `total`, `take` (remove keeping composition), `scaled`, `add`, `fraction`, `dominant`.
- `chemistry.py`: `Reaction` (reactant/product coefficient dicts, `apply(stream, conversion)` on the limiting reactant, `label`), `parse("A+B>C")`, `STEP_TEMPLATES`, `Chemistry` (the run's `chain`; `target(level)`, `known(level)`), `generate_chemistry(rng)`, `side_reaction_for`.
- `equipment.py`: dataclasses, all `eq=False` (identity comparison, hashable). Base `Equipment` (`name`, `n_in`, `n_out`, `pos`, `fixed`, `reset()`). `Feed` (stock), `Outlet` (received), `Tank` (content, capacity), `Pump` (max_gpm, running, flow_gpm), `Reactor` (reaction, conversion, optional side reaction), `Separator` (`top[species]` share to out 0), `Splitter` (ratio to out 0, `cycle()`), `Mixer` (2 in).
- `network.py`: `Port`, `Pipe` (`carried` = what flowed last step, for drawing), `Network` (connect rules, `step(dt)`).
  - **Flow model:** each running pump whose inlet is piped straight from a `Feed` or `Tank` draws `max_gpm*dt/60` from it and pushes it downstream. The push passes instantly through reactors, separators, splitters, mixers and running pumps until it lands in a tank or outlet. Open ports, full tanks, stopped pumps and tank-less loops (depth > `MAX_DEPTH`) spill; `spilled_gal` tracks it. Recycle loops therefore need a tank.

## content/

- `equipment.py`: `Namer` (P101, TK101, R101, C101, SP101, MX101), `make_*` per type, `starting_hand`, `level_grant` (free reactor for the new reaction), `draft_options`. All take the run's `random.Random`.

## run/

- `contract.py`: `Contract` (species, quantity, purity, feed `Stream`, `check(received)`), `make_contract(level, chem, rng)` with the scaling rules.
- `state.py`: `RunState` owns the seed/rng, chemistry, `Network` (with fixed FEED/PRODUCT/WASTE), `inventory`, `level`, `contract`, `attempts_left`, `over`. `reset_plant()` restocks for an attempt, `finish_attempt()` scores, `draft_options()`/`next_grant()`/`advance()` move to the next contract keeping the plant.

## scenes/

- `base.py`: `Scene` interface (`handle_event`, `update(dt)`, `draw(surface)`).
- `play.py`: `PlayScene(game, run)`. Modes `build` / `running` / `result`. Places fixtures the first time. Runs the sim at `SIM_SPEED` sim-seconds per real second times the speed setting (1/4/16x, F key), in substeps; an attempt ends on STOP or after `IDLE_END` real seconds with no flow. Result overlay leads to the draft, back to build, or a new run.
- `draft.py`: `DraftScene(game, run)`. Pick `DRAFT_PICKS` cards, then `run.advance()` and back to a new `PlayScene`.

## game.py / main.py

`Game` owns the window, clock and current scene; `new_run(seed)` makes a `RunState` and `PlayScene`; `change_scene()` swaps scenes. `python -m goop_sim` -> `__main__.py` -> `main.main()`.

## Where things go next

- New equipment type: dataclass in `sim/equipment.py`, routing branch in `Network._deliver`, size in `ui/geometry._SIZES`, drawing branch in `ui/widgets.draw_equipment`, `describe`/`details` text, a `make_*` + weight in `content/equipment.py`.
- New reaction templates: `STEP_TEMPLATES` in `sim/chemistry.py` (each step may only use species made by earlier steps; the test enforces this).
- Contract rules: `run/contract.py`.

## Tests

`tests/test_network.py` covers streams, reactions, connection rules, routing through every unit, spills, tank-less loops and a recycle-through-tank plant. `tests/test_run.py` covers chemistry generation, dealing, grants/draft, contract escalation and checks, attempts, and plant persistence across contracts. Run `pytest`. UI is checked by driving the scenes with synthetic pygame events under `SDL_VIDEODRIVER=dummy` and saving screenshots.
