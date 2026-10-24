from datetime import timezone

import numpy as np

from prague_rain_radar.chmi import Grid, crop_indices, parse_index, quarter_hour_files


def test_parse_and_filter_quarter_hours():
    html = """
    <a href="T_PANV23_C_OKPR_20261024130000.hdf">one</a>
    <a href="T_PANV23_C_OKPR_20261024130500.hdf">two</a>
    <a href="T_PANV23_C_OKPR_20261024131500.hdf">three</a>
    """
    files = parse_index(html)
    selected = quarter_hour_files(files, "2026-10-24")
    assert [item.timestamp.minute for item in selected] == [0, 15]
    assert all(item.timestamp.tzinfo == timezone.utc for item in selected)


def test_crop_indices_are_inside_grid():
    grid = Grid(11.266869, 48.047275, 19.623974, 51.458369, 1555.7, 1555.7, 598, 378)
    x0, y0, x1, y1 = crop_indices(grid, 13.4, 49.6, 15.5, 50.5)
    assert 0 <= x0 < x1 <= grid.width
    assert 0 <= y0 < y1 <= grid.height
    assert (x1 - x0) > (y1 - y0)

