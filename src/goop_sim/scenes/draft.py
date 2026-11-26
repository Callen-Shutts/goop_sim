import pygame

from goop_sim import settings
from goop_sim.run.state import DRAFT_PICKS, RunState
from goop_sim.scenes.base import Scene
from goop_sim.ui import theme, widgets

CARD_W, CARD_H, CARD_GAP = 220, 190, 20


class DraftScene(Scene):
    """Between contracts: pick DRAFT_PICKS of the offered equipment; the new reaction's reactor is free."""

    def __init__(self, game, run: RunState):
        super().__init__(game)
        self.run = run
        self.font = pygame.font.SysFont("arial", 14)
        self.big = pygame.font.SysFont("arial", 24, bold=True)
        self.options = run.draft_options()
        self.grant = run.next_grant()
        self.selected = []

    def card_rect(self, i: int) -> pygame.Rect:
        n = len(self.options)
        x0 = (settings.SCREEN_WIDTH - (n * CARD_W + (n - 1) * CARD_GAP)) // 2
        return pygame.Rect(x0 + i * (CARD_W + CARD_GAP), 250, CARD_W, CARD_H)

    def confirm_rect(self) -> pygame.Rect:
        return pygame.Rect(settings.SCREEN_WIDTH // 2 - 120, 500, 240, 48)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
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
        widgets.draw_toolbar(
            surface, self.font, settings.SCREEN_WIDTH, f"CONTRACT {self.run.level} COMPLETE", "EQUIPMENT DRAFT"
        )
        cx = settings.SCREEN_WIDTH // 2
        widgets.draw_label(surface, self.big, (cx, 100), f"PICK {DRAFT_PICKS} TO ADD TO YOUR PLANT")
        next_species = self.run.chem.target(self.run.level + 1)
        widgets.draw_label(surface, self.font, (cx, 140), f"Next contract asks for {next_species}. Your plant carries over.")
        if self.grant:
            text = "Free: " + ", ".join(f"{eq.name} ({widgets.describe(eq)})" for eq in self.grant)
            widgets.draw_label(surface, self.font, (cx, 165), text, theme.OK)
        else:
            widgets.draw_label(surface, self.font, (cx, 165), "No new reaction: expect more volume, higher purity, dirtier feed.", theme.ALARM)

        for i, eq in enumerate(self.options):
            rect = self.card_rect(i)
            chosen = eq in self.selected
            pygame.draw.rect(surface, theme.VALUE_BOX, rect)
            pygame.draw.rect(surface, theme.SELECTED if chosen else theme.TANK_OUTLINE, rect, 4 if chosen else 1)
            y = rect.y + 10
            for j, line in enumerate(widgets.details(eq)):
                color = theme.LABEL_TEXT if j == 0 else theme.VALUE_TEXT
                surface.blit(self.font.render(line, True, color), (rect.x + 10, y))
                y += 19

        ready = len(self.selected) == DRAFT_PICKS
        label = "CONTINUE" if ready else f"SELECT {DRAFT_PICKS - len(self.selected)} MORE"
        widgets.draw_button(surface, self.font, self.confirm_rect(), label, theme.BUTTON if ready else theme.BUTTON_DISABLED)
