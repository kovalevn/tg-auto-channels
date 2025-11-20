from datetime import datetime, time, timezone

from app.services.posting import _in_window


def test_in_window_basic():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert _in_window(now, time(10, 0), time(18, 0))


def test_in_window_wraps_midnight():
    now = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)
    assert _in_window(now, time(22, 0), time(3, 0))


def test_outside_window():
    now = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    assert not _in_window(now, time(10, 0), time(18, 0))
