"""Centralized logging configuration for SAP BRIM AI backend."""

import os
import sys
import logging
from backend.app.security.log_safety import PrivacyLogFilter

VERBOSE_LOGGERS = (
    "uvicorn.access",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "httpx",
    "httpcore",
    "urllib3",
    "watchfiles",
    "passlib",
    "huggingface_hub",
    "transformers",
    "torch",
    "sentence_transformers",
    "google",
    "google.generativeai",
    "google.auth",
    "groq",
    "openai",
    "asyncio",
    "multipart",
)

# uvicorn installs its own handlers on these (propagate=False), so the root handler never sees them.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


class AppLogFormatter(logging.Formatter):
    """Clean, consistent formatting for terminal logs."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logging(log_level: str | None = None) -> None:
    """Initialize and configure centralized application logging."""
    log_level_name = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper().strip()
    resolved_level = getattr(logging, log_level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    # Avoid duplicate handlers on re-initialization or module reload
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(AppLogFormatter())
    _add_privacy_filter(console_handler)
    root_logger.addHandler(console_handler)

    # Silence noisy third-party and internal query loggers. Their records still pass the privacy filter:
    # a logger with its own handlers (uvicorn.access under uvicorn) gets the filter on them, the others
    # propagate to the filtered root handler instead of falling through to logging.lastResort.
    target_noise_level = logging.WARNING if resolved_level > logging.DEBUG else logging.DEBUG
    for name in VERBOSE_LOGGERS:
        noisy_logger = logging.getLogger(name)
        noisy_logger.setLevel(target_noise_level)
        if noisy_logger.handlers:
            _filter_logger_handlers(noisy_logger)
        else:
            noisy_logger.propagate = True

    # uvicorn's loggers do not propagate to the root. The handler filters cover the handlers uvicorn
    # installed before this module was imported (`uvicorn backend.app.main:app`); the logger filters keep
    # redacting when uvicorn replaces its handlers afterwards (`uvicorn.run(app)`, reload workers), since
    # logging.config.dictConfig keeps existing logger filters.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        _add_privacy_filter(uvicorn_logger)
        _filter_logger_handlers(uvicorn_logger)

    # Records of any logger left without a handler are printed by logging.lastResort.
    if logging.lastResort is not None:
        _add_privacy_filter(logging.lastResort)


def _add_privacy_filter(target: logging.Filterer) -> None:
    if not any(isinstance(existing, PrivacyLogFilter) for existing in target.filters):
        target.addFilter(PrivacyLogFilter())


def _filter_logger_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        _add_privacy_filter(handler)
