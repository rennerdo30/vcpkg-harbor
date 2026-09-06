"""Jinja2 template filters for the dashboard.

Keeps presentation helpers (byte sizes, counts, timestamps) in one place so the
templates stay free of duplicated arithmetic and magic numbers.
"""

from datetime import datetime

import structlog
from jinja2 import Environment
from markupsafe import Markup

logger = structlog.get_logger(__name__)

#: Units used when rendering byte sizes, smallest first.
BYTE_UNITS: tuple[str, ...] = ("B", "KB", "MB", "GB", "TB", "PB")
#: Step between two byte units (binary kilobyte, matching CacheStats).
BYTES_PER_UNIT = 1024
#: Decimal places used for byte sizes above one kilobyte.
BYTE_PRECISION = 2
#: Placeholder rendered when a value is missing.
EMPTY_VALUE = "—"
#: Fallback timestamp format; the browser re-formats it for the user's locale.
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"


def format_bytes(value: float | int | None) -> str:
    """Render a byte count as a human-readable size, e.g. ``1.50 MB``.

    Args:
        value: Number of bytes. ``None`` renders the empty placeholder.

    Returns:
        The formatted size, or ``EMPTY_VALUE`` if the input is unusable.
    """
    if value is None:
        return EMPTY_VALUE
    try:
        size = float(value)
    except (TypeError, ValueError):
        logger.debug("Cannot format byte size", value=value)
        return EMPTY_VALUE

    for unit in BYTE_UNITS:
        if abs(size) < BYTES_PER_UNIT:
            # Whole bytes never need decimals.
            if unit == BYTE_UNITS[0]:
                return f"{int(size)} {unit}"
            return f"{size:.{BYTE_PRECISION}f} {unit}"
        size /= BYTES_PER_UNIT
    return f"{size:.{BYTE_PRECISION}f} {BYTE_UNITS[-1]}"


def format_count(value: float | int | None) -> str:
    """Render a number with thousands separators, e.g. ``12,345``.

    The raw value is kept in a ``data-number`` attribute so ``app.js`` can
    re-format it for the visitor's locale; the rendered text is the fallback for
    clients without JavaScript.
    """
    if value is None:
        return EMPTY_VALUE
    try:
        text = f"{value:,d}" if isinstance(value, int) else f"{float(value):,.2f}"
    except (TypeError, ValueError):
        logger.debug("Cannot format number", value=value)
        return EMPTY_VALUE
    return Markup('<span data-number="{}">{}</span>').format(value, text)


def format_datetime(value: datetime | str | None) -> str:
    """Render an ISO timestamp (or ``datetime``) as ``YYYY-MM-DD HH:MM``.

    Templates wrap the result in a ``<time datetime="...">`` element so the
    browser can present it in the visitor's locale.
    """
    if value is None or value == "":
        return EMPTY_VALUE
    if isinstance(value, datetime):
        return value.strftime(TIMESTAMP_FORMAT)
    try:
        return datetime.fromisoformat(value).strftime(TIMESTAMP_FORMAT)
    except ValueError:
        logger.debug("Cannot parse timestamp", value=value)
        return str(value)


def register_filters(env: Environment) -> None:
    """Register the dashboard filters on a Jinja2 environment."""
    env.filters["filesize"] = format_bytes
    env.filters["count"] = format_count
    env.filters["datetime"] = format_datetime
    logger.debug("Registered dashboard template filters", filters=sorted(env.filters))
