"""Tests for the dashboard template filters."""

from datetime import datetime

import pytest
from jinja2 import Environment

from vcpkg_harbor.dashboard.filters import (
    EMPTY_VALUE,
    format_bytes,
    format_count,
    format_datetime,
    register_filters,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B"),
        (800, "800 B"),
        (1024, "1.00 KB"),
        (1536, "1.50 KB"),
        (1048576, "1.00 MB"),
        (5_368_709_120, "5.00 GB"),
        (None, EMPTY_VALUE),
    ],
)
def test_format_bytes(value: int | None, expected: str) -> None:
    """Byte sizes are rendered with the expected unit."""
    assert format_bytes(value) == expected


def test_format_count_keeps_raw_value_for_the_client() -> None:
    """Counts carry the raw number so the browser can localise them."""
    rendered = format_count(12345)
    assert 'data-number="12345"' in rendered
    assert "12,345" in rendered


def test_format_count_handles_missing_values() -> None:
    """A missing count renders the placeholder instead of failing."""
    assert format_count(None) == EMPTY_VALUE


def test_format_datetime_accepts_iso_strings_and_datetimes() -> None:
    """Timestamps are rendered in a fixed, sortable fallback format."""
    assert format_datetime("2026-01-02T03:04:05.678901") == "2026-01-02 03:04"
    assert format_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04"
    assert format_datetime(None) == EMPTY_VALUE


def test_format_datetime_passes_through_unparsable_values() -> None:
    """Unexpected timestamp formats are shown as-is rather than crashing."""
    assert format_datetime("not-a-timestamp") == "not-a-timestamp"


def test_register_filters_exposes_the_filters_to_templates() -> None:
    """Templates can use the filters after registration."""
    env = Environment(autoescape=True)
    register_filters(env)

    template = env.from_string("{{ size|filesize }} {{ hits|count }} {{ when|datetime }}")
    rendered = template.render(size=2048, hits=1000, when="2026-01-02T03:04:05")

    assert "2.00 KB" in rendered
    assert 'data-number="1000"' in rendered
    assert "2026-01-02 03:04" in rendered
