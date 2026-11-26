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
- **Color.** Colors go by role, since species letters change every run: feed species blue (and green for a second feed), then each chain product orange, magenta, cyan..., waste always brown. The legend marks which letter is waste. Pipes, tank levels and reactor sight glasses show the volume-weighted blend of what they carry, so a stream turns toward its species' color as it gets purer. Moving dots show flow; idle pipes keep a dim tint of their last contents.
- **Persistence.** The plant (placed equipment, pipes, inventory) and money carry over to the next contract. Later contracts build on what you made: the next target is made from species your plant already produces.
- **Random chemistry per run (procedural).** Each run picks fresh species letters, a feed of one species or (40%) two species mixed 50/50-70/30, a waste species, and a 3-step chain. Each step makes a new species from 1-2 species the plant already has, with coefficients 1-2, and always uses the newest product, so every contract builds on the last. Contract n asks for step n's product. Contract quantities are capped at 35% of the chemistry's theoretical max yield so any roll stays achievable. Past the end of the chain contracts ask for more volume, higher purity, and a feed contaminated with waste.
- **Random equipment.** Reactors (conversion 45–90%, rated 80–250 GPM, 35% chance of a side reaction that degrades a species into waste), columns (random per-species split to the top outlet: some species sharp to top, the rest sharp to bottom, 2–15% leak; rated 100–300 GPM), pumps (max 150–600 GPM, min 10–30% of max), tanks (2k–20k gal), splitters, mixers.
- **No dead runs.** The starting hand and each new-reaction grant include a high-purity column (1–5% leak) that sends that reaction's product one way and its reactants the other. Two-feed runs also start with an extra random column.
- **Money.** Completing a contract pays base ($600 + $300 per level) plus a purity bonus: base × 1.5 × how far the average purity of accepted product is from spec toward 100%. Never paid for extra quantity (the contract also ends as soon as quantity is met). Off-spec product costs $0.08/gal and spills $0.15/gal, tallied across restarts. Time is free, so slow or odd settings are safe to explore; waste is the consequence. Payout never drops below 20% of base. Start with $250. The header shows money and an estimated payout live.
- **Store between contracts** (replaces the free draft). 6 offers priced from their stats (bigger tanks, faster/wider-range pumps, higher-conversion/higher-rated reactors without side reactions, sharper/higher-rated columns cost more), buy any you can afford, reroll for $50 (+$25 per reroll in the same store). The new reaction's reactor and its purifying column are free.
- Volumes are gallons; reactions change volume by their coefficients (no mass balance realism).
- Flow model: see ARCHITECTURE. Liquid with nowhere to go is spilled and shown as an alarm.

## Open questions

- Balance: contract sizes, pay, bonus multiplier, fees and prices are first guesses. With the high-purity column a simple plant often earns a ~+100% purity bonus at contract 1, which may be too generous; reactors (~$650-900) may be too pricey.
- Rate effects are judged per pump push, not summed across pumps feeding the same unit in one step (approximation).
- Upgrade cards (boost a placed unit's conversion/pump size/column sharpness) and selling equipment back in the store are not built yet.
- Multiple products per contract, a menu, a run summary/score screen (money earned could be the score).
- Whether to add disruptions (failures, demand spikes). User said randomness is in the equipment and chemistry, so default is no.
