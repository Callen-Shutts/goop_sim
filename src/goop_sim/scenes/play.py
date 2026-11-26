import math

import pygame

from goop_sim import settings
from goop_sim.run.history import History
from goop_sim.run.state import RunState
from goop_sim.scenes.base import Scene
from goop_sim.sim.equipment import Outlet, Pump, Reactor, Splitter
from goop_sim.sim.network import Port
from goop_sim.sim.stream import Stream
from goop_sim.ui import theme, widgets
from goop_sim.ui.layout import tidy
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
        self.history = History(run)  # undo/redo of layout edits (Ctrl+Z / Ctrl+Y)
        theme.set_species(run.chem.species, run.chem.waste)
        self.grid = self._make_grid()
        self.place_fixtures()

    @property
    def net(self):
        return self.run.net

    def place_fixtures(self):
        mid = (CANVAS_TOP + CANVAS_BOTTOM) // 2
        spots = {self.run.feed: (70, mid), self.run.waste: (CANVAS_RIGHT - 80, mid + 150)}
        for outlet, dy in zip(self.run.products, (-230, -110, 10)):  # PRODUCT, PRODUCT 2, PRODUCT 3, top to bottom
            spots[outlet] = (CANVAS_RIGHT - 80, mid + dy)
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
        for pipe, (path, _hops) in route_pipes(self.net.pipes, self.net.equipment).items():
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
            self.result = None

    def return_to_inventory(self, eq, record=True):
        """Take a placed unit off the canvas: its pipes go, its contents are lost, settings are kept."""
        if eq is None or eq.fixed or eq not in self.net.equipment:
            return
        if record:
            self.history.record()
        for pipe in [p for p in self.net.pipes if eq in (p.out.equipment, p.into.equipment)]:
            pipe.empty()  # its contents are lost with the unit
        if self.pending and self.pending.equipment is eq:
            self.pending = None
        self.net.remove(eq)
        eq.pos = None
        eq.reset()
        self.run.inventory.append(eq)
        if self.selected is eq:
            self.selected = None

    def undo(self):
        if self.history.undo():
            self._after_history()

    def redo(self):
        if self.history.redo():
            self._after_history()

    def _after_history(self):
        self.pending = None
        self.drag = None
        if self.selected is not None and self.selected not in self.net.equipment:
            self.selected = None
        self.scroll = min(self.scroll, self.max_scroll())

    def legend_rect(self) -> pygame.Rect:
        height = 48 + 18 * len(self.run.chem.known(self.run.level))
        return pygame.Rect(10, CANVAS_BOTTOM - height - 10, 240, height)

    def tidy_up(self):
        """Auto-arrange the plant into left-to-right columns (one undo step)."""
        if self.drag:
            return
        area = pygame.Rect(20, CANVAS_TOP + 20, CANVAS_RIGHT - 40, CANVAS_BOTTOM - CANVAS_TOP - 40)
        moves = tidy(self.net, area, [self.legend_rect()])
        if all(eq.pos == p for eq, p in moves.items()):
            return
        self.history.record()
        for eq, p in moves.items():
            eq.pos = p

    def nudge(self, eq, steps):
        if isinstance(eq, (Pump, Splitter)):
            eq.nudge(steps)

    def show_result(self, kind):
        run, c = self.run, self.run.contract
        if kind == "met":
            pay = run.complete_contract()
            title, button = f"CONTRACT {run.level} COMPLETE", "GO TO STORE"
            lines = [
                "BASE PAY".ljust(32) + f"${pay.base:>7,.0f}",
                f"PURITY BONUS ({pay.avg_purity:.1%} avg)".ljust(32) + f"+${pay.purity_bonus:>6,.0f}",
                f"OFF-SPEC FEE ({run.offspec_total:,.0f} GAL)".ljust(32) + f"-${pay.offspec_fee:>6,.0f}",
                f"SPILL FEE ({run.spill_total:,.0f} GAL)".ljust(32) + f"-${pay.spill_fee:>6,.0f}",
                "PAID".ljust(32) + f"${pay.total:>7,}",
            ]
            self.result = {"kind": kind, "title": title, "lines": lines, "button": button}
            self.running = False
            return
        lines = [
            f"ON-SPEC {o.species} (>={o.purity:.0%})  {o.delivered(out):,.0f} / {o.quantity_gal:,.0f} GAL"
            for o, out in zip(c.orders, run.products)
        ] + [
            f"OFF-SPEC REJECTED  {run.offspec_total:,.0f} GAL",
            f"SPILLED            {run.spill_total:,.0f} GAL",
        ]
        if run.restarts_left > 0:
            title, button = "OUT OF FEED", f"RESTART CONTRACT ({run.restarts_left} LEFT)"
            lines.append("Restart restocks feed and empties the plant.")
        else:
            title, button = "RUN OVER", "START A NEW RUN"
            lines.append(f"You reached contract {run.level}.")
        self.result = {"kind": kind, "title": title, "lines": lines, "button": button}
        self.running = False

    def on_continue(self):
        if self.result["kind"] == "met":
            from goop_sim.scenes.store import StoreScene

            self.game.change_scene(StoreScene(self.game, self.run))
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
            ctrl = event.mod & pygame.KMOD_CTRL
            shift = event.mod & pygame.KMOD_SHIFT
            if self.result:
                if event.key == pygame.K_RETURN:
                    self.on_continue()
            elif ctrl and event.key == pygame.K_z:
                self.redo() if shift else self.undo()
            elif ctrl and event.key == pygame.K_y:
                self.redo()
            elif event.key == pygame.K_ESCAPE:
                self.pending = None
                self.selected = None
            elif event.key == pygame.K_SPACE:
                self.toggle_run()
            elif event.key == pygame.K_f:
                self.cycle_speed()
            elif event.key == pygame.K_t:
                self.tidy_up()
            elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                target = self.selected
                if target is None and self.in_canvas(self.mouse):
                    target = self.equipment_at(self.mouse)
                self.return_to_inventory(target)
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
                    before = self.history.snapshot()
                    if self.net.connect(self.pending, port):
                        self.history.push(before)
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
                    "before": self.history.snapshot(),  # undo point, kept only if the drag changes something
                }
            return
        item = self.card_at(pos)
        if item:
            self.drag = {
                "eq": item,
                "offset": (0, 0),
                "start": pos,
                "moved": False,
                "from_inventory": True,
                "pos": pos,
                "before": self.history.snapshot(),
            }

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
            self.history.record()
            self.net.disconnect(pipe)
            pipe.empty()

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
                self.history.push(d["before"])  # undo puts it back where the drag started
                self.return_to_inventory(eq, record=False)
            return
        target = snap((pos[0] + d["offset"][0], pos[1] + d["offset"][1]))
        if d["from_inventory"] or target != dict(d["before"][0]).get(eq):
            self.history.push(d["before"])
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
        """Overall color of what a pipe holds (or last carried, for a pipe with no holdup)."""
        held = Stream()
        for slug in pipe.slugs:
            held.add(slug)
        return widgets.blend(held) or widgets.blend(pipe.carried)

    def draw(self, surface):
        self.controls = []
        surface.fill(theme.BACKGROUND)
        surface.blit(self.grid, (0, CANVAS_TOP))
        self.draw_legend(surface)

        net = self.net
        routes = route_pipes(net.pipes, net.equipment)
        hovered = self.hovered_pipe()
        colors = {pipe: self.pipe_color(pipe) for pipe in net.pipes}
        flowing = self.running and net.last_dt > 0
        for pipe, (path, _hops) in routes.items():
            gpm = pipe.carried.total() * 60 / net.last_dt if flowing else 0.0
            widgets.draw_pipe(surface, path, widgets.pipe_fill(pipe), gpm, self.t, pipe is hovered)
        for pipe, (_path, hops) in routes.items():  # jumps go on top of the pipes they cross
            for arc in hops:
                widgets.draw_hop(surface, arc, colors[pipe], pipe is hovered)
        for eq in net.equipment:
            hot = self.pending if self.pending and self.pending.equipment is eq else None
            spec = eq.spec if isinstance(eq, Outlet) else None
            widgets.draw_equipment(surface, self.font, eq, highlight=hot, selected=eq is self.selected, spec=spec)
        self.draw_spills(surface)
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
                lines = widgets.details(hover)
                spilled = net.spilled_by(hover) if hover in net.equipment else 0.0
                if spilled > 0.5:
                    lines = [*lines, f"SPILLED HERE {spilled:,.0f} GAL"]
                widgets.draw_tooltip(surface, self.font, self.mouse, lines)
            elif hovered:
                lines = widgets.pipe_details(hovered, net.last_dt, self.running)
                widgets.draw_tooltip(surface, self.font, self.mouse, lines)

    def draw_spills(self, surface):
        """Alarm wherever liquid spilled last step: a red drip and readout at an open outlet, a
        flashing red frame and readout on a full tank, stopped pump or tank-less loop."""
        net = self.net
        if net.last_dt <= 0:
            return
        flash = int(self.t * 3) % 2 == 0
        for key, stream in net.spills.items():
            gpm = stream.total() * 60 / net.last_dt
            if isinstance(key, Port):
                if key.equipment not in net.equipment or net.pipe_at(key):
                    continue  # piped up since
                x, y = port_pos(key)
                color = widgets.blend(stream) or theme.ALARM
                for i in range(4):  # drops falling from the open outlet into a puddle
                    k = (self.t * 1.4 + i / 4) % 1.0
                    pygame.draw.circle(surface, color, (x + 4 + 6 * k, y + 6 + 34 * k * k), 4.5 - 1.5 * k)
                puddle = pygame.Rect(0, 0, 30 + 4 * math.sin(self.t * 4), 8)
                puddle.center = (x + 10, y + 42)
                pygame.draw.ellipse(surface, color, puddle)
                pygame.draw.ellipse(surface, theme.ALARM, puddle, 1)
                pygame.draw.circle(surface, theme.ALARM, (x, y), PORT_RADIUS + 3, 2)
                widgets.draw_value_box(surface, self.font, (x + 58, y + 8), f"SPILL {gpm:,.0f} GPM", theme.ALARM, theme.ALARM)
            else:
                if key not in net.equipment:
                    continue
                rect = rect_of(key)
                if flash:
                    pygame.draw.rect(surface, theme.ALARM, rect.inflate(12, 12), 2)
                # Below the unit's readouts, or above its tag when that would run off the canvas.
                y = rect.bottom + 54 if rect.bottom + 82 < CANVAS_BOTTOM else rect.top - 70
                widgets.draw_value_box(surface, self.font, (rect.centerx, y), f"SPILL {gpm:,.0f} GPM", theme.ALARM, theme.ALARM)
                widgets.draw_text(surface, self.font, (rect.centerx, y + 18), net.spill_reason(key), theme.ALARM)

    def draw_header(self, surface):
        run, c = self.run, self.run.contract
        pygame.draw.rect(surface, theme.PANEL, (0, 0, W, CANVAS_TOP))
        pygame.draw.line(surface, theme.PANEL_EDGE, (0, CANVAS_TOP - 1), (W, CANVAS_TOP - 1))
        widgets.draw_text(surface, self.mid, (14, CANVAS_TOP // 2), f"CONTRACT {run.level}", theme.TAG_TEXT, "midleft")
        # One block per order: product and purity spec, progress bar, gallons on-spec so far.
        x = 130
        width = 250 if len(c.orders) > 1 else 420
        for order, outlet in zip(c.orders, run.products):
            color = theme.SPECIES.get(order.species, theme.OK)
            label = widgets.draw_text(surface, self.mid, (x, CANVAS_TOP // 2), f"{order.species} {order.purity:.0%}+", color, "midleft")
            done = order.delivered(outlet)
            bar = pygame.Rect(label.right + 8, 13, width - (label.width + 8) - 92, 14)
            widgets.draw_bar(surface, bar, done / order.quantity_gal, color)
            text = theme.OK if done >= order.quantity_gal else theme.VALUE_TEXT
            widgets.draw_text(surface, self.font, (bar.right + 6, bar.centery), f"{done:,.0f}/{order.quantity_gal:,.0f}", text, "midleft")
            x += width
        rej, spill = run.offspec_total, run.spill_total
        cash = widgets.draw_text(surface, self.mid, (W - 14, CANVAS_TOP // 2), f"${run.money:,}", theme.WARN, "midright")
        est = run.preview_payout().total
        waste = f"OFF-SPEC {rej:,.0f}  SPILL {spill:,.0f}  EST PAY ${est:,}"
        color = theme.ALARM if rej > 0.5 or spill > 0.5 else theme.TEXT
        widgets.draw_text(surface, self.font, (cash.left - 18, CANVAS_TOP // 2), waste, color, "midright")

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
            ("UNDO ^Z", self.undo, theme.KEY if self.history.undo_stack else theme.KEY_DISABLED, 80),
            ("REDO ^Y", self.redo, theme.KEY if self.history.redo_stack else theme.KEY_DISABLED, 80),
            ("TIDY  [T]", self.tidy_up, theme.KEY, 90),
        ]
        for label, action, fill, width in keys:
            rect = pygame.Rect(x, top + 6, width, H - top - 12)
            widgets.draw_button(surface, self.font, rect, label, fill)
            self.controls.append((rect, lambda _p, a=action: a(), None))
            x += width + 8
        state = "RUNNING" if self.running else "PAUSED"
        widgets.draw_text(surface, self.font, (x + 8, top + 14), state, theme.OK if self.running else theme.MUTED, "midleft")
        hint = "Del/right-click: unit to inventory | F11 fullscreen | Ctrl+Q quit"
        widgets.draw_text(surface, self.font, (x + 8, top + 33), hint, theme.MUTED, "midleft")

    def draw_legend(self, surface):
        reactions = self.run.chem.known(self.run.level)
        rect = self.legend_rect()
        widgets.draw_frame(surface, self.font, rect, "REACTIONS")
        for i, reaction in enumerate(reactions):
            widgets.draw_text(surface, self.font, (rect.x + 10, rect.y + 26 + i * 18), reaction.label, theme.TEXT, "topleft")
        x = rect.x + 10
        for species, color in theme.SPECIES.items():
            chip = pygame.Rect(x, rect.bottom - 20, 12, 12)
            pygame.draw.rect(surface, color, chip)
            label = f"{species} WASTE" if species == self.run.chem.waste else species
            widgets.draw_text(surface, self.font, (chip.right + 4, chip.centery), label, theme.TEXT, "midleft")
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
