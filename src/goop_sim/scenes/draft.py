import pygame

from goop_sim import settings
from goop_sim.run.state import DRAFT_PICKS, RunState
from goop_sim.scenes.base import Scene
from goop_sim.ui import theme, widgets

W = settings.SCREEN_WIDTH
CARD_W, CARD_H, CARD_GAP = 220, 260, 18


class DraftScene(Scene):
    """Between contracts: pick DRAFT_PICKS of the offered equipment; the new reaction's reactor is free."""

    def __init__(self, game, run: RunState):
        super().__init__(game)
        self.run = run
        self.font = pygame.font.SysFont("consolas", 13)
        self.mid = pygame.font.SysFont("consolas", 15, bold=True)
        self.big = pygame.font.SysFont("consolas", 26, bold=True)
        self.options = run.draft_options()
        self.grant = run.next_grant()
        self.selected = []
        self.mouse = (0, 0)

    def card_rect(self, i: int) -> pygame.Rect:
        n = len(self.options)
        x0 = (W - (n * CARD_W + (n - 1) * CARD_GAP)) // 2
        return pygame.Rect(x0 + i * (CARD_W + CARD_GAP), 230, CARD_W, CARD_H)

    def confirm_rect(self) -> pygame.Rect:
        return pygame.Rect(W // 2 - 140, 540, 280, 46)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, eq in enumerate(self.options):
                if self.card_rect(i).collidepoint(event.pos):
                    if eq in self.selected:
                        self.selected.remove(eq)
                    elif len(self.selected) < DRAFT_PICKS:
                        self.selected.append(eq)
                    return
            if self.confirm_rect().collidepoint(event.pos):
                self.confirm()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.confirm()

    def confirm(self):
        if len(self.selected) != DRAFT_PICKS:
            return
        from goop_sim.scenes.play import PlayScene

        self.run.advance(self.selected, self.grant)
        self.game.change_scene(PlayScene(self.game, self.run))

    def draw(self, surface):
        surface.fill(theme.BACKGROUND)
        pygame.draw.rect(surface, theme.PANEL, (0, 0, W, theme.TOOLBAR_HEIGHT))
        widgets.draw_text(surface, self.mid, (14, theme.TOOLBAR_HEIGHT // 2), f"CONTRACT {self.run.level} COMPLETE", theme.OK, "midleft")
        widgets.draw_text(surface, self.font, (W - 14, theme.TOOLBAR_HEIGHT // 2), "EQUIPMENT REQUISITION", theme.TAG_TEXT, "midright")

        cx = W // 2
        widgets.draw_text(surface, self.big, (cx, 90), f"PICK {DRAFT_PICKS} UNITS FOR YOUR PLANT", theme.TEXT)
        nxt = self.run.chem.target(self.run.level + 1)
        widgets.draw_text(surface, self.font, (cx, 128), f"Next contract wants {nxt}. Your plant, settings and inventory carry over.", theme.MUTED)
        if self.grant:
            names = ", ".join(f"{eq.name} {widgets.describe(eq)}" for eq in self.grant)
            widgets.draw_text(surface, self.mid, (cx, 160), f"NEW REACTION UNLOCKED - FREE: {names}", theme.OK)
            chip = pygame.Rect(0, 0, 44, 44)
            chip.center = (cx, 196)
            widgets.draw_icon(surface, self.grant[0], chip)
        else:
            widgets.draw_text(surface, self.mid, (cx, 160), "NO NEW REACTION: EXPECT MORE VOLUME, HIGHER PURITY, DIRTIER FEED", theme.WARN)

        for i, eq in enumerate(self.options):
            rect = self.card_rect(i)
            chosen = eq in self.selected
            hover = rect.collidepoint(self.mouse)
            pygame.draw.rect(surface, theme.CARD, rect)
            edge = theme.SELECT if chosen else (theme.TAG_TEXT if hover else theme.CARD_EDGE)
            pygame.draw.rect(surface, edge, rect, 3 if chosen else 1)
            icon_box = pygame.Rect(rect.x + 10, rect.y + 10, rect.width - 20, 110)
            pygame.draw.rect(surface, theme.BACKGROUND, icon_box)
            widgets.draw_icon(surface, eq, icon_box.inflate(-30, -20))
            y = icon_box.bottom + 10
            for j, line in enumerate(widgets.details(eq)):
                color = theme.TAG_TEXT if j == 0 else theme.TEXT
                widgets.draw_text(surface, self.font, (rect.x + 12, y), line, color, "topleft")
                y += 18
            if chosen:
                widgets.draw_text(surface, self.mid, (rect.right - 12, rect.y + 16), "PICKED", theme.SELECT, "topright")

        ready = len(self.selected) == DRAFT_PICKS
        label = "CONTINUE  [ENTER]" if ready else f"SELECT {DRAFT_PICKS - len(self.selected)} MORE"
        widgets.draw_button(surface, self.mid, self.confirm_rect(), label, theme.KEY_ACTIVE if ready else theme.KEY_DISABLED)
