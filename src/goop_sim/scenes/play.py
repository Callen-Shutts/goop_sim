import math

import pygame

from goop_sim import settings
from goop_sim.run.state import RunState
from goop_sim.scenes.base import Scene
from goop_sim.sim.equipment import Pump, Splitter
from goop_sim.ui import theme, widgets
from goop_sim.ui.geometry import (
    PORT_RADIUS,
    all_ports,
    dist_to_segment,
    pipe_points,
    port_pos,
    rect_of,
    snap,
)

CANVAS_RIGHT = settings.SCREEN_WIDTH - theme.PANEL_WIDTH
CLICK_SLOP = 4
SIM_SPEED = 60.0  # simulated seconds per real second at 1x
SPEEDS = (1, 4, 16)  # fast-forward multipliers, cycled with F or the speed button
MAX_SUBSTEP = 2.0  # simulated seconds per Network.step
IDLE_END = 1.5  # real seconds with no flow before an attempt ends by itself


class PlayScene(Scene):
    """Build the plant (drag, pipe, set pumps/splitters), then RUN it against the current contract.

    Modes: "build" (editing), "running" (sim advancing; only pumps and splitters can be operated),
    "result" (attempt scored, overlay waiting for a click).
    """

    def __init__(self, game, run: RunState):
        super().__init__(game)
        self.run = run
        self.font = pygame.font.SysFont("arial", 14)
        self.big = pygame.font.SysFont("arial", 24, bold=True)
        self.mode = "build"
        self.result = None  # {"ok", "title", "lines", "button"} while mode == "result"
        self.pending = None  # Port the player clicked first while piping
        self.drag = None  # {"eq", "offset", "start", "moved", "from_inventory", "pos"}
        self.mouse = (0, 0)
        self.idle = 0.0
        self.speed = SPEEDS[0]
        self.place_fixtures()

    @property
    def net(self):
        return self.run.net

    def place_fixtures(self):
        mid = (settings.SCREEN_HEIGHT + theme.TOOLBAR_HEIGHT) // 2
        spots = {
            self.run.feed: (80, mid),
            self.run.product: (CANVAS_RIGHT - 80, mid - 120),
            self.run.waste: (CANVAS_RIGHT - 80, mid + 120),
        }
        for eq, pos in spots.items():
            if eq.pos is None:
                eq.pos = snap(pos)

    # -- layout helpers -------------------------------------------------

    def card_rect(self, index: int) -> pygame.Rect:
        y = theme.TOOLBAR_HEIGHT + 36 + index * (theme.CARD_HEIGHT + theme.CARD_GAP)
        return pygame.Rect(CANVAS_RIGHT + 12, y, theme.PANEL_WIDTH - 24, theme.CARD_HEIGHT)

    def run_button_rect(self) -> pygame.Rect:
        return pygame.Rect(CANVAS_RIGHT + 12, settings.SCREEN_HEIGHT - 56, theme.PANEL_WIDTH - 24, 44)

    def speed_button_rect(self) -> pygame.Rect:
        return pygame.Rect(CANVAS_RIGHT + 12, settings.SCREEN_HEIGHT - 96, theme.PANEL_WIDTH - 24, 32)

    def cycle_speed(self):
        self.speed = SPEEDS[(SPEEDS.index(self.speed) + 1) % len(SPEEDS)]

    def result_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, 440, 230)
        rect.center = (CANVAS_RIGHT // 2, (settings.SCREEN_HEIGHT + theme.TOOLBAR_HEIGHT) // 2)
        return rect

    def continue_rect(self) -> pygame.Rect:
        box = self.result_rect()
        return pygame.Rect(box.centerx - 100, box.bottom - 60, 200, 42)

    def port_at(self, pos):
        for eq in self.net.equipment:
            for port in all_ports(eq):
                if pygame.Vector2(port_pos(port)).distance_to(pos) <= PORT_RADIUS + 3:
                    return port
        return None

    def equipment_at(self, pos):
        for eq in reversed(self.net.equipment):
            if rect_of(eq).collidepoint(pos):
                return eq
        return None

    def card_at(self, pos):
        for i, item in enumerate(self.run.inventory):
            if self.card_rect(i).collidepoint(pos):
                return item
        return None

    def pipe_at(self, pos):
        for pipe in self.net.pipes:
            pts = pipe_points(pipe)
            if any(dist_to_segment(pos, a, b) <= 6 for a, b in zip(pts, pts[1:])):
                return pipe
        return None

    # -- input ----------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
            self.on_motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.mode == "result":
                if event.button == 1 and self.continue_rect().collidepoint(event.pos):
                    self.on_continue()
            elif event.button == 1:
                self.on_left_down(event.pos)
            elif event.button == 3:
                self.on_right_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_left_up(event.pos)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.pending = None
            elif event.key == pygame.K_SPACE and self.mode != "result":
                self.press_run()
            elif event.key == pygame.K_f:
                self.cycle_speed()
            elif event.key == pygame.K_RETURN and self.mode == "result":
                self.on_continue()

    def operate(self, eq):
        if isinstance(eq, Pump):
            eq.toggle()
        elif isinstance(eq, Splitter):
            eq.cycle()

    def on_left_down(self, pos):
        if self.run_button_rect().collidepoint(pos):
            self.press_run()
            return
        if self.speed_button_rect().collidepoint(pos):
            self.cycle_speed()
            return
        if self.mode == "running":
            self.operate(self.equipment_at(pos))
            return
        port = self.port_at(pos)
        if port:
            if self.pending is None:
                if not self.net.pipe_at(port):
                    self.pending = port
            else:
                self.net.connect(self.pending, port)
                self.pending = None
            return
        self.pending = None
        eq = self.equipment_at(pos)
        if eq and not eq.fixed:
            self.drag = {
                "eq": eq,
                "offset": (eq.pos[0] - pos[0], eq.pos[1] - pos[1]),
                "start": pos,
                "moved": False,
                "from_inventory": False,
            }
            return
        item = self.card_at(pos)
        if item:
            self.drag = {"eq": item, "offset": (0, 0), "start": pos, "moved": True, "from_inventory": True, "pos": pos}

    def on_right_down(self, pos):
        if self.mode != "build":
            return
        if self.pending:
            self.pending = None
            return
        pipe = self.pipe_at(pos)
        if pipe:
            self.net.disconnect(pipe)

    def on_motion(self, pos):
        d = self.drag
        if not d:
            return
        if pygame.Vector2(pos).distance_to(d["start"]) > CLICK_SLOP:
            d["moved"] = True
        if not d["moved"]:
            return
        new_pos = (pos[0] + d["offset"][0], pos[1] + d["offset"][1])
        if d["from_inventory"]:
            d["pos"] = new_pos
        else:
            d["eq"].pos = new_pos

    def on_left_up(self, pos):
        d = self.drag
        if not d:
            return
        self.drag = None
        eq = d["eq"]
        if not d["moved"]:
            self.operate(eq)
            return
        if pos[0] >= CANVAS_RIGHT or pos[1] < theme.TOOLBAR_HEIGHT:
            if not d["from_inventory"]:
                self.net.remove(eq)
                eq.pos = None
                eq.reset()
                self.run.inventory.append(eq)
            return
        target = snap((pos[0] + d["offset"][0], pos[1] + d["offset"][1]))
        if d["from_inventory"]:
            self.run.inventory.remove(eq)
            self.net.add(eq)
        eq.pos = target

    def press_run(self):
        if self.mode == "build":
            self.mode = "running"
            self.pending = None
            self.drag = None
            self.idle = 0.0
        elif self.mode == "running":
            self.end_attempt()

    def end_attempt(self):
        run = self.run
        contract = run.contract
        received = run.product.received
        ok = run.finish_attempt()
        lines = [
            f"Delivered {contract.delivered(received):,.0f} / {contract.quantity_gal:,.0f} GAL {contract.species}",
            f"Purity {received.fraction(contract.species):.0%}  (need {contract.purity:.0%})",
        ]
        if run.net.spilled_gal > 0.5:
            lines.append(f"Spilled {run.net.spilled_gal:,.0f} GAL")
        if ok:
            title, button = f"CONTRACT {run.level} MET", "PICK EQUIPMENT"
        elif run.over:
            title, button = "RUN OVER", "NEW RUN"
            lines.append(f"You reached contract {run.level}.")
        else:
            title, button = "CONTRACT FAILED", "BACK TO BUILD"
            lines.append(f"{run.attempts_left} attempt(s) left. Plant layout is kept.")
        self.result = {"ok": ok, "title": title, "lines": lines, "button": button}
        self.mode = "result"

    def on_continue(self):
        if self.result["ok"]:
            from goop_sim.scenes.draft import DraftScene

            self.game.change_scene(DraftScene(self.game, self.run))
        elif self.run.over:
            self.game.new_run()
        else:
            self.run.reset_plant()
            self.result = None
            self.mode = "build"

    # -- loop -----------------------------------------------------------

    def update(self, dt):
        if self.mode != "running":
            return
        sim_dt = dt * SIM_SPEED * self.speed
        steps = max(1, math.ceil(sim_dt / MAX_SUBSTEP))
        moved = 0.0
        for _ in range(steps):
            self.net.step(sim_dt / steps)
            moved += self.net.moved_gal
        self.idle = 0.0 if moved > 1e-6 else self.idle + dt
        if self.idle >= IDLE_END:
            self.end_attempt()

    def draw(self, surface):
        run = self.run
        surface.fill(theme.BACKGROUND)
        self.draw_legend(surface)
        for pipe in self.net.pipes:
            widgets.draw_pipe(surface, pipe)
        for eq in self.net.equipment:
            hot = self.pending if self.pending and self.pending.equipment is eq else None
            widgets.draw_equipment(surface, self.font, eq, highlight=hot)
        if self.pending:
            pygame.draw.line(surface, theme.PORT_HOT, port_pos(self.pending), self.mouse, 2)

        pygame.draw.rect(
            surface, theme.PANEL, (CANVAS_RIGHT, theme.TOOLBAR_HEIGHT, theme.PANEL_WIDTH, settings.SCREEN_HEIGHT)
        )
        widgets.draw_label(
            surface, self.font, (CANVAS_RIGHT + theme.PANEL_WIDTH // 2, theme.TOOLBAR_HEIGHT + 18), "EQUIPMENT"
        )
        for i, item in enumerate(run.inventory):
            if self.drag and self.drag["eq"] is item and self.drag["from_inventory"]:
                continue
            widgets.draw_card(surface, self.font, self.card_rect(i), item)
        widgets.draw_button(surface, self.font, self.speed_button_rect(), f"SPEED {self.speed}x  (F)", theme.TOOLBAR)
        if self.mode == "build":
            widgets.draw_button(surface, self.font, self.run_button_rect(), "RUN  (SPACE)")
        elif self.mode == "running":
            widgets.draw_button(surface, self.font, self.run_button_rect(), "STOP + SCORE", theme.BUTTON_STOP)
        else:
            widgets.draw_button(surface, self.font, self.run_button_rect(), "SCORED", theme.BUTTON_DISABLED)

        if self.drag and self.drag["moved"] and self.drag["from_inventory"]:
            widgets.draw_equipment(surface, self.font, self.drag["eq"], pos=self.drag["pos"], ports=False)

        self.draw_toolbar(surface)
        if self.mode == "result":
            self.draw_result(surface)
        elif not self.drag:
            hover = self.equipment_at(self.mouse) if self.mouse[0] < CANVAS_RIGHT else self.card_at(self.mouse)
            if hover:
                widgets.draw_tooltip(surface, self.font, self.mouse, widgets.details(hover))

    def draw_toolbar(self, surface):
        run, c = self.run, self.run.contract
        left = f"CONTRACT {run.level}:  {c.summary}      ATTEMPTS {run.attempts_left}"
        got = run.product.received
        right = f"PRODUCT {c.species} {c.delivered(got):,.0f} GAL  {got.fraction(c.species):.0%}"
        color = theme.TOOLBAR_TEXT
        if self.net.spilled_gal > 0.5:
            right = f"SPILL {self.net.spilled_gal:,.0f} GAL    " + right
            color = theme.PORT_HOT
        widgets.draw_toolbar(surface, self.font, settings.SCREEN_WIDTH, left, right, color)

    def draw_legend(self, surface):
        reactions = self.run.chem.known(self.run.level)
        lines = [r.label for r in reactions]
        height = 30 + 18 * len(lines)
        rect = pygame.Rect(12, settings.SCREEN_HEIGHT - 12 - height, 170, height)
        widgets.draw_panel_box(surface, self.font, rect, "KNOWN REACTIONS", lines)
        x = rect.right + 16
        for species, color in theme.SPECIES.items():
            pygame.draw.rect(surface, color, (x, rect.bottom - 16, 14, 14))
            widgets.draw_label(surface, self.font, (x + 24, rect.bottom - 9), species)
            x += 40

    def draw_result(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill(theme.OVERLAY_SHADE)
        surface.blit(shade, (0, 0))
        box = self.result_rect()
        pygame.draw.rect(surface, theme.VALUE_BOX, box)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, box, 2)
        color = theme.OK if self.result["ok"] else theme.ALARM
        widgets.draw_label(surface, self.big, (box.centerx, box.y + 30), self.result["title"], color)
        y = box.y + 66
        for line in self.result["lines"]:
            widgets.draw_label(surface, self.font, (box.centerx, y), line)
            y += 20
        widgets.draw_button(surface, self.font, self.continue_rect(), self.result["button"])
