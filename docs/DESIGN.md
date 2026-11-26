# Game design

## Pitch

A roguelike chemical-engineering game styled as a dark DCS/HMI control-room screen (black background, shaded gray vessels, cyan tags, black value boxes with green numbers, softkey bar along the bottom). Each run rolls its own chemistry and deals you random equipment. You build a flowsheet (reactors, separation columns, splitters, mixers, pumps, tanks) that turns a fixed feed into a product spec, tune it live until it makes on-spec product, then extend that same plant contract after contract.

## Decided

- 2D, Python, pygame-ce.
- **Build, then run and tune it yourself.** Drag equipment from the inventory (each card has an icon), click an out port then an in port to pipe it. RUN starts the plant live; everything stays editable. There is no pass/fail screen after a run: you watch the colors and readouts and figure out what is wrong.
- **Removing units.** Any placed unit (not FEED/PRODUCT/WASTE) can go back to the inventory at any time: right-click, Delete/Backspace on the selected unit, the faceplate TO INV key, or drag to the panel. Its pipes are removed and its contents lost; its settings (setpoint, split) are kept.
- **Undo/redo.** Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z), plus softkeys, for layout edits only: placing, moving, piping, removing pipes, sending units back. Up to 100 steps, cleared when a new contract starts. Process state is not rewound: a unit brought back by undo comes back empty. Pump setpoints and splitter ratios are not undo steps.
- **Tuning.** Every pump has a dealt flow range (e.g. 30-150 GPM) with a tunable setpoint; splitters tune 0-100% in 5% steps. Faceplate panel (click a unit), mouse wheel over a unit, or arrow keys.
- **Rate matters.** Reactors and columns have a rated GPM. Above it, reactor conversion drops and column splits smear toward 50/50 (load box turns red). Faster finishes sooner but risks going off-spec, so there is a sweet spot to find.
- **Contracts.** Deliver ≥ N gal of a target species into PRODUCT. Each arriving stream is graded: only streams at ≥ P% purity count; off-spec streams are rejected (shown in the header). The contract completes the moment enough on-spec product has arrived. Thresholds, not optimization, so many designs pass.
- **Running out.** Feed is finite (15,000 gal + 1,000 per level). Running dry before finishing offers a restart (restock feed, empty the plant, keep layout and settings); 2 restarts per contract, then the run is over. Restart is also a softkey.
- **Display.** Starts fullscreen; F11 toggles, Ctrl+Q quits. The game draws at a fixed 1280x720 and SDL scales it (letterboxed on non-16:9 screens), so the canvas does not grow with the screen.
- **Pipe readability.** Pipes route orthogonally; parallel pipes that would overlap are pushed into separate lanes, and where a horizontal run crosses another pipe's vertical run it draws a line jump (arc) over it. Hovering a pipe highlights it and shows its flow and composition (% and GPM per species).
- **Color.** Each species has a color (A blue, B green, C orange, D magenta, E brown). Pipes, tank levels and reactor sight glasses show the volume-weighted blend of what they carry, so a stream turns toward its species' color as it gets purer. Moving dots show flow; idle pipes keep a dim tint of their last contents.
- **Persistence.** The plant (placed equipment, pipes, inventory) carries over to the next contract. Later contracts build on what you made: the next target is made from species your plant already produces.
- **Random chemistry per run.** A 3-step reaction chain rolled from templates (step 1: A→B or 2A→B; step 2: B→C, A+B→C, 2B→C; step 3: C→D, B+C→D, A+C→D). Contract n asks for the product of step n. Past the end of the chain contracts ask for more volume, higher purity, and a feed contaminated with waste E.
- **Random equipment.** Reactors (conversion 45–90%, rated 80–250 GPM, 35% chance of a side reaction that degrades a species into waste E), columns (random per-species split to the top outlet: some species sharp to top, the rest sharp to bottom; rated 100–300 GPM), pumps (max 150–600 GPM, min 10–30% of max), tanks (2k–20k gal), splitters, mixers.
- **Draft between contracts.** Pick 2 of 5 random cards. The reactor for the newly needed reaction is granted free.
- Species: A (feed) … D, E is waste only. Volumes are gallons; reactions change volume by their coefficients (no mass balance realism).
- Flow model: see ARCHITECTURE. Liquid with nowhere to go is spilled and shown as an alarm.

## Open questions

- Balance: contract quantities/purities are first guesses (B 3000, C 1500, D 1000 gal at 75%) and contract 1 can pass with no tuning if wired right. Needs playtesting; may want tighter purity or a time/feed squeeze.
- Rate effects are judged per pump push, not summed across pumps feeding the same unit in one step (approximation).
- Upgrade cards (boost a placed unit's conversion/pump size/column sharpness) were planned for the draft but not built yet.
- Multiple products per contract, second feed streams, a menu, a run summary/score screen.
- Should spilling or running time cost something (score, money)?
- Whether to add disruptions (failures, demand spikes). User said randomness is in the equipment and chemistry, so default is no.
