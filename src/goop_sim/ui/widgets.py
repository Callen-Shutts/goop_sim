import pygame

from goop_sim.sim.equipment import Equipment, Pump, Sink, Source, Tank
from goop_sim.ui import theme
from goop_sim.ui.geometry import PORT_RADIUS, all_ports, pipe_points, port_pos, rect_of


def draw_value_box(surface, font, center, text):
    img = font.render(text, True, theme.VALUE_TEXT)
    rect = img.get_rect(center=center).inflate(8, 4)
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, theme.VALUE_TEXT, rect, 1)
    surface.blit(img, img.get_rect(center=center))


def draw_label(surface, font, center, text, color=theme.LABEL_TEXT):
    img = font.render(text, True, color)
    surface.blit(img, img.get_rect(center=center))


def draw_equipment(surface, font, eq: Equipment, pos=None, ports=True, highlight=None):
    rect = rect_of(eq, pos)
    if isinstance(eq, Tank):
        pygame.draw.rect(surface, theme.TANK_EMPTY, rect)
        fill_h = int(rect.height * eq.fraction)
        pygame.draw.rect(surface, theme.TANK_FILL, (rect.x, rect.bottom - fill_h, rect.width, fill_h))
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2)
        draw_label(surface, font, (rect.centerx, rect.y - 34), eq.name)
        draw_value_box(surface, font, (rect.centerx, rect.y - 14), f"{eq.level_ft:.2f} FT")
    elif isinstance(eq, Pump):
        color = theme.PUMP_RUNNING if eq.running else theme.PUMP_STOPPED
        pygame.draw.circle(surface, color, rect.center, rect.width // 2)
        pygame.draw.circle(surface, theme.TANK_OUTLINE, rect.center, rect.width // 2, 2)
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 14), f"{eq.flow_gpm:.0f} GPM")
    else:
        pygame.draw.rect(surface, theme.FIXTURE_FILL, rect)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2)
        draw_label(surface, font, rect.center, eq.name)
    if ports:
        for port in all_ports(eq):
            center = port_pos(port, pos)
            color = theme.PORT_HOT if port == highlight else theme.PORT
            pygame.draw.circle(surface, color, center, PORT_RADIUS)
            pygame.draw.circle(surface, theme.TANK_OUTLINE, center, PORT_RADIUS, 1)


def draw_pipe(surface, pipe, active):
    color = theme.PIPE if active else theme.PIPE_IDLE
    pygame.draw.lines(surface, color, False, pipe_points(pipe), 3)


def describe(eq: Equipment) -> str:
    if isinstance(eq, Pump):
        return f"{eq.max_gpm:.0f} GPM"
    if isinstance(eq, Tank):
        return f"{eq.capacity_gal / 1000:.0f}K GAL, {eq.diameter_ft:.0f} FT DIA"
    return ""


def draw_card(surface, font, rect, eq):
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 1)
    surface.blit(font.render(eq.name, True, theme.LABEL_TEXT), (rect.x + 10, rect.y + 8))
    surface.blit(font.render(describe(eq), True, theme.VALUE_TEXT), (rect.x + 10, rect.y + 28))


def draw_toolbar(surface, font, width, status):
    pygame.draw.rect(surface, theme.TOOLBAR, (0, 0, width, theme.TOOLBAR_HEIGHT))
    x = 20
    for item in ("ALARMS", "TRENDS", "LOGS", "REPORTS", "COMMS"):
        img = font.render(item, True, theme.TOOLBAR_TEXT)
        surface.blit(img, (x, (theme.TOOLBAR_HEIGHT - img.get_height()) // 2))
        x += img.get_width() + 40
    img = font.render(status, True, theme.TOOLBAR_TEXT)
    surface.blit(img, (width - img.get_width() - 20, (theme.TOOLBAR_HEIGHT - img.get_height()) // 2))
