"""Colors and sizes for a dark DCS/HMI control-room screen."""

BACKGROUND = (6, 10, 14)
GRID_DOT = (26, 36, 44)
PANEL = (14, 20, 26)
PANEL_EDGE = (50, 70, 80)
CARD = (22, 30, 38)
CARD_EDGE = (60, 80, 92)

TEXT = (225, 230, 235)
TAG_TEXT = (90, 220, 240)  # cyan equipment tags
MUTED = (120, 135, 145)
VALUE_TEXT = (90, 255, 120)  # green numbers in black boxes
VALUE_BOX = (0, 0, 0)
VALUE_EDGE = (110, 120, 130)

VESSEL_LIGHT = (205, 210, 215)
VESSEL_DARK = (70, 76, 84)
OUTLINE = (20, 24, 28)
GLASS = (10, 16, 22)

PIPE_WALL = (70, 82, 92)
PIPE_EMPTY = (22, 28, 34)

RUN = (40, 200, 80)
STOP = (220, 45, 40)
ALARM = (235, 45, 40)
WARN = (245, 220, 40)
OK = (60, 220, 90)
SELECT = (245, 220, 40)

FEED_TAG = (25, 70, 200)
PRODUCT_TAG = (25, 70, 200)
WASTE_TAG = (110, 80, 55)

KEY = (34, 40, 46)  # softkey buttons, like the bottom bar of a DCS screen
KEY_EDGE = (150, 160, 170)
KEY_ACTIVE = (25, 95, 60)
KEY_DANGER = (130, 30, 25)
KEY_DISABLED = (28, 30, 34)

PORT_RING = (90, 220, 240)
PORT_FILL = (10, 16, 22)
PORT_HOT = (245, 220, 40)
OVERLAY_SHADE = (0, 0, 0, 150)

# One color per species. Streams are drawn as the volume-weighted blend of these, so a stream
# turns toward a species' color as it gets purer.
SPECIES = {
    "A": (50, 130, 255),  # blue feed
    "B": (60, 230, 90),  # green
    "C": (255, 160, 30),  # orange
    "D": (225, 70, 255),  # magenta
    "E": (140, 110, 80),  # brown waste
}

TOOLBAR_HEIGHT = 40
BOTTOM_BAR = 48
PANEL_WIDTH = 240
CARD_HEIGHT = 44
CARD_GAP = 6
FACEPLATE_HEIGHT = 196
