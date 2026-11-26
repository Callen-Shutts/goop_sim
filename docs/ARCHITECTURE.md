# Architecture

Python 3.11+ (venv uses 3.12), pygame-ce. Package in `src/goop_sim/`, installed editable into `.venv`.

## Layers (dependencies point downward only)

```
scenes/   input handling, per-screen state, drawing order
  |
ui/       HMI look: theme.py (colors/sizes), geometry.py (rects, port positions, pipe routing, hit-test math), widgets.py (draw functions, card/tooltip text)
  |
run/      one roguelike run: contracts, money, store, progression, undo history. No pygame.
  |
content/  what a run can deal (random equipment) and what it costs
  |
sim/      pure simulation, NO pygame import. Unit-tested.
```

`sim/`, `content/` and `run/` stay free of pygame so they can be tested headlessly.

## sim/

- `stream.py`: `Stream`, a `dict` of species -> gallons with `total`, `take` (remove keeping composition), `scaled`, `add`, `fraction`, `dominant`.
- `chemistry.py`: `Reaction` (reactant/product coefficient dicts, `apply(stream, conversion)` on the limiting reactant, `label`), `parse("A+B>C")`, `Chemistry` (`chain`, `feed` composition, `waste`; `species`/`all_species` in role order, `target(level)`, `known(level)`, `feed_per_gal(species)` stoichiometric feed cost used to size contracts), `generate_chemistry(rng)` (fixed letters: feed A or A+B, products C, D, ... in unlock order, waste `W`; random stoichiometry: 4 reactions, each after the first uses at least one earlier product, coefficients 1-3, reduced by their gcd when there are two reactants), `side_reaction_for(rng, main, waste)`. Nothing in `sim/` assumes particular letters.
- `equipment.py`: dataclasses, all `eq=False` (identity comparison, hashable). Base `Equipment` (`name`, `n_in`, `n_out`, `pos`, `fixed`, `reset()`). `Feed` (stock), `Outlet` (received; with a `spec` it grades each arriving stream into `accepted` (+`accepted_volume`, `accepted_purity`) or `rejected_gal`; `inflow` = last step), `Tank` (content, capacity), `Pump` (min/max range, `setpoint_gpm`, `nudge`, running, flow_gpm), `Reactor` (reaction, conversion, `rated_gpm`, `load_gpm`, optional side reaction; `effective_conversion(gpm)`; `volume_gal` + `content` make it a stirred vessel: `run(inflow, gpm, dt)` mixes inflow in, reacts the content with a rate chosen so steady running at `gpm` gives `effective_conversion(gpm)` (stirred-tank kinetics, k·τ/(1+k·τ)), and returns the overflow once full; it does not react while nothing flows in; volume 0 = instant pass-through), `Separator` (`top[species]` share to out 0, `rated_gpm`, `effective_top(gpm)` smears toward 0.5 when overloaded), `Splitter` (ratio to out 0, `set_ratio`/`nudge` in 5% steps), `Mixer` (2 in).
- `network.py`: `Port`, `Pipe` (`carried` = what entered last step; plug-flow holdup: `slugs` oldest-first, `capacity_gal` from the Manhattan distance between its units × `GAL_PER_PX`, `push(stream)` returns what leaves the far end once full, `fill`, `empty()`; units without positions give capacity 0 = instant, which keeps the sim tests simple), `Network` (connect rules, `step(dt)`, `last_dt`).
  - **Flow model:** each running pump whose inlet is piped straight from a `Feed` or `Tank` draws `setpoint_gpm*dt/60` from it. Then the inline units (pumps, reactors, separators, splitters, mixers) are processed once each in upstream-first order (`_inline_order`), each on the combined stream that reached it from every pump this step (`_inbox`), so streams from different pumps really mix before reacting and reactors/columns see their true total GPM against their rating. Every pipe is pushed through on the way (plug flow), and reactors hold their volume, so liquid takes a few seconds at 1x to cross the plant and a startup front moves along the pipes; what is left in pipes and reactors when the feed runs out never arrives. Outputs land in tanks and outlets as soon as they leave a pipe. Open ports, full tanks, stopped pumps and inline units on a loop with no tank (`_looped`) spill; `spilled_gal` tracks the total; `spills` (last step, as streams) and `spill_totals` (since reset) key each spill by the open out `Port` or by the unit (full tank, stopped pump, tank-less loop), with `spill_reason(key)`, `spilled_by(eq)` and `clear_spills()`. Recycle loops therefore need a tank.

## content/

- `equipment.py`: `Namer` (P101, TK101, R101, C101, SP101, MX101), `make_*(rng, namer, chem, ...)` per type (`make_separator(..., apart=reaction)` builds a guaranteed high-purity column for that reaction), `price_of(eq)` (store price from stats), `starting_hand`, `level_grant` (free reactor + purifying column for the new reaction), `shop_offers`. All take the run's `random.Random`.

## run/

- `contract.py`: `Order` (species, quantity, purity, `spec`, `delivered(outlet)`, `met(outlet)`), `Contract` (level, `orders`, feed `Stream`, `base_pay`, `check(outlets)` with order i graded at outlet i, `summary`), `order_count(level, rng)`, `make_contract(level, chem, rng, min_orders)` (main order = the level's new product, extra orders = earlier products at their own purity; all orders scaled together to the yield cap via `feed_per_gal`), `Payout` + `settle(contract, purities, offspec_gal, spill_gal)` (bonus weighted by order size) with the money constants.
- `history.py`: `History(run)` undo/redo of layout. A snapshot is `(placed [(eq, pos)], pipes, inventory)` holding the real objects; `snapshot()`/`push()` let callers take the snapshot before an edit and keep it only if the edit happened (`record()` = both). Restoring resets units that leave the canvas.
- `state.py`: `RunState` owns the seed/rng, chemistry, `Network` (with fixed FEED, WASTE and `products`, one PRODUCT outlet per order, added as contracts need them; `product` is the first), `inventory`, `money`, `level`, `contract`, `restarts_left`. `start_contract(contract)` adds outlets and sets each one's spec (spare ones get none). `complete_contract()` also rolls `next_contract` (never fewer orders than outlets) for the store to show; `advance()` starts it. `met`, `feed_empty`, `restart()` (restock, empty, keep layout/settings; carries off-spec/spill tallies into `offspec_total`/`spill_total`), `preview_payout()`, `complete_contract()` (pays and stocks `offers`), store `buy(eq)`/`reroll()`/`price(eq)`, `next_grant()`, `advance(grant)`.

## scenes/

- `base.py`: `Scene` interface (`handle_event`, `update(dt)`, `draw(surface)`).
- `play.py`: `PlayScene(game, run)`. `running` flag plus a `result` overlay; editing is always allowed. Layout: header (contract + progress bar), canvas with dot grid, right panel (scrollable `INVENTORY` cards with icons, `FACEPLATE` for the selected unit), bottom softkeys (RUN/PAUSE, SPEED 1/4/16x, RESTART). `self.controls` is a list of `(rect, on_click, on_drag)` rebuilt every `draw()` (softkeys, faceplate buttons/sliders); clicks check it first. Runs the sim at `SIM_SPEED` sim-seconds per real second times the speed, in substeps; shows the result as soon as `run.met`, or "out of feed" after `IDLE_END` idle seconds with an empty feed. `draw_spills` puts the alarm where a spill happens: animated drips, a puddle and a red SPILL GPM readout at an open outlet; a flashing red frame, readout and reason on a unit. Hovering a unit adds how much it has spilled. Pipes draw what they hold, so idle pipes keep their contents' color; pipes removed with a unit are emptied. `return_to_inventory(eq)` is the single path for taking a unit off the canvas (right-click, Delete/Backspace, faceplate key, drag to panel). `self.history` records an undo point before every layout edit (drags snapshot at mouse-down and push only if the drop changed something); Ctrl+Z/Ctrl+Y call `undo()`/`redo()`. `tidy_up()` (T key / TIDY softkey) applies `ui.layout.tidy` as one undo step.
- `store.py`: `StoreScene(game, run)`. Payout breakdown, next-contract panel with the free grant, 6 priced offer cards (click to buy), reroll, then `run.advance(grant)` and a new `PlayScene`.
- Both scenes call `theme.set_species(chem.species, chem.waste)` so colors follow the run's letters.

## ui/

- `theme.py`: dark DCS palette, layout sizes, `PALETTE`/`WASTE_COLOR` and the shared `SPECIES` table (species -> color, mutated in place by `set_species`; defaults to A-D + E for tests).
- `geometry.py`: `_SIZES`, `rect_of`, `fit_rect` (icons), ports, `pipe_points(pipe, lane)` (forward = Z route, backward = loop under both units; `lane` shifts the free legs), `lay_out_pipes` (first lane whose free legs don't overlap earlier pipes), `route_pipes(pipes, obstacles)` (laid-out paths; recycle loops run under the readouts of any `obstacles` unit their bottom run passes beneath plus line-jump arcs where a horizontal run crosses another pipe's vertical run; returns `{pipe: (path, hops)}`), hit-testing, `snap`. The play scene draws and hit-tests pipes from `route_pipes`, then redraws hop arcs on top.
- `layout.py`: `tidy(net, area, keep_out)` auto-layout (no side effects; returns new centers). Layered: DFS from FEED marks recycle pipes as back edges, units go in the column of their longest forward path (FEED first, outlets last, both left where they are), columns spread evenly between them, then each column lines units' in ports up with the out port feeding them, sorts by that height and pushes them apart leaving room for tags and readouts (`_spread`); a right-to-left pass places units nothing feeds next to what they feed. Unpiped units are parked along the top; `keep_out` rects (the legend) shorten the columns they overlap. Long pipes that skip columns are not routed around units in between.
- `widgets.py`: `blend(stream)` color mixing, cached shaded `_cylinder` bodies, `draw_body` (symbol only; reused at icon size by `draw_icon`), `draw_equipment` (symbol + tags + value boxes + ports), `pipe_fill(pipe)` (held slugs as colored fractions of the pipe's length from the inlet end) and `draw_pipe` (wall, empty bore, colored filled part, moving dots only in the filled part); reactors draw a level gauge from `content`, cards, tooltips, frames, buttons, bars, `describe`/`details` text.

## game.py / main.py

`Game` owns the window, clock and current scene; `new_run(seed)` makes a `RunState` and `PlayScene`; `change_scene()` swaps scenes. The window is opened with `pygame.SCALED` (+ `FULLSCREEN` per `settings.FULLSCREEN`, else `RESIZABLE`) so all layout stays in 1280x720 logical pixels and mouse events are mapped automatically; F11 toggles fullscreen, Ctrl+Q quits. Falls back to a plain window if the driver can't scale (headless). `python -m goop_sim` -> `__main__.py` -> `main.main()`.

## Where things go next

- New equipment type: dataclass in `sim/equipment.py`, routing branch in `Network._deliver`, size in `ui/geometry._SIZES`, drawing branch in `ui/widgets.draw_equipment`, `describe`/`details` text, a `make_*` + weight in `content/equipment.py`.
- Chemistry generation: `generate_chemistry` in `sim/chemistry.py` (each step may only use species the plant already has and must use the newest; tests enforce this over 60 seeds).
- Contract and money rules: `run/contract.py`. Prices: `price_of` in `content/equipment.py`.

## Tests

`tests/test_network.py` covers streams, reactions, connection rules, routing through every unit, pump setpoints, splitter tuning, overload effects, outlet grading, spills, tank-less loops, a recycle-through-tank plant, mixing of streams from different pumps, pipe plug flow, startup delay, reactor fill/overflow and steady-state conversion, reactants meeting inside the vessel, and restart emptying pipes and reactors. `tests/test_geometry.py` covers line jumps and lane separation. `tests/test_layout.py` covers tidy (straight series lines, flow order with a recycle, fixed units untouched, parking, no overlaps and legend avoidance over 40 random tangles). `tests/test_history.py` covers undo/redo of place, pipe, move and removal. `tests/test_run.py` covers procedural chemistry (seeding, variety, build-on-last rule, feed cost), dealing (incl. pump ranges and the guaranteed purifying column), pricing, contract escalation/achievability, on-spec checks, payout (purity bonus, fees, floor), fees surviving restarts, store buy/reroll, and plant/settings/money persistence across contracts. Run `pytest`. UI is checked by driving the scenes with synthetic pygame events under `SDL_VIDEODRIVER=dummy` and saving screenshots.
