# Game design

## Pitch

A roguelike chemical-engineering game styled as an HMI/SCADA screen (like a water-utility control panel: blue pipes, tank graphics with level readouts, white value boxes with blue text, red/green pump icons, dark toolbar with ALARMS / TRENDS / LOGS / REPORTS / COMMS). Each run deals you random equipment (pumps, splitters, tanks, ...) and you must build a process that produces enough product.

## Decided

- 2D, Python, pygame-ce.
- The only randomness is **the equipment you are dealt**.
- You drag dealt equipment from a side panel onto the canvas, then connect it by clicking an out port and an in port to lay pipe.
- Equipment is operated like an HMI: click a pump to start/stop it.
- UI reference style: a real water-system HMI screenshot (light gray background, blue pipes, grey toolbar).

## Open questions

- **Win condition.** Currently a placeholder: produce 5,000 gal total. Candidates: hold a target GPM for some time, total volume by a deadline, etc.
- Run structure: levels per run, rewards/drafting between levels, difficulty scaling, what ends a run.
- Equipment roster beyond pump/tank: splitters, mixers, valves, reactors, filters? Real chemistry (multiple fluids/compositions) or just volume?
- Whether to add disruptions (failures, demand spikes). User said randomness is the equipment only, so default is no.
- Alarms/trends/logs toolbar items are cosmetic for now; could become real features (tank overflow alarms, flow trends).
