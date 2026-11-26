"""Drawing for the dark HMI look: shaded vessels, colored pipes with moving flow, value boxes, icons."""

import math

import pygame

from goop_sim.sim.equipment import Equipment, Feed, Mixer, Outlet, Pump, Reactor, Separator, Splitter, Tank
from goop_sim.sim.network import Port
from goop_sim.sim.stream import Stream
from goop_sim.ui import theme
from goop_sim.ui.geometry import PORT_RADIUS, all_ports, fit_rect, port_pos, rect_of

# -- color helpers ----------------------------------------------------------


def mix(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def blend(stream: Stream):
    """Volume-weighted blend of species colors, or None for an empty stream."""
    total = stream.total()
    if total <= 1e-9:
        return None
    rgb = [0.0, 0.0, 0.0]
    for species, gal in stream.items():
        color = theme.SPECIES.get(species, theme.MUTED)
        for i in range(3):
            rgb[i] += color[i] * gal / total
    return tuple(round(c) for c in rgb)


# -- primitives -------------------------------------------------------------

_cylinders: dict = {}


def _cylinder(w: int, h: int, radius: int) -> pygame.Surface:
    """Gray body shaded left-to-right like a lit cylinder, with rounded ends. Cached per size."""
    key = (w, h, radius)
    surf = _cylinders.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            u = x / max(1, w - 1)
            k = max(0.0, math.cos((u - 0.35) * math.pi * 0.95))
            pygame.draw.line(surf, mix(theme.VESSEL_DARK, theme.VESSEL_LIGHT, k), (x, 0), (x, h - 1))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        _cylinders[key] = surf
    return surf


def draw_vessel(surface, rect, radius):
    surface.blit(_cylinder(rect.width, rect.height, radius), rect.topleft)
    pygame.draw.rect(surface, theme.OUTLINE, rect, 1, border_radius=radius)


def draw_text(surface, font, pos, text, color=theme.TEXT, anchor="center"):
    img = font.render(text, True, color)
    surface.blit(img, img.get_rect(**{anchor: pos}))
    return img.get_rect(**{anchor: pos})


def draw_value_box(surface, font, center, text, color=theme.VALUE_TEXT, edge=theme.VALUE_EDGE):
    img = font.render(text, True, color)
    rect = img.get_rect(center=center).inflate(8, 4)
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, edge, rect, 1)
    surface.blit(img, img.get_rect(center=center))
    return rect


def draw_button(surface, font, rect, text, fill=theme.KEY, text_color=theme.TEXT, edge=theme.KEY_EDGE):
    pygame.draw.rect(surface, fill, rect)
    pygame.draw.rect(surface, edge, rect, 1)
    # bevel like an old softkey
    pygame.draw.line(surface, mix(fill, (255, 255, 255), 0.25), rect.topleft, (rect.right - 1, rect.top))
    draw_text(surface, font, rect.center, text, text_color)


def draw_bar(surface, rect, fraction, color, edge=theme.VALUE_EDGE):
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    w = round(rect.width * max(0.0, min(1.0, fraction)))
    if w > 0:
        pygame.draw.rect(surface, color, (rect.x, rect.y, w, rect.height))
    pygame.draw.rect(surface, edge, rect, 1)


# -- pipes --------------------------------------------------------------------


def draw_pipe(surface, points, color, flow_gpm: float, t: float, highlight=False):
    """A pipe with its contents' color inside and dots moving with the flow."""
    wall = theme.PIPE_HOVER if highlight else theme.PIPE_WALL
    pygame.draw.lines(surface, wall, False, points, 10)
    for p in points:
        pygame.draw.circle(surface, wall, p, 5)
    inner = color or theme.PIPE_EMPTY
    pygame.draw.lines(surface, inner, False, points, 6)
    for p in points[1:-1]:
        pygame.draw.circle(surface, inner, p, 3)
    if flow_gpm <= 0 or not color:
        return
    dot = mix(color, (255, 255, 255), 0.65)
    spacing = 22
    speed = 25 + min(flow_gpm, 800) / 5  # px per second
    d = (t * speed) % spacing
    for a, b in zip(points, points[1:]):
        av, bv = pygame.Vector2(a), pygame.Vector2(b)
        length = av.distance_to(bv)
        while length > 0 and d <= length:
            pygame.draw.circle(surface, dot, av + (bv - av) * (d / length), 2)
            d += spacing
        d -= length


def draw_hop(surface, arc, color, highlight=False):
    """Redraw a line-jump arc on top of the pipe it crosses, with a background gap around it."""
    pygame.draw.lines(surface, theme.BACKGROUND, False, arc, 14)
    pygame.draw.lines(surface, theme.PIPE_HOVER if highlight else theme.PIPE_WALL, False, arc, 10)
    pygame.draw.lines(surface, color or theme.PIPE_EMPTY, False, arc, 6)


def pipe_details(pipe, dt: float, running: bool) -> list[str]:
    """Tooltip for a pipe: where it runs, flow, and composition of what it carried last step."""
    def end(port):
        eq = port.equipment
        if port.kind == "out" and isinstance(eq, (Separator, Splitter)):
            return f"{eq.name} {'TOP' if port.index == 0 else 'BTM'}"
        return eq.name

    lines = [f"PIPE {end(pipe.out)} -> {end(pipe.into)}"]
    total = pipe.carried.total()
    if total <= 1e-9 or dt <= 0:
        lines.append(" EMPTY / NO FLOW")
        return lines
    gpm = total * 60 / dt
    lines.append(f" FLOW {gpm:,.0f} GPM" + ("" if running else "  (paused)"))
    for species in theme.SPECIES:
        gal = pipe.carried.get(species, 0.0)
        if gal / total >= 0.0005:
            lines.append(f"  {species} {gal / total:6.1%}  {gal * 60 / dt:7,.1f} GPM")
    return lines


# -- equipment ----------------------------------------------------------------


def _tag_points(rect):
    tip = min(16, rect.width // 5)
    return [rect.topleft, (rect.right - tip, rect.top), (rect.right, rect.centery), (rect.right - tip, rect.bottom), rect.bottomleft]


def draw_body(surface, eq: Equipment, rect: pygame.Rect, font=None, fill=None):
    """The equipment's symbol inside `rect`. Used full size on the canvas and tiny for icons."""
    small = rect.height < 50
    if isinstance(eq, Tank):
        draw_vessel(surface, rect, max(3, rect.width // 5))
        inset = max(2, rect.width // 10)
        glass = rect.inflate(-2 * inset, -2 * inset)
        pygame.draw.rect(surface, theme.GLASS, glass)
        frac = min(1.0, eq.volume_gal / eq.capacity_gal) if eq.capacity_gal else 0.0
        color = blend(eq.content)
        h = round(glass.height * frac)
        if color and h > 0:
            level = pygame.Rect(glass.x, glass.bottom - h, glass.width, h)
            pygame.draw.rect(surface, color, level)
            pygame.draw.line(surface, mix(color, (255, 255, 255), 0.5), level.topleft, (level.right - 1, level.top))
        elif small:
            pygame.draw.rect(surface, theme.SPECIES["A"], (glass.x, glass.centery, glass.width, glass.height // 2))
        pygame.draw.rect(surface, theme.OUTLINE, glass, 1)
    elif isinstance(eq, Pump):
        r = min(rect.width, rect.height) // 2
        c = rect.center
        base = [(c[0] - r, rect.bottom), (c[0] + r, rect.bottom), (c[0] + r // 2, c[1]), (c[0] - r // 2, c[1])]
        pygame.draw.polygon(surface, theme.VESSEL_DARK, base)
        pygame.draw.circle(surface, theme.VESSEL_DARK, c, r)
        pygame.draw.circle(surface, theme.VESSEL_LIGHT, (c[0] - r // 5, c[1] - r // 5), round(r * 0.75))
        pygame.draw.circle(surface, theme.OUTLINE, c, r, 1)
        color = theme.RUN if eq.running else theme.STOP
        k = r * 0.55
        tri = [(c[0] + k, c[1]), (c[0] - k * 0.6, c[1] - k * 0.8), (c[0] - k * 0.6, c[1] + k * 0.8)]
        pygame.draw.polygon(surface, color, tri)
    elif isinstance(eq, Reactor):
        motor_h = max(3, rect.height // 9)
        body = pygame.Rect(rect.x, rect.y + motor_h + 2, rect.width, rect.height - motor_h - 2)
        draw_vessel(surface, body, rect.width // 3)
        motor = pygame.Rect(0, 0, max(4, rect.width // 6), motor_h)
        motor.midbottom = (rect.centerx, body.top + 1)
        pygame.draw.rect(surface, theme.VESSEL_DARK, motor)
        pygame.draw.line(surface, theme.OUTLINE, (rect.centerx, body.top), (rect.centerx, body.centery + body.height // 5), max(1, rect.width // 40))
        blade = rect.width // 4
        y = body.centery + body.height // 5
        pygame.draw.line(surface, theme.OUTLINE, (rect.centerx - blade, y), (rect.centerx + blade, y), max(1, rect.width // 30))
        if fill:
            glass = pygame.Rect(0, 0, rect.width // 3, rect.height // 7)
            glass.center = (rect.centerx, body.bottom - body.height // 5)
            pygame.draw.rect(surface, fill, glass, border_radius=3)
            pygame.draw.rect(surface, theme.OUTLINE, glass, 1, border_radius=3)
    elif isinstance(eq, Separator):
        draw_vessel(surface, rect, rect.width // 2)
        gap = max(4, rect.height // 11)
        for y in range(rect.y + gap * 2, rect.bottom - gap, gap):
            pygame.draw.line(surface, theme.VESSEL_DARK, (rect.x + 3, y), (rect.right - 4, y), 1)
    elif isinstance(eq, Splitter):
        c = rect.center
        left = [rect.topleft, c, rect.bottomleft]
        right = [(rect.right, rect.top), c, (rect.right, rect.bottom)]
        for tri in (left, right):
            pygame.draw.polygon(surface, theme.VESSEL_LIGHT, tri)
            pygame.draw.polygon(surface, theme.OUTLINE, tri, 1)
        pygame.draw.circle(surface, theme.VESSEL_DARK, c, max(2, rect.height // 6))
    elif isinstance(eq, Mixer):
        r = min(rect.width, rect.height) // 2
        pygame.draw.circle(surface, theme.VESSEL_LIGHT, rect.center, r)
        pygame.draw.circle(surface, theme.OUTLINE, rect.center, r, 1)
        k = round(r * 0.6)
        cx, cy = rect.center
        pygame.draw.line(surface, theme.VESSEL_DARK, (cx - k, cy - k), (cx + k, cy + k), 2)
        pygame.draw.line(surface, theme.VESSEL_DARK, (cx - k, cy + k), (cx + k, cy - k), 2)
    else:
        if isinstance(eq, Feed):
            color = theme.FEED_TAG
        else:
            color = theme.WASTE_TAG if eq.name == "WASTE" else theme.PRODUCT_TAG
        pts = _tag_points(rect)
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, theme.TEXT, pts, 1)
        if font and not small:
            draw_text(surface, font, (rect.x + 8, rect.y + 6), eq.name, theme.TEXT, "topleft")


def draw_equipment(surface, font, eq: Equipment, pos=None, ports=True, highlight=None, selected=False, fill=None, spec=None):
    rect = rect_of(eq, pos)
    if selected:
        pygame.draw.rect(surface, theme.SELECT, rect.inflate(14, 14), 1)
    draw_body(surface, eq, rect, font, fill)
    if isinstance(eq, Tank):
        draw_text(surface, font, (rect.centerx, rect.y - 30), eq.name, theme.TAG_TEXT)
        pct = eq.volume_gal / eq.capacity_gal if eq.capacity_gal else 0
        draw_value_box(surface, font, (rect.centerx, rect.y - 12), f"{pct:4.0%}", theme.WARN if pct > 0.95 else theme.VALUE_TEXT)
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 12), f"{eq.volume_gal:,.0f} GAL")
    elif isinstance(eq, Pump):
        draw_text(surface, font, (rect.centerx, rect.y - 12), eq.name, theme.TAG_TEXT)
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 12), f"{eq.flow_gpm:.0f} GPM")
    elif isinstance(eq, Reactor):
        draw_text(surface, font, (rect.centerx, rect.y - 12), eq.name, theme.TAG_TEXT)
        side = "*" if eq.side else ""
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 12), f"{eq.reaction.label} {eq.conversion:.0%}{side}", theme.TAG_TEXT)
        _draw_load(surface, font, (rect.centerx, rect.bottom + 32), eq)
    elif isinstance(eq, Separator):
        draw_text(surface, font, (rect.centerx, rect.y - 12), eq.name, theme.TAG_TEXT)
        _draw_load(surface, font, (rect.centerx, rect.bottom + 12), eq)
        if ports:
            for i, (text, dy) in enumerate((("TOP", -13), ("BTM", 13))):
                x, y = port_pos(Port(eq, "out", i), pos)
                draw_text(surface, font, (x + 6, y + dy), text, theme.MUTED, "midleft")
    elif isinstance(eq, Splitter):
        draw_text(surface, font, (rect.centerx, rect.y - 12), eq.name, theme.TAG_TEXT)
        draw_value_box(surface, font, (rect.centerx, rect.bottom + 12), f"{eq.ratio:.0%}/{1 - eq.ratio:.0%}")
    elif isinstance(eq, Mixer):
        draw_text(surface, font, (rect.centerx, rect.y - 12), eq.name, theme.TAG_TEXT)
    elif isinstance(eq, Feed):
        draw_value_box(surface, font, (rect.centerx - 8, rect.bottom - 14), f"{eq.stock.total():,.0f} GAL")
    elif isinstance(eq, Outlet):
        if spec:
            species, purity = spec
            if eq.inflow.total() > 0:
                p = eq.inflow.fraction(species)
                ok = p >= purity - 1e-9
                draw_value_box(surface, font, (rect.centerx - 8, rect.bottom - 14), f"{species} {p:.0%}", theme.OK if ok else theme.ALARM, theme.OK if ok else theme.ALARM)
            else:
                draw_value_box(surface, font, (rect.centerx - 8, rect.bottom - 14), f"{species} --%", theme.MUTED)
        else:
            draw_value_box(surface, font, (rect.centerx - 8, rect.bottom - 14), f"{eq.received.total():,.0f} GAL")
    if ports:
        for port in all_ports(eq):
            center = port_pos(port, pos)
            hot = port == highlight
            pygame.draw.circle(surface, theme.PORT_HOT if hot else theme.PORT_FILL, center, PORT_RADIUS)
            pygame.draw.circle(surface, theme.PORT_RING, center, PORT_RADIUS, 1)


def _draw_load(surface, font, center, eq):
    """Load vs rating; turns red when the unit is pushed past it."""
    over = eq.load_gpm > eq.rated_gpm + 0.5
    color = theme.ALARM if over else theme.VALUE_TEXT
    draw_value_box(surface, font, center, f"{eq.load_gpm:.0f}/{eq.rated_gpm:.0f} GPM", color, theme.ALARM if over else theme.VALUE_EDGE)


def draw_icon(surface, eq: Equipment, box: pygame.Rect):
    draw_body(surface, eq, fit_rect(eq, box))


# -- text for cards and tooltips ----------------------------------------------


def describe(eq: Equipment) -> str:
    """One-line summary for an inventory card."""
    if isinstance(eq, Pump):
        return f"PUMP {eq.min_gpm:.0f}-{eq.max_gpm:.0f} GPM"
    if isinstance(eq, Tank):
        return f"TANK {eq.capacity_gal:,.0f} GAL"
    if isinstance(eq, Reactor):
        side = "*" if eq.side else ""
        return f"{eq.reaction.label} {eq.conversion:.0%}{side} <{eq.rated_gpm:.0f}"
    if isinstance(eq, Separator):
        tops = "".join(s for s, f in eq.top.items() if f >= 0.5)
        return f"COLUMN TOP:{tops or '-'} <{eq.rated_gpm:.0f}"
    if isinstance(eq, Splitter):
        return "SPLITTER 0-100%"
    if isinstance(eq, Mixer):
        return "MIXER 2>1"
    return ""


def composition_lines(stream: Stream) -> list[str]:
    total = stream.total()
    lines = []
    for species in theme.SPECIES:
        gal = stream.get(species, 0.0)
        if gal > 0.5:
            lines.append(f" {species} {gal:8,.0f} GAL {gal / total:4.0%}")
    return lines or [" (empty)"]


def details(eq: Equipment) -> list[str]:
    """Tooltip / faceplate lines."""
    if isinstance(eq, Pump):
        state = "RUNNING" if eq.running else "STOPPED"
        return [f"{eq.name}  PUMP", f"RANGE {eq.min_gpm:.0f}-{eq.max_gpm:.0f} GPM", f"SP {eq.setpoint_gpm:.0f} GPM  {state}", "Pulls from a FEED or TANK."]
    if isinstance(eq, Tank):
        return [f"{eq.name}  TANK", f"CAP {eq.capacity_gal:,.0f} GAL", *composition_lines(eq.content)]
    if isinstance(eq, Reactor):
        lines = [f"{eq.name}  REACTOR", f"{eq.reaction.label}", f"CONVERSION {eq.conversion:.0%}", f"RATED {eq.rated_gpm:.0f} GPM"]
        if eq.load_gpm > eq.rated_gpm + 0.5:
            lines.append(f"OVERLOADED: {eq.effective_conversion(eq.load_gpm):.0%} NOW")
        if eq.side:
            lines.append(f"SIDE {eq.side.label} {eq.side_conversion:.0%}")
        lines.append("Faster than rated = less conversion")
        return lines
    if isinstance(eq, Separator):
        items = [f"{s}{f:4.0%}" for s, f in eq.top.items()]
        lines = [f"{eq.name}  COLUMN", "SHARE SENT TO TOP:"]
        lines += [" " + "  ".join(items[i : i + 3]) for i in range(0, len(items), 3)]
        lines.append(f"RATED {eq.rated_gpm:.0f} GPM")
        if eq.load_gpm > eq.rated_gpm + 0.5:
            lines.append("FLOODING: splits smearing")
        lines.append("Faster than rated = sloppier split")
        return lines
    if isinstance(eq, Splitter):
        return [f"{eq.name}  SPLITTER", f"TOP {eq.ratio:.0%} / BTM {1 - eq.ratio:.0%}"]
    if isinstance(eq, Mixer):
        return [f"{eq.name}  MIXER", "Joins two streams."]
    if isinstance(eq, Feed):
        return [f"{eq.name}  REMAINING", *composition_lines(eq.stock)]
    if isinstance(eq, Outlet):
        lines = [f"{eq.name}  RECEIVED", *composition_lines(eq.received)]
        if eq.spec:
            lines.append(f" OFF-SPEC {eq.rejected_gal:,.0f} GAL")
        return lines
    return [eq.name]


def draw_card(surface, font, rect, eq, selected=False):
    pygame.draw.rect(surface, theme.CARD, rect)
    pygame.draw.rect(surface, theme.SELECT if selected else theme.CARD_EDGE, rect, 2 if selected else 1)
    icon_box = pygame.Rect(rect.x + 4, rect.y + 4, rect.height - 8, rect.height - 8)
    pygame.draw.rect(surface, theme.BACKGROUND, icon_box)
    draw_icon(surface, eq, icon_box.inflate(-4, -4))
    x = icon_box.right + 8
    surface.blit(font.render(eq.name, True, theme.TAG_TEXT), (x, rect.y + 5))
    surface.blit(font.render(describe(eq), True, theme.TEXT), (x, rect.y + 23))


def draw_tooltip(surface, font, pos, lines):
    imgs = [font.render(line, True, theme.TEXT if i else theme.TAG_TEXT) for i, line in enumerate(lines)]
    w = max(img.get_width() for img in imgs) + 16
    h = sum(img.get_height() for img in imgs) + 12
    x = min(pos[0] + 16, surface.get_width() - w - 4)
    y = min(pos[1] + 16, surface.get_height() - h - 4)
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(surface, theme.VALUE_BOX, rect)
    pygame.draw.rect(surface, theme.TAG_TEXT, rect, 1)
    y += 6
    for img in imgs:
        surface.blit(img, (x + 8, y))
        y += img.get_height()


def draw_frame(surface, font, rect, title):
    """A boxed HMI panel with a title strip."""
    pygame.draw.rect(surface, theme.PANEL, rect)
    pygame.draw.rect(surface, theme.PANEL_EDGE, rect, 1)
    strip = pygame.Rect(rect.x, rect.y, rect.width, 20)
    pygame.draw.rect(surface, theme.KEY, strip)
    draw_text(surface, font, (rect.x + 8, strip.centery), title, theme.TAG_TEXT, "midleft")
