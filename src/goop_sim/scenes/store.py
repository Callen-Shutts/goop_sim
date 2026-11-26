import pygame

from goop_sim import settings
from goop_sim.run.state import RunState
from goop_sim.scenes.base import Scene
from goop_sim.ui import theme, widgets

W, H = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
CARD_W, CARD_H, GAP = 380, 196, 16
COLS = 3


def _fee(amount: float) -> str:
    return f"-${amount:,.0f}" if round(amount) else "$0"


class StoreScene(Scene):
    """Between contracts: spend money on equipment priced by its stats. The new reaction's reactor is free."""

    def __init__(self, game, run: RunState):
        super().__init__(game)
        self.run = run
        self.font = pygame.font.SysFont("consolas", 13)
        self.mid = pygame.font.SysFont("consolas", 15, bold=True)
        self.big = pygame.font.SysFont("consolas", 26, bold=True)
        self.grant = run.next_grant()
        self.mouse = (0, 0)
        self.bought = []
        self.flash = ""  # short message, e.g. "Not enough money"
        theme.set_species(run.chem.species, run.chem.waste)

    def card_rect(self, i: int) -> pygame.Rect:
        x0 = (W - (COLS * CARD_W + (COLS - 1) * GAP)) // 2
        row, col = divmod(i, COLS)
        return pygame.Rect(x0 + col * (CARD_W + GAP), 196 + row * (CARD_H + GAP), CARD_W, CARD_H)

    def reroll_rect(self) -> pygame.Rect:
        return pygame.Rect(W // 2 - 300, H - 66, 260, 46)

    def continue_rect(self) -> pygame.Rect:
        return pygame.Rect(W // 2 + 40, H - 66, 260, 46)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, eq in enumerate(list(self.run.offers)):
                if self.card_rect(i).collidepoint(event.pos):
                    self.buy(eq)
                    return
            if self.reroll_rect().collidepoint(event.pos):
                if self.run.reroll():
                    self.flash = ""
                else:
                    self.flash = "Not enough money to reroll."
            elif self.continue_rect().collidepoint(event.pos):
                self.leave()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.leave()

    def buy(self, eq):
        cost = self.run.price(eq)
        if self.run.buy(eq):
            self.bought.append(eq)
            self.flash = f"Bought {eq.name} for ${cost:,}. It's in your inventory."
        else:
            self.flash = f"Not enough money for {eq.name} (${cost:,})."

    def leave(self):
        from goop_sim.scenes.play import PlayScene

        self.run.advance(self.grant)
        self.game.change_scene(PlayScene(self.game, self.run))

    def draw(self, surface):
        run = self.run
        surface.fill(theme.BACKGROUND)
        pygame.draw.rect(surface, theme.PANEL, (0, 0, W, theme.TOOLBAR_HEIGHT))
        widgets.draw_text(surface, self.mid, (14, theme.TOOLBAR_HEIGHT // 2), f"CONTRACT {run.level} COMPLETE", theme.OK, "midleft")
        widgets.draw_text(surface, self.mid, (W - 14, theme.TOOLBAR_HEIGHT // 2), f"${run.money:,}", theme.WARN, "midright")
        widgets.draw_text(surface, self.font, (W - 100, theme.TOOLBAR_HEIGHT // 2), "EQUIPMENT STORE", theme.TAG_TEXT, "midright")

        self.draw_payout(surface)
        self.draw_next(surface)

        for i, eq in enumerate(run.offers):
            self.draw_offer(surface, self.card_rect(i), eq)
        if not run.offers:
            widgets.draw_text(surface, self.mid, (W // 2, 300), "SOLD OUT - reroll for new stock", theme.MUTED)

        if self.flash:
            color = theme.OK if self.flash.startswith("Bought") else theme.ALARM
            widgets.draw_text(surface, self.font, (W // 2, H - 84), self.flash, color)
        can_reroll = run.money >= run.reroll_cost
        widgets.draw_button(
            surface, self.mid, self.reroll_rect(), f"REROLL STOCK  ${run.reroll_cost}", theme.KEY if can_reroll else theme.KEY_DISABLED
        )
        widgets.draw_button(surface, self.mid, self.continue_rect(), "NEXT CONTRACT  [ENTER]", theme.KEY_ACTIVE)

    def draw_payout(self, surface):
        pay = self.run.last_payout
        rect = pygame.Rect(20, 54, 420, 126)
        widgets.draw_frame(surface, self.font, rect, "CONTRACT PAYOUT")
        if not pay:
            return
        rows = [
            ("BASE PAY", f"${pay.base:,.0f}", theme.TEXT),
            (f"PURITY BONUS  ({pay.avg_purity:.1%} avg)", f"+${pay.purity_bonus:,.0f}", theme.OK),
            ("OFF-SPEC + SPILL FEES", _fee(pay.offspec_fee + pay.spill_fee), theme.ALARM),
            ("PAID", f"${pay.total:,}", theme.WARN),
        ]
        for j, (label, value, color) in enumerate(rows):
            y = rect.y + 30 + j * 22
            widgets.draw_text(surface, self.font if j < 3 else self.mid, (rect.x + 12, y), label, theme.TEXT, "topleft")
            widgets.draw_text(surface, self.font if j < 3 else self.mid, (rect.right - 12, y), value, color, "topright")

    def draw_next(self, surface):
        rect = pygame.Rect(460, 54, W - 480, 126)
        widgets.draw_frame(surface, self.font, rect, "NEXT CONTRACT")
        nxt = self.run.next_contract
        x, y = rect.x + 12, rect.y + 30
        wants = nxt.summary if nxt else self.run.chem.target(self.run.level + 1)
        widgets.draw_text(surface, self.font, (x, y), f"WANTS {wants}", theme.TEXT, "topleft")
        if nxt and len(nxt.orders) > len(self.run.products):
            widgets.draw_text(surface, self.font, (rect.right - 12, y), "+ NEW PRODUCT OUTLET", theme.WARN, "topright")
        widgets.draw_text(
            surface, self.font, (x, y + 20), "Plant, settings and inventory carry over. Pay rewards purity above spec, not volume.", theme.MUTED, "topleft"
        )
        if self.grant:
            eq = self.grant[0]
            icon = pygame.Rect(x, y + 44, 40, 40)
            pygame.draw.rect(surface, theme.BACKGROUND, icon)
            widgets.draw_icon(surface, eq, icon.inflate(-6, -6))
            widgets.draw_text(surface, self.mid, (icon.right + 10, icon.centery - 9), "NEW REACTION - FREE REACTOR", theme.OK, "topleft")
            widgets.draw_text(surface, self.font, (icon.right + 10, icon.centery + 9), f"{eq.name}  {widgets.describe(eq)}", theme.TEXT, "topleft")
        else:
            widgets.draw_text(surface, self.mid, (x, y + 54), "No new reaction: expect more volume, higher purity, dirtier feed.", theme.WARN, "topleft")

    def draw_offer(self, surface, rect, eq):
        cost = self.run.price(eq)
        affordable = cost <= self.run.money
        hover = rect.collidepoint(self.mouse)
        pygame.draw.rect(surface, theme.CARD, rect)
        edge = (theme.TAG_TEXT if affordable else theme.ALARM) if hover else theme.CARD_EDGE
        pygame.draw.rect(surface, edge, rect, 2 if hover else 1)
        icon = pygame.Rect(rect.x + 10, rect.y + 10, 110, 110)
        pygame.draw.rect(surface, theme.BACKGROUND, icon)
        widgets.draw_icon(surface, eq, icon.inflate(-16, -16))
        price = pygame.Rect(rect.x + 10, icon.bottom + 10, 110, 30)
        widgets.draw_button(surface, self.mid, price, f"${cost:,}", theme.KEY_ACTIVE if affordable else theme.KEY_DISABLED)
        widgets.draw_text(surface, self.font, (price.centerx, price.bottom + 14), "CLICK TO BUY" if affordable else "CAN'T AFFORD", theme.MUTED)
        y = rect.y + 12
        for j, line in enumerate(widgets.details(eq)):
            widgets.draw_text(surface, self.font, (icon.right + 12, y), line, theme.TAG_TEXT if j == 0 else theme.TEXT, "topleft")
            y += 18
