# Game design

## Pitch

A roguelike chemical-engineering game styled as an HMI/SCADA screen (like a water-utility control panel: blue pipes, tank graphics with level readouts, white value boxes with blue text, red/green pump icons, dark toolbar). Each run rolls its own chemistry and deals you random equipment. You build a flowsheet (reactors, separation columns, splitters, mixers, pumps, tanks) that turns a fixed feed into a product spec, then extend that same plant contract after contract.

## Decided

- 2D, Python, pygame-ce.
- **The challenge is building the plant, not operating it.** Build mode: drag equipment from the side panel, click an out port then an in port to pipe it. RUN locks the layout and processes the whole feed; only pumps (on/off) and splitters (ratio) can be touched while running.
- **Contracts.** Each level is a contract: deliver ≥ N gal of a target species at ≥ P% purity into PRODUCT, from a fixed feed amount. Thresholds, not optimization, so many designs pass.
- **Attempts.** 3 RUN attempts per contract. Between attempts the plant layout stays; feed is restocked and tanks/outlets empty. Using all 3 without passing ends the run.
- **Persistence.** The plant (placed equipment, pipes, inventory) carries over to the next contract. Later contracts build on what you made: the next target is made from species your plant already produces.
- **Random chemistry per run.** A 3-step reaction chain rolled from templates (step 1: A→B or 2A→B; step 2: B→C, A+B→C, 2B→C; step 3: C→D, B+C→D, A+C→D). Contract n asks for the product of step n. Past the end of the chain contracts ask for more volume, higher purity, and a feed contaminated with waste E.
- **Random equipment.** Reactors (conversion 45–90%, 35% chance of a side reaction that degrades a species into waste E), columns (random per-species split to the top outlet: some species sharp to top, the rest sharp to bottom), pumps (100–400 GPM), tanks (2k–20k gal), splitters (25/50/75%), mixers.
- **Draft between contracts.** Pick 2 of 5 random cards. The reactor for the newly needed reaction is granted free.
- Species: A (feed) … D, E is waste only. Volumes are gallons; reactions change volume by their coefficients (no mass balance realism).
- Flow model: see ARCHITECTURE. Liquid with nowhere to go is spilled and shown as an alarm.

## Open questions

- Balance: contract quantities/purities are first guesses (B 3000, C 1500, D 1000 gal at 75%). Needs playtesting.
- Upgrade cards (boost a placed unit's conversion/pump size/column sharpness) were planned for the draft but not built yet.
- Multiple products per contract, second feed streams, a menu, a run summary/score screen.
- Should spilling or running time cost something (score, money)?
- Should the panel scroll when inventory gets long?
- Whether to add disruptions (failures, demand spikes). User said randomness is in the equipment and chemistry, so default is no.
