"""Structured logging configuration using structlog."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from structlog.types import Processor

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings


def setup_logging(settings: "Settings") -> None:
    """Configure structured logging with structlog."""
    log_level = getattr(logging, settings.logging.level.upper(), logging.INFO)

    # Configure shared processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.logging.json_format:
        # JSON format for production
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Set up file logging if configured
    if settings.logging.file:
        _setup_file_logging(settings)

    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def _setup_file_logging(settings: "Settings") -> None:
    """Set up rotating file logging."""
    if not settings.logging.file:
        return
    log_path = Path(settings.logging.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=settings.logging.retention_days,
    )

    if settings.logging.json_format:
        file_handler.setFormatter(
            logging.Formatter('{"timestamp":"%(asctime)s","message":"%(message)s"}')
        )
    else:
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )

    logging.getLogger().addHandler(file_handler)


def get_logger(name: str | None = None) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
