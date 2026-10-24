import numpy as np

from prague_rain_radar.render import colorize


def test_colorize_handles_signal_and_nodata():
    values = np.array([[-10.0, 20.0, 50.0, np.nan]], dtype=np.float32)
    image = colorize(values)
    assert image.shape == (1, 4, 3)
    assert tuple(image[0, 1]) != tuple(image[0, 0])
    assert tuple(image[0, 3]) == (50, 50, 50)

