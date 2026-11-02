import random

import pygame

from goop_sim import settings
from goop_sim.content.equipment import deal_hand
from goop_sim.scenes.base import Scene
from goop_sim.sim.equipment import Pump, Sink, Source
from goop_sim.sim.network import Network, Port
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


class PlayScene(Scene):
    """Drag dealt equipment onto the canvas, click ports to pipe it together, click pumps to run them."""

    def __init__(self, game, rng: random.Random | None = None):
        super().__init__(game)
        self.font = pygame.font.SysFont("arial", 14)
        self.net = Network(target_gal=5000)
        mid = (settings.SCREEN_HEIGHT + theme.TOOLBAR_HEIGHT) // 2
        source = Source("SUPPLY", pos=snap((100, mid)))
        sink = Sink("PRODUCT", pos=snap((CANVAS_RIGHT - 100, mid)))
        self.net.add(source)
        self.net.add(sink)
        self.inventory = deal_hand(rng or random.Random())
        self.pending = None  # Port the player clicked first while piping
        self.drag = None  # {"eq", "offset", "start", "moved", "from_inventory", "pos"}
        self.mouse = (0, 0)

    # -- layout helpers -------------------------------------------------

    def card_rect(self, index: int) -> pygame.Rect:
        y = theme.TOOLBAR_HEIGHT + 40 + index * (theme.CARD_HEIGHT + theme.CARD_GAP)
        return pygame.Rect(CANVAS_RIGHT + 15, y, theme.PANEL_WIDTH - 30, theme.CARD_HEIGHT)

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
            if event.button == 1:
                self.on_left_down(event.pos)
            elif event.button == 3:
                self.on_right_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_left_up(event.pos)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.pending = None

    def on_left_down(self, pos):
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
        for i, item in enumerate(self.inventory):
            rect = self.card_rect(i)
            if rect.collidepoint(pos):
                self.drag = {
                    "eq": item,
                    "offset": (0, 0),
                    "start": pos,
                    "moved": True,
                    "from_inventory": True,
                    "pos": pos,
                }
                return

    def on_right_down(self, pos):
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
            if isinstance(eq, Pump):
                eq.toggle()
            return
        over_panel = pos[0] >= CANVAS_RIGHT
        if over_panel or pos[1] < theme.TOOLBAR_HEIGHT:
            if not d["from_inventory"]:
                self.net.remove(eq)
                eq.pos = None
                if isinstance(eq, Pump):
                    eq.running = False
                    eq.flow_gpm = 0.0
                self.inventory.append(eq)
            return
        target = snap((pos[0] + d["offset"][0], pos[1] + d["offset"][1]))
        if d["from_inventory"]:
            self.inventory.remove(eq)
            self.net.add(eq)
        eq.pos = target

    # -- loop -----------------------------------------------------------

    def update(self, dt):
        self.net.step(dt)

    def draw(self, surface):
        surface.fill(theme.BACKGROUND)
        net = self.net
        active = self.active_pipes()
        for pipe in net.pipes:
            widgets.draw_pipe(surface, pipe, pipe in active)
        for eq in net.equipment:
            hot = self.pending if self.pending and self.pending.equipment is eq else None
            widgets.draw_equipment(surface, self.font, eq, highlight=hot)
        if self.pending:
            pygame.draw.line(surface, theme.PORT_HOT, port_pos(self.pending), self.mouse, 2)

        pygame.draw.rect(
            surface,
            theme.PANEL,
            (CANVAS_RIGHT, theme.TOOLBAR_HEIGHT, theme.PANEL_WIDTH, settings.SCREEN_HEIGHT),
        )
        widgets.draw_label(
            surface, self.font, (CANVAS_RIGHT + theme.PANEL_WIDTH // 2, theme.TOOLBAR_HEIGHT + 20), "EQUIPMENT"
        )
        for i, item in enumerate(self.inventory):
            if self.drag and self.drag["eq"] is item and self.drag["from_inventory"]:
                continue
            widgets.draw_card(surface, self.font, self.card_rect(i), item)

        if self.drag and self.drag["moved"] and self.drag["from_inventory"]:
            widgets.draw_equipment(surface, self.font, self.drag["eq"], pos=self.drag["pos"], ports=False)

        status = f"PRODUCED {net.produced_gal:,.0f} / {net.target_gal:,.0f} GAL"
        if net.complete:
            status += "   TARGET MET"
        widgets.draw_toolbar(surface, self.font, settings.SCREEN_WIDTH, status)

    def active_pipes(self):
        """Pipes touching a pump that is currently moving liquid."""
        active = set()
        for pump in self.net.equipment:
            if isinstance(pump, Pump) and pump.flow_gpm > 0:
                for kind in ("in", "out"):
                    pipe = self.net.pipe_at(Port(pump, kind))
                    if pipe:
                        active.add(pipe)
        return active
