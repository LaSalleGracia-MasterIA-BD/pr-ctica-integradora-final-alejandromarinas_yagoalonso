"""Tests unitarios puros del helper day_window_utc (Feature 15, T4d)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.api.time_window import day_window_utc


def test_day_window_returns_start_at_midnight_utc():
    start, _ = day_window_utc(date(2026, 5, 20))
    assert start == datetime(2026, 5, 20, 0, 0, 0, 0, tzinfo=timezone.utc)


def test_day_window_returns_end_at_end_of_day_utc():
    _, end = day_window_utc(date(2026, 5, 20))
    assert end == datetime(2026, 5, 20, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_day_window_is_inclusive_within_one_day():
    start, end = day_window_utc(date(2026, 5, 20))
    assert (end - start).total_seconds() < 86400  # menos de 24h


def test_day_window_uses_utc_timezone():
    start, end = day_window_utc(date(2026, 1, 1))
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc


def test_day_window_works_for_leap_day():
    start, end = day_window_utc(date(2024, 2, 29))
    assert start.day == 29 and start.month == 2 and start.year == 2024
    assert end.day == 29 and end.month == 2 and end.year == 2024
