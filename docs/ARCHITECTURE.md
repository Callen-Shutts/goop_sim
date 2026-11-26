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
- `equipment.py`: dataclasses, all `eq=False` (identity comparison, hashable). Base `Equipment` (`name`, `n_in`, `n_out`, `pos`, `fixed`, `reset()`). `Feed` (stock), `Outlet` (received; with a `spec` it grades each arriving stream into `accepted` or `rejected_gal`; `inflow` = last step), `Tank` (content, capacity), `Pump` (min/max range, `setpoint_gpm`, `nudge`, running, flow_gpm), `Reactor` (reaction, conversion, `rated_gpm`, `load_gpm`, optional side reaction; `effective_conversion(gpm)`), `Separator` (`top[species]` share to out 0, `rated_gpm`, `effective_top(gpm)` smears toward 0.5 when overloaded), `Splitter` (ratio to out 0, `set_ratio`/`nudge` in 5% steps), `Mixer` (2 in).
- `network.py`: `Port`, `Pipe` (`carried` = what flowed last step, for drawing), `Network` (connect rules, `step(dt)`, `last_dt`).
  - **Flow model:** each running pump whose inlet is piped straight from a `Feed` or `Tank` draws `setpoint_gpm*dt/60` from it and pushes it downstream. The push passes instantly through reactors, separators, splitters, mixers and running pumps until it lands in a tank or outlet; reactors and columns see that push's GPM and lose performance above their rating. Open ports, full tanks, stopped pumps and tank-less loops (depth > `MAX_DEPTH`) spill; `spilled_gal` tracks it. Recycle loops therefore need a tank.

## content/

- `equipment.py`: `Namer` (P101, TK101, R101, C101, SP101, MX101), `make_*` per type, `starting_hand`, `level_grant` (free reactor for the new reaction), `draft_options`. All take the run's `random.Random`.

## run/

- `contract.py`: `Contract` (species, quantity, purity, feed `Stream`, `spec`, `check(outlet)` on accepted product), `make_contract(level, chem, rng)` with the scaling rules.
- `state.py`: `RunState` owns the seed/rng, chemistry, `Network` (with fixed FEED/PRODUCT/WASTE), `inventory`, `level`, `contract`, `restarts_left`. Sets PRODUCT's spec per contract. `met`, `feed_empty`, `restart()` (restock, empty, keep layout/settings), `draft_options()`/`next_grant()`/`advance()`.

## scenes/

- `base.py`: `Scene` interface (`handle_event`, `update(dt)`, `draw(surface)`).
- `play.py`: `PlayScene(game, run)`. `running` flag plus a `result` overlay; editing is always allowed. Layout: header (contract + progress bar), canvas with dot grid, right panel (scrollable `INVENTORY` cards with icons, `FACEPLATE` for the selected unit), bottom softkeys (RUN/PAUSE, SPEED 1/4/16x, RESTART). `self.controls` is a list of `(rect, on_click, on_drag)` rebuilt every `draw()` (softkeys, faceplate buttons/sliders); clicks check it first. Runs the sim at `SIM_SPEED` sim-seconds per real second times the speed, in substeps; shows the result as soon as `run.met`, or "out of feed" after `IDLE_END` idle seconds with an empty feed. `pipe_memory` keeps idle pipes tinted. `return_to_inventory(eq)` is the single path for taking a unit off the canvas (right-click, Delete/Backspace, faceplate key, drag to panel).
- `draft.py`: `DraftScene(game, run)`. Big icon cards; pick `DRAFT_PICKS`, then `run.advance()` and back to a new `PlayScene`.

## ui/

- `theme.py`: dark DCS palette, `SPECIES` colors, layout sizes.
- `geometry.py`: `_SIZES`, `rect_of`, `fit_rect` (icons), ports, `pipe_points(pipe, lane)` (forward = Z route, backward = loop under both units; `lane` shifts the free legs), `lay_out_pipes` (first lane whose free legs don't overlap earlier pipes), `route_pipes` (laid-out paths plus line-jump arcs where a horizontal run crosses another pipe's vertical run; returns `{pipe: (path, hops)}`), hit-testing, `snap`. The play scene draws and hit-tests pipes from `route_pipes`, then redraws hop arcs on top.
- `widgets.py`: `blend(stream)` color mixing, cached shaded `_cylinder` bodies, `draw_body` (symbol only; reused at icon size by `draw_icon`), `draw_equipment` (symbol + tags + value boxes + ports), `draw_pipe` (wall, contents color, moving dots), cards, tooltips, frames, buttons, bars, `describe`/`details` text.

## game.py / main.py

`Game` owns the window, clock and current scene; `new_run(seed)` makes a `RunState` and `PlayScene`; `change_scene()` swaps scenes. The window is opened with `pygame.SCALED` (+ `FULLSCREEN` per `settings.FULLSCREEN`, else `RESIZABLE`) so all layout stays in 1280x720 logical pixels and mouse events are mapped automatically; F11 toggles fullscreen, Ctrl+Q quits. Falls back to a plain window if the driver can't scale (headless). `python -m goop_sim` -> `__main__.py` -> `main.main()`.

## Where things go next

- New equipment type: dataclass in `sim/equipment.py`, routing branch in `Network._deliver`, size in `ui/geometry._SIZES`, drawing branch in `ui/widgets.draw_equipment`, `describe`/`details` text, a `make_*` + weight in `content/equipment.py`.
- New reaction templates: `STEP_TEMPLATES` in `sim/chemistry.py` (each step may only use species made by earlier steps; the test enforces this).
- Contract rules: `run/contract.py`.

## Tests

`tests/test_network.py` covers streams, reactions, connection rules, routing through every unit, pump setpoints, splitter tuning, overload effects, outlet grading, spills, tank-less loops and a recycle-through-tank plant. `tests/test_geometry.py` covers line jumps and lane separation. `tests/test_run.py` covers chemistry generation, dealing (incl. pump ranges), grants/draft, contract escalation and on-spec checks, restarts, and plant/settings persistence across contracts. Run `pytest`. UI is checked by driving the scenes with synthetic pygame events under `SDL_VIDEODRIVER=dummy` and saving screenshots.
