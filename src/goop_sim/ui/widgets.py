import pygame

from goop_sim.sim.equipment import Equipment, Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.network import Port
from goop_sim.sim.stream import Stream
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


def draw_fill(surface, rect, stream: Stream, capacity: float, vertical=True):
    """Stacked species bands, bottom-up (vertical) or left-to-right."""
    if capacity <= 0:
        return
    offset = 0
    for species, color in theme.SPECIES.items():
        share = stream.get(species, 0.0) / capacity
        if vertical:
            h = round(rect.height * share)
            if h > 0:
                pygame.draw.rect(surface, color, (rect.x, rect.bottom - offset - h, rect.width, h))
            offset += h
        else:
            w = round(rect.width * share)
            if w > 0:
                pygame.draw.rect(surface, color, (rect.x + offset, rect.y, w, rect.height))
            offset += w


def draw_equipment(surface, font, eq: Equipment, pos=None, ports=True, highlight=None):
    rect = rect_of(eq, pos)
    if isinstance(eq, Tank):
        pygame.draw.rect(surface, theme.TANK_EMPTY, rect)
        draw_fill(surface, rect, eq.content, eq.capacity_gal)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2)
        draw_label(surface, font, (rect.centerx, rect.y - 34), eq.name)
        draw_value_box(surface, font, (rect.centerx, rect.y - 14), f"{eq.volume_gal:,.0f} GAL")
    elif isinstance(eq, Pump):
        color = theme.PUMP_RUNNING if eq.running else theme.PUMP_STOPPED
        pygame.draw.circle(surface, color, rect.center, rect.width // 2)
        pygame.draw.circle(surface, theme.TANK_OUTLINE, rect.center, rect.width // 2, 2)
        tip = (rect.right - 8, rect.centery)
        pygame.draw.polygon(surface, theme.VALUE_BOX, [tip, (rect.x + 12, rect.y + 11), (rect.x + 12, rect.bottom - 11)])
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 14), f"{eq.flow_gpm:.0f} GPM")
    elif isinstance(eq, Reactor):
        pygame.draw.rect(surface, theme.VESSEL_FILL, rect, border_radius=18)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2, border_radius=18)
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
        draw_label(surface, font, (rect.centerx, rect.centery - 10), eq.reaction.label if eq.reaction else "?")
        side = " +SIDE" if eq.side else ""
        draw_label(surface, font, (rect.centerx, rect.centery + 10), f"{eq.conversion:.0%}{side}", theme.VALUE_TEXT)
    elif isinstance(eq, Separator):
        pygame.draw.rect(surface, theme.VESSEL_FILL, rect, border_radius=20)
        for y in range(rect.y + 25, rect.bottom - 15, 16):
            pygame.draw.line(surface, theme.TANK_OUTLINE, (rect.x + 8, y), (rect.right - 8, y), 1)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2, border_radius=20)
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
        if ports:
            for i, text in enumerate(("TOP", "BTM")):
                x, y = port_pos(Port(eq, "out", i), pos)
                draw_label(surface, font, (x + 26, y - 12), text, theme.MUTED_TEXT)
    elif isinstance(eq, Splitter):
        c = rect.center
        r = rect.width // 2
        points = [(c[0], c[1] - r), (c[0] + r, c[1]), (c[0], c[1] + r), (c[0] - r, c[1])]
        pygame.draw.polygon(surface, theme.VESSEL_FILL, points)
        pygame.draw.polygon(surface, theme.TANK_OUTLINE, points, 2)
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
        ratio = f"{eq.ratio:.0%} / {1 - eq.ratio:.0%}"
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 14), ratio)
    elif isinstance(eq, Mixer):
        points = [rect.topleft, (rect.right, rect.centery), rect.bottomleft]
        pygame.draw.polygon(surface, theme.VESSEL_FILL, points)
        pygame.draw.polygon(surface, theme.TANK_OUTLINE, points, 2)
        draw_label(surface, font, (rect.centerx, rect.y - 12), eq.name)
    else:
        pygame.draw.rect(surface, theme.FIXTURE_FILL, rect)
        pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 2)
        draw_label(surface, font, (rect.centerx, rect.y + 14), eq.name)
        stream = eq.stock if isinstance(eq, Feed) else eq.received
        draw_label(surface, font, (rect.centerx, rect.y + 34), f"{stream.total():,.0f} GAL", theme.VALUE_TEXT)
        bar = pygame.Rect(rect.x + 8, rect.bottom - 12, rect.width - 16, 6)
        pygame.draw.rect(surface, theme.TANK_EMPTY, bar)
        draw_fill(surface, bar, stream, stream.total(), vertical=False)
    if ports:
        for port in all_ports(eq):
            center = port_pos(port, pos)
            color = theme.PORT_HOT if port == highlight else theme.PORT
            pygame.draw.circle(surface, color, center, PORT_RADIUS)
            pygame.draw.circle(surface, theme.TANK_OUTLINE, center, PORT_RADIUS, 1)


def draw_pipe(surface, pipe):
    species = pipe.carried.dominant()
    color = theme.SPECIES[species] if species else theme.PIPE_IDLE
    pygame.draw.lines(surface, color, False, pipe_points(pipe), 4 if species else 3)


def describe(eq: Equipment) -> str:
    """One-line summary for an inventory card."""
    if isinstance(eq, Pump):
        return f"PUMP {eq.max_gpm:.0f} GPM"
    if isinstance(eq, Tank):
        return f"TANK {eq.capacity_gal:,.0f} GAL"
    if isinstance(eq, Reactor):
        side = " +SIDE" if eq.side else ""
        return f"{eq.reaction.label}  {eq.conversion:.0%}{side}"
    if isinstance(eq, Separator):
        tops = "".join(s for s, f in eq.top.items() if f >= 0.5)
        return f"COLUMN  TOP: {tops or '-'}"
    if isinstance(eq, Splitter):
        return "SPLITTER"
    if isinstance(eq, Mixer):
        return "MIXER"
    return ""


def composition_lines(stream: Stream) -> list[str]:
    total = stream.total()
    lines = []
    for species in theme.SPECIES:
        gal = stream.get(species, 0.0)
        if gal > 0.5:
            lines.append(f"  {species}  {gal:,.0f} GAL  ({gal / total:.0%})")
    return lines or ["  (empty)"]


def details(eq: Equipment) -> list[str]:
    """Tooltip lines."""
    if isinstance(eq, Pump):
        state = "RUNNING" if eq.running else "STOPPED"
        return [f"{eq.name}  PUMP", f"Max {eq.max_gpm:.0f} GPM, {state}", "Draws from a feed or tank on its inlet.", "Click to start/stop."]
    if isinstance(eq, Tank):
        return [f"{eq.name}  TANK", f"Capacity {eq.capacity_gal:,.0f} GAL", *composition_lines(eq.content)]
    if isinstance(eq, Reactor):
        lines = [f"{eq.name}  REACTOR", f"{eq.reaction.label}   {eq.conversion:.0%} conversion"]
        if eq.side:
            lines.append(f"Side: {eq.side.label}   {eq.side_conversion:.0%}")
        return lines
    if isinstance(eq, Separator):
        lines = [f"{eq.name}  COLUMN", "Share of each species sent to TOP:"]
        lines += [f"  {s}  {f:.0%}" for s, f in eq.top.items()]
        return lines
    if isinstance(eq, Splitter):
        return [f"{eq.name}  SPLITTER", f"TOP {eq.ratio:.0%} / BOTTOM {1 - eq.ratio:.0%}", "Click to change the split."]
    if isinstance(eq, Mixer):
        return [f"{eq.name}  MIXER", "Joins two streams into one."]
    if isinstance(eq, Feed):
        return [f"{eq.name}  FEED (remaining)", *composition_lines(eq.stock)]
    if isinstance(eq, Outlet):
        return [f"{eq.name}  (received)", *composition_lines(eq.received)]
    return [eq.name]


def draw_card(surface, font, rect, eq, selected=False):
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, theme.SELECTED if selected else theme.TANK_OUTLINE, rect, 3 if selected else 1)
    surface.blit(font.render(eq.name, True, theme.LABEL_TEXT), (rect.x + 8, rect.y + 3))
    surface.blit(font.render(describe(eq), True, theme.VALUE_TEXT), (rect.x + 8, rect.y + 20))


def draw_tooltip(surface, font, pos, lines):
    imgs = [font.render(line, True, theme.LABEL_TEXT) for line in lines]
    w = max(img.get_width() for img in imgs) + 16
    h = sum(img.get_height() for img in imgs) + 12
    x = min(pos[0] + 16, surface.get_width() - w - 4)
    y = min(pos[1] + 16, surface.get_height() - h - 4)
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(surface, theme.TOOLTIP, rect)
    pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 1)
    y += 6
    for img in imgs:
        surface.blit(img, (x + 8, y))
        y += img.get_height()


def draw_button(surface, font, rect, text, color=theme.BUTTON):
    pygame.draw.rect(surface, color, rect, border_radius=4)
    draw_label(surface, font, rect.center, text, theme.BUTTON_TEXT)


def draw_panel_box(surface, font, rect, title, lines):
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, theme.TANK_OUTLINE, rect, 1)
    y = rect.y + 6
    surface.blit(font.render(title, True, theme.LABEL_TEXT), (rect.x + 8, y))
    for line in lines:
        y += 18
        surface.blit(font.render(line, True, theme.VALUE_TEXT), (rect.x + 8, y))


def draw_toolbar(surface, font, width, left, right, right_color=theme.TOOLBAR_TEXT):
    pygame.draw.rect(surface, theme.TOOLBAR, (0, 0, width, theme.TOOLBAR_HEIGHT))
    img = font.render(left, True, theme.TOOLBAR_TEXT)
    surface.blit(img, (20, (theme.TOOLBAR_HEIGHT - img.get_height()) // 2))
    img = font.render(right, True, right_color)
    surface.blit(img, (width - img.get_width() - 20, (theme.TOOLBAR_HEIGHT - img.get_height()) // 2))
