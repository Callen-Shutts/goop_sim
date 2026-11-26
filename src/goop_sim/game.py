import pygame

from goop_sim import settings
from goop_sim.run.state import RunState
from goop_sim.scenes.play import PlayScene


class Game:
    def __init__(self, seed: int | None = None, fullscreen: bool = settings.FULLSCREEN):
        pygame.init()
        self.screen = self._open_window(fullscreen)
        pygame.display.set_caption(settings.TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.new_run(seed)

    def _open_window(self, fullscreen: bool) -> pygame.Surface:
        """SCALED keeps the logical 1280x720 layout and maps mouse positions for us at any window size."""
        size = (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
        try:
            return pygame.display.set_mode(size, flags)
        except pygame.error:  # e.g. headless drivers without scaling support
            return pygame.display.set_mode(size)

    def toggle_fullscreen(self) -> None:
        try:
            pygame.display.toggle_fullscreen()
        except pygame.error:
            pass

    def new_run(self, seed: int | None = None) -> None:
        self.run_state = RunState(seed)
        self.scene = PlayScene(self, self.run_state)

    def change_scene(self, scene) -> None:
        self.scene = scene

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(settings.FPS) / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                    self.running = False
                else:
                    self.scene.handle_event(event)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()
