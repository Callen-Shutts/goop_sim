import pygame


class Scene:
    """Base class for a game screen. The Game calls these each frame."""

    def __init__(self, game):
        self.game = game

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass
