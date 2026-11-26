import math

import pygame

from goop_sim import settings
from goop_sim.run.state import RunState
from goop_sim.scenes.base import Scene
from goop_sim.sim.equipment import Pump, Reactor, Splitter
from goop_sim.sim.network import Port
from goop_sim.ui import theme, widgets
from goop_sim.ui.geometry import (
    GRID,
    PORT_RADIUS,
    all_ports,
    dist_to_segment,
    pipe_points,
    port_pos,
    rect_of,
    route_pipes,
    snap,
)

W, H = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
CANVAS_RIGHT = W - theme.PANEL_WIDTH
CANVAS_TOP = theme.TOOLBAR_HEIGHT
CANVAS_BOTTOM = H - theme.BOTTOM_BAR
CLICK_SLOP = 4
SIM_SPEED = 60.0  # simulated seconds per real second at 1x
SPEEDS = (1, 4, 16)
MAX_SUBSTEP = 2.0  # simulated seconds per Network.step
IDLE_END = 1.5  # real seconds with no flow and no feed before "out of feed"

FACEPLATE = pygame.Rect(
    CANVAS_RIGHT + 8, CANVAS_BOTTOM - theme.FACEPLATE_HEIGHT - 8, theme.PANEL_WIDTH - 16, theme.FACEPLATE_HEIGHT
)
INVENTORY = pygame.Rect(CANVAS_RIGHT + 8, CANVAS_TOP + 28, theme.PANEL_WIDTH - 16, FACEPLATE.top - CANVAS_TOP - 36)


class PlayScene(Scene):
    """Build and operate the plant live.

    Everything stays editable. RUN starts the flow; tune pumps and splitters (faceplate, mouse
    wheel, arrow keys) and watch the colors until PRODUCT reads on-spec. The contract completes
    as soon as enough on-spec product has arrived; running dry offers a restart.
    """

    def __init__(self, game, run: RunState):
        super().__init__(game)
        self.run = run
        self.font = pygame.font.SysFont("consolas", 13)
        self.mid = pygame.font.SysFont("consolas", 15, bold=True)
        self.big = pygame.font.SysFont("consolas", 26, bold=True)
        self.running = False
        self.speed = SPEEDS[0]
        self.result = None  # {"kind", "title", "lines", "button"}
        self.pending = None  # Port clicked first while piping
        self.drag = None  # {"eq", "offset", "start", "moved", "from_inventory", "pos"}
        self.slider = None  # callback(x) while dragging a faceplate slider
        self.selected = None
        self.mouse = (0, 0)
        self.idle = 0.0
        self.t = 0.0
        self.scroll = 0
        self.controls = []  # (rect, on_click, on_drag) rebuilt every draw
        self.pipe_memory = {}  # last color seen in each pipe, so idle pipes stay tinted
        self.grid = self._make_grid()
        self.place_fixtures()

    @property
    def net(self):
        return self.run.net

    def place_fixtures(self):
        mid = (CANVAS_TOP + CANVAS_BOTTOM) // 2
        spots = {
            self.run.feed: (70, mid),
            self.run.product: (CANVAS_RIGHT - 80, mid - 120),
            self.run.waste: (CANVAS_RIGHT - 80, mid + 120),
        }
        for eq, pos in spots.items():
            if eq.pos is None:
                eq.pos = snap(pos)

    def _make_grid(self):
        surf = pygame.Surface((CANVAS_RIGHT, CANVAS_BOTTOM - CANVAS_TOP))
        surf.fill(theme.BACKGROUND)
        for x in range(0, CANVAS_RIGHT, GRID):
            for y in range(0, CANVAS_BOTTOM - CANVAS_TOP, GRID):
                surf.set_at((x, y), theme.GRID_DOT)
        return surf

    # -- hit testing -----------------------------------------------------

    def card_rect(self, index: int) -> pygame.Rect:
        y = INVENTORY.y + index * (theme.CARD_HEIGHT + theme.CARD_GAP) - self.scroll
        return pygame.Rect(INVENTORY.x, y, INVENTORY.width, theme.CARD_HEIGHT)

    def max_scroll(self) -> int:
        content = len(self.run.inventory) * (theme.CARD_HEIGHT + theme.CARD_GAP)
        return max(0, content - INVENTORY.height)

    def card_at(self, pos):
        if not INVENTORY.collidepoint(pos):
            return None
        for i, item in enumerate(self.run.inventory):
            if self.card_rect(i).collidepoint(pos):
                return item
        return None

    def in_canvas(self, pos) -> bool:
        return pos[0] < CANVAS_RIGHT and CANVAS_TOP <= pos[1] < CANVAS_BOTTOM

    def port_at(self, pos):
        for eq in self.net.equipment:
            for port in all_ports(eq):
                if pygame.Vector2(port_pos(port)).distance_to(pos) <= PORT_RADIUS + 3:
                    return port
        return None

    def equipment_at(self, pos):
        for eq in reversed(self.net.equipment):
            if rect_of(eq).inflate(6, 6).collidepoint(pos):
                return eq
        return None

    def pipe_at(self, pos):
        """Hit-test against the drawn routes (lanes and jumps included)."""
        for pipe, (path, _hops) in route_pipes(self.net.pipes).items():
            if any(dist_to_segment(pos, a, b) <= 6 for a, b in zip(path, path[1:])):
                return pipe
        return None

    def hovered_pipe(self):
        """Pipe under the mouse, unless the mouse is on equipment, a port, or busy dragging/piping."""
        if self.result or self.drag or self.slider or self.pending or not self.in_canvas(self.mouse):
            return None
        if self.equipment_at(self.mouse) or self.port_at(self.mouse):
            return None
        return self.pipe_at(self.mouse)

    def result_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, 480, 250)
        rect.center = (CANVAS_RIGHT // 2, (CANVAS_TOP + CANVAS_BOTTOM) // 2)
        return rect

    def continue_rect(self) -> pygame.Rect:
        box = self.result_rect()
        return pygame.Rect(box.centerx - 140, box.bottom - 58, 280, 40)

    # -- actions -----------------------------------------------------------

    def toggle_run(self):
        self.running = not self.running
        self.idle = 0.0

    def cycle_speed(self):
        self.speed = SPEEDS[(SPEEDS.index(self.speed) + 1) % len(SPEEDS)]

    def restart(self):
        if self.run.restart():
            self.running = False
            self.pipe_memory.clear()
            self.result = None

    def return_to_inventory(self, eq):
        """Take a placed unit off the canvas: its pipes go, its contents are lost, settings are kept."""
        if eq is None or eq.fixed or eq not in self.net.equipment:
            return
        for pipe in [p for p in self.net.pipes if eq in (p.out.equipment, p.into.equipment)]:
            self.pipe_memory.pop(pipe, None)
        if self.pending and self.pending.equipment is eq:
            self.pending = None
        self.net.remove(eq)
        eq.pos = None
        eq.reset()
        self.run.inventory.append(eq)
        if self.selected is eq:
            self.selected = None

    def nudge(self, eq, steps):
        if isinstance(eq, (Pump, Splitter)):
            eq.nudge(steps)

    def show_result(self, kind):
        run, c = self.run, self.run.contract
        lines = [
            f"ON-SPEC {c.species}   {c.delivered(run.product):,.0f} / {c.quantity_gal:,.0f} GAL",
            f"OFF-SPEC REJECTED  {run.product.rejected_gal:,.0f} GAL",
            f"SPILLED            {self.net.spilled_gal:,.0f} GAL",
        ]
        if kind == "met":
            title, button = f"CONTRACT {run.level} COMPLETE", "PICK NEW EQUIPMENT"
            lines.append(f"FEED LEFT          {run.feed.stock.total():,.0f} GAL")
        elif run.restarts_left > 0:
            title, button = "OUT OF FEED", f"RESTART CONTRACT ({run.restarts_left} LEFT)"
            lines.append("Restart restocks feed and empties the plant.")
        else:
            title, button = "RUN OVER", "START A NEW RUN"
            lines.append(f"You reached contract {run.level}.")
        self.result = {"kind": kind, "title": title, "lines": lines, "button": button}
        self.running = False

    def on_continue(self):
        if self.result["kind"] == "met":
            from goop_sim.scenes.draft import DraftScene

            self.game.change_scene(DraftScene(self.game, self.run))
        elif self.run.restarts_left > 0:
            self.restart()
        else:
            self.game.new_run()

    # -- input -------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
            self.on_motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.result:
                if event.button == 1 and self.continue_rect().collidepoint(event.pos):
                    self.on_continue()
            elif event.button == 1:
                self.on_left_down(event.pos)
            elif event.button == 3:
                self.on_right_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_left_up(event.pos)
        elif event.type == pygame.MOUSEWHEEL and not self.result:
            if INVENTORY.collidepoint(self.mouse):
                self.scroll = max(0, min(self.max_scroll(), self.scroll - event.y * 30))
            elif self.in_canvas(self.mouse):
                self.nudge(self.equipment_at(self.mouse), event.y)
            elif FACEPLATE.collidepoint(self.mouse):
                self.nudge(self.selected, event.y)
        elif event.type == pygame.KEYDOWN:
            if self.result:
                if event.key == pygame.K_RETURN:
                    self.on_continue()
            elif event.key == pygame.K_ESCAPE:
                self.pending = None
                self.selected = None
            elif event.key == pygame.K_SPACE:
                self.toggle_run()
            elif event.key == pygame.K_f:
                self.cycle_speed()
            elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                self.return_to_inventory(self.selected)
            elif event.key in (pygame.K_UP, pygame.K_RIGHT):
                self.nudge(self.selected, 1)
            elif event.key in (pygame.K_DOWN, pygame.K_LEFT):
                self.nudge(self.selected, -1)

    def on_left_down(self, pos):
        for rect, on_click, on_drag in self.controls:
            if rect.collidepoint(pos):
                on_click(pos)
                self.slider = on_drag
                return
        if self.in_canvas(pos):
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
            if eq is None:
                self.selected = None
            elif eq.fixed:
                self.selected = eq
            else:
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
            self.drag = {"eq": item, "offset": (0, 0), "start": pos, "moved": False, "from_inventory": True, "pos": pos}

    def on_right_down(self, pos):
        if self.pending:
            self.pending = None
            return
        if not self.in_canvas(pos):
            return
        eq = self.equipment_at(pos)
        if eq:
            self.return_to_inventory(eq)
            return
        pipe = self.pipe_at(pos)
        if pipe:
            self.net.disconnect(pipe)
            self.pipe_memory.pop(pipe, None)

    def on_motion(self, pos):
        if self.slider:
            self.slider(pos)
            return
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
        self.slider = None
        d = self.drag
        if not d:
            return
        self.drag = None
        eq = d["eq"]
        if not d["moved"]:
            if not d["from_inventory"]:
                self.selected = eq
            return
        if not self.in_canvas(pos):
            if not d["from_inventory"]:
                self.return_to_inventory(eq)
            return
        target = snap((pos[0] + d["offset"][0], pos[1] + d["offset"][1]))
        if d["from_inventory"]:
            self.run.inventory.remove(eq)
            self.net.add(eq)
            self.scroll = min(self.scroll, self.max_scroll())
        eq.pos = target
        self.selected = eq

    # -- loop --------------------------------------------------------------

    def update(self, dt):
        self.t += dt
        if self.result or not self.running:
            return
        sim_dt = dt * SIM_SPEED * self.speed
        steps = max(1, math.ceil(sim_dt / MAX_SUBSTEP))
        moved = 0.0
        for _ in range(steps):
            self.net.step(sim_dt / steps)
            moved += self.net.moved_gal
            if self.run.met:
                self.show_result("met")
                return
        self.idle = 0.0 if moved > 1e-6 else self.idle + dt
        if self.run.feed_empty and self.idle >= IDLE_END:
            self.show_result("dry")

    # -- drawing -----------------------------------------------------------

    def pipe_color(self, pipe):
        color = widgets.blend(pipe.carried)
        if color:
            self.pipe_memory[pipe] = color
            return color
        old = self.pipe_memory.get(pipe)
        return widgets.mix(old, theme.PIPE_EMPTY, 0.5) if old else None

    def draw(self, surface):
        self.controls = []
        surface.fill(theme.BACKGROUND)
        surface.blit(self.grid, (0, CANVAS_TOP))
        self.draw_legend(surface)

        net = self.net
        routes = route_pipes(net.pipes)
        hovered = self.hovered_pipe()
        colors = {pipe: self.pipe_color(pipe) for pipe in net.pipes}
        flowing = self.running and net.last_dt > 0
        for pipe, (path, _hops) in routes.items():
            gpm = pipe.carried.total() * 60 / net.last_dt if flowing else 0.0
            widgets.draw_pipe(surface, path, colors[pipe], gpm, self.t, pipe is hovered)
        for pipe, (_path, hops) in routes.items():  # jumps go on top of the pipes they cross
            for arc in hops:
                widgets.draw_hop(surface, arc, colors[pipe], pipe is hovered)
        for eq in net.equipment:
            hot = self.pending if self.pending and self.pending.equipment is eq else None
            fill = None
            if isinstance(eq, Reactor):
                out = net.pipe_at(Port(eq, "out"))
                fill = self.pipe_color(out) if out else None
            spec = self.run.contract.spec if eq is self.run.product else None
            widgets.draw_equipment(surface, self.font, eq, highlight=hot, selected=eq is self.selected, fill=fill, spec=spec)
        if self.pending:
            pygame.draw.line(surface, theme.PORT_HOT, port_pos(self.pending), self.mouse, 2)

        self.draw_panel(surface)
        self.draw_header(surface)
        self.draw_softkeys(surface)

        if self.drag and self.drag["moved"] and self.drag["from_inventory"]:
            widgets.draw_equipment(surface, self.font, self.drag["eq"], pos=self.drag["pos"], ports=False)

        if self.result:
            self.draw_result(surface)
        elif not self.drag and not self.slider:
            hover = self.equipment_at(self.mouse) if self.in_canvas(self.mouse) else self.card_at(self.mouse)
            if hover and hover is not self.selected:
                widgets.draw_tooltip(surface, self.font, self.mouse, widgets.details(hover))
            elif hovered:
                lines = widgets.pipe_details(hovered, net.last_dt, self.running)
                widgets.draw_tooltip(surface, self.font, self.mouse, lines)

    def draw_header(self, surface):
        run, c = self.run, self.run.contract
        pygame.draw.rect(surface, theme.PANEL, (0, 0, W, CANVAS_TOP))
        pygame.draw.line(surface, theme.PANEL_EDGE, (0, CANVAS_TOP - 1), (W, CANVAS_TOP - 1))
        widgets.draw_text(surface, self.mid, (14, CANVAS_TOP // 2), f"CONTRACT {run.level}", theme.TAG_TEXT, "midleft")
        widgets.draw_text(surface, self.font, (130, CANVAS_TOP // 2), f"MAKE {c.summary}", theme.TEXT, "midleft")
        bar = pygame.Rect(470, 12, 220, 16)
        done = c.delivered(run.product)
        widgets.draw_bar(surface, bar, done / c.quantity_gal, theme.SPECIES.get(c.species, theme.OK))
        widgets.draw_text(surface, self.font, (bar.right + 8, bar.centery), f"{done:,.0f}/{c.quantity_gal:,.0f}", theme.VALUE_TEXT, "midleft")
        rej, spill = run.product.rejected_gal, self.net.spilled_gal
        right = f"FEED {run.feed.stock.total():,.0f}   OFF-SPEC {rej:,.0f}   SPILL {spill:,.0f}"
        color = theme.WARN if rej > 0.5 or spill > 0.5 else theme.TEXT
        widgets.draw_text(surface, self.font, (W - 14, CANVAS_TOP // 2), right, color, "midright")

    def draw_panel(self, surface):
        pygame.draw.rect(surface, theme.PANEL, (CANVAS_RIGHT, CANVAS_TOP, theme.PANEL_WIDTH, CANVAS_BOTTOM - CANVAS_TOP))
        pygame.draw.line(surface, theme.PANEL_EDGE, (CANVAS_RIGHT, CANVAS_TOP), (CANVAS_RIGHT, CANVAS_BOTTOM))
        widgets.draw_text(surface, self.mid, (CANVAS_RIGHT + 12, CANVAS_TOP + 14), "INVENTORY", theme.TAG_TEXT, "midleft")
        if self.max_scroll():
            widgets.draw_text(surface, self.font, (W - 12, CANVAS_TOP + 14), "wheel to scroll", theme.MUTED, "midright")
        surface.set_clip(INVENTORY)
        for i, item in enumerate(self.run.inventory):
            if self.drag and self.drag["eq"] is item and self.drag["moved"]:
                continue
            widgets.draw_card(surface, self.font, self.card_rect(i), item)
        surface.set_clip(None)
        if not self.run.inventory:
            widgets.draw_text(surface, self.font, INVENTORY.center, "(all equipment placed)", theme.MUTED)
        self.draw_faceplate(surface)

    def draw_faceplate(self, surface):
        rect, eq = FACEPLATE, self.selected
        widgets.draw_frame(surface, self.font, rect, f"FACEPLATE  {eq.name}" if eq else "FACEPLATE")
        x, y, w = rect.x + 10, rect.y + 28, rect.width - 20
        if eq is not None and not eq.fixed:
            # small "return to inventory" key in the title strip
            back = pygame.Rect(rect.right - 92, rect.y + 2, 88, 16)
            widgets.draw_button(surface, self.font, back, "TO INV [DEL]", theme.KEY_DANGER)
            self.controls.append((back, lambda _p, e=eq: self.return_to_inventory(e), None))
        if eq is None:
            for i, line in enumerate(["Click a unit to inspect", "and tune it here.", "", "Wheel over a pump or", "splitter to adjust it."]):
                widgets.draw_text(surface, self.font, (x, y + 4 + i * 18), line, theme.MUTED, "topleft")
            return
        if isinstance(eq, Pump):
            btn = pygame.Rect(x, y, 104, 28)
            fill, label = (theme.KEY_ACTIVE, "RUNNING") if eq.running else (theme.KEY_DANGER, "STOPPED")
            widgets.draw_button(surface, self.font, btn, label, fill)
            self.controls.append((btn, lambda _p, p=eq: p.toggle(), None))
            widgets.draw_value_box(surface, self.font, (btn.right + 52, btn.centery), f"PV {eq.flow_gpm:4.0f}")
            self._slider(
                surface,
                y + 42,
                f"SETPOINT {eq.setpoint_gpm:.0f} GPM",
                (eq.setpoint_gpm - eq.min_gpm) / max(1e-9, eq.max_gpm - eq.min_gpm),
                f"{eq.min_gpm:.0f}",
                f"{eq.max_gpm:.0f}",
                lambda f, p=eq: p.set_setpoint(round((p.min_gpm + f * (p.max_gpm - p.min_gpm)) / 5) * 5),
                eq,
                f"STEP {eq.step_gpm:.0f}",
            )
        elif isinstance(eq, Splitter):
            widgets.draw_text(surface, self.font, (x, y + 6), "Share of flow to TOP outlet", theme.MUTED, "topleft")
            self._slider(
                surface,
                y + 42,
                f"TOP {eq.ratio:.0%}  /  BTM {1 - eq.ratio:.0%}",
                eq.ratio,
                "0%",
                "100%",
                lambda f, s=eq: s.set_ratio(f),
                eq,
                "STEP 5%",
            )
        else:
            for i, line in enumerate(widgets.details(eq)[1:9]):
                widgets.draw_text(surface, self.font, (x, y + i * 18), line, theme.TEXT, "topleft")

    def _slider(self, surface, y, label, fraction, lo, hi, set_fraction, eq, step_text):
        x, w = FACEPLATE.x + 10, FACEPLATE.width - 20
        widgets.draw_text(surface, self.mid, (x, y), label, theme.VALUE_TEXT, "topleft")
        bar = pygame.Rect(x, y + 24, w, 18)
        widgets.draw_bar(surface, bar, fraction, theme.TAG_TEXT)
        knob = pygame.Rect(0, 0, 6, 24)
        knob.center = (bar.x + round(bar.width * fraction), bar.centery)
        pygame.draw.rect(surface, theme.TEXT, knob)
        widgets.draw_text(surface, self.font, (x, bar.bottom + 4), lo, theme.MUTED, "topleft")
        widgets.draw_text(surface, self.font, (x + w, bar.bottom + 4), hi, theme.MUTED, "topright")

        def drag(pos, bar=bar):
            set_fraction(max(0.0, min(1.0, (pos[0] - bar.x) / bar.width)))

        self.controls.append((bar.inflate(0, 10), drag, drag))
        minus = pygame.Rect(x, bar.bottom + 26, 56, 30)
        plus = pygame.Rect(x + w - 56, bar.bottom + 26, 56, 30)
        widgets.draw_button(surface, self.mid, minus, "-")
        widgets.draw_button(surface, self.mid, plus, "+")
        widgets.draw_text(surface, self.font, (x + w // 2, minus.centery), step_text, theme.MUTED)
        self.controls.append((minus, lambda _p: eq.nudge(-1), None))
        self.controls.append((plus, lambda _p: eq.nudge(1), None))

    def draw_softkeys(self, surface):
        top = CANVAS_BOTTOM
        pygame.draw.rect(surface, theme.PANEL, (0, top, W, H - top))
        pygame.draw.line(surface, theme.PANEL_EDGE, (0, top), (W, top))
        x = 8
        keys = [
            ("PAUSE  [SPACE]" if self.running else "RUN  [SPACE]", self.toggle_run, theme.KEY_ACTIVE if self.running else theme.KEY, 160),
            (f"SPEED {self.speed}x  [F]", self.cycle_speed, theme.KEY, 130),
            (
                f"RESTART ({self.run.restarts_left})",
                self.restart,
                theme.KEY if self.run.restarts_left else theme.KEY_DISABLED,
                140,
            ),
        ]
        for label, action, fill, width in keys:
            rect = pygame.Rect(x, top + 6, width, H - top - 12)
            widgets.draw_button(surface, self.font, rect, label, fill)
            self.controls.append((rect, lambda _p, a=action: a(), None))
            x += width + 8
        state = "RUNNING" if self.running else "PAUSED"
        widgets.draw_text(surface, self.font, (x + 8, top + 14), state, theme.OK if self.running else theme.MUTED, "midleft")
        hint = "drag cards | out->in port: pipe | right-click unit/pipe: remove | F11 fullscreen | Ctrl+Q quit"
        widgets.draw_text(surface, self.font, (x + 8, top + 33), hint, theme.MUTED, "midleft")

    def draw_legend(self, surface):
        reactions = self.run.chem.known(self.run.level)
        height = 48 + 18 * len(reactions)
        rect = pygame.Rect(10, CANVAS_BOTTOM - height - 10, 190, height)
        widgets.draw_frame(surface, self.font, rect, "REACTIONS")
        for i, reaction in enumerate(reactions):
            widgets.draw_text(surface, self.font, (rect.x + 10, rect.y + 26 + i * 18), reaction.label, theme.TEXT, "topleft")
        x = rect.x + 10
        for species, color in theme.SPECIES.items():
            chip = pygame.Rect(x, rect.bottom - 20, 12, 12)
            pygame.draw.rect(surface, color, chip)
            widgets.draw_text(surface, self.font, (chip.right + 4, chip.centery), species, theme.TEXT, "midleft")
            x += 35

    def draw_result(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill(theme.OVERLAY_SHADE)
        surface.blit(shade, (0, 0))
        box = self.result_rect()
        good = self.result["kind"] == "met"
        pygame.draw.rect(surface, theme.PANEL, box)
        pygame.draw.rect(surface, theme.OK if good else theme.ALARM, box, 2)
        widgets.draw_text(surface, self.big, (box.centerx, box.y + 32), self.result["title"], theme.OK if good else theme.ALARM)
        y = box.y + 70
        for line in self.result["lines"]:
            widgets.draw_text(surface, self.font, (box.x + 40, y), line, theme.TEXT, "topleft")
            y += 20
        widgets.draw_button(surface, self.mid, self.continue_rect(), self.result["button"], theme.KEY_ACTIVE if good else theme.KEY)
