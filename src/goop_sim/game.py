import pygame

from goop_sim import settings
from goop_sim.run.state import RunState
from goop_sim.scenes.play import PlayScene


class Game:
    def __init__(self, seed: int | None = None):
        pygame.init()
        self.screen = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        pygame.display.set_caption(settings.TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.new_run(seed)

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
                else:
                    self.scene.handle_event(event)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()
