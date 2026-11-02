# goop_sim

Roguelike chemical-engineering game with an HMI/SCADA look, in Python + pygame-ce. Read these first:

- `docs/DESIGN.md`: game concept, decisions made, open questions
- `docs/ARCHITECTURE.md`: layers, modules, how to extend
- `docs/sessions/`: one summary log per working session. Add a new file each session, named by date.

## Commands

- Run: `.venv\Scripts\python -m goop_sim`
- Test: `.venv\Scripts\python -m pytest -q`
- Headless smoke test of the UI: set `SDL_VIDEODRIVER=dummy` and drive `PlayScene.handle_event` with synthetic pygame events.

## Rules

- `sim/` must not import pygame. Game logic goes there with tests; drawing goes in `ui/`.
- Equipment dataclasses use `eq=False`; keep it.
- Update `docs/DESIGN.md` when a design question is answered, `docs/ARCHITECTURE.md` when structure changes, and add a session log at the end of a session.
- On Windows, create files with the Write tool rather than very large shell heredocs.
