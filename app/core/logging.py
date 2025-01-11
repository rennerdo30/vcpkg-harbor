import sys
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
    console: bool = True
) -> None:
    """Configure logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output logs in JSON format
        log_file: Path to log file (None to disable file logging)
        console: Whether to output logs to console
    """
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Set up timestamp processor with UTC time
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        timestamper,
    ]

    if json_format:
        # JSON format for production
        formatters = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ]
    else:
        # Colored console output for development
        formatters = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.exception_formatter)
        ]

    structlog.configure(
        processors=formatters,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure handlers
    handlers: List[logging.Handler] = []
    
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        if json_format:
            formatter = jsonlogger.JsonFormatter(
                '%(timestamp)s %(level)s %(name)s %(message)s',
                timestamp=True
            )
            console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    if log_file:
        # Rotate log files daily, keep 30 days of history
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=settings.logging.retention_days,
            encoding="utf-8",
            delay=True,
        )
        if json_format:
            formatter = jsonlogger.JsonFormatter(
                '%(timestamp)s %(level)s %(name)s %(message)s',
                timestamp=True
            )
            file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Add all handlers
    for handler in handlers:
        handler.setLevel(level.upper())
        root_logger.addHandler(handler)

    # Configure uvicorn access logs
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers = handlers

    # Log startup
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        level=level,
        json_format=json_format,
        log_file=log_file,
    )


def get_request_logger(request_id: str) -> logging.Logger:
    """Get a logger with request context."""
    logger = structlog.get_logger()
    logger.bind(request_id=request_id)
    return logger