from goop_sim import settings


def test_screen_size_positive():
    assert settings.SCREEN_WIDTH > 0 and settings.SCREEN_HEIGHT > 0
