"""Structured, cloud-safe logging configuration."""

import json
import logging
import os
import re
import sys
from typing import Any, Dict


# Sanitization pattern to mask potential secrets and sensitive tokens
SANITIZE_REGEX = re.compile(r"(?i)(password|secret|token|api_key|authorization|bearer)\s*[:=]\s*['\"]?([^\s'\"]+)", re.IGNORECASE)


def sanitize_message(msg: str) -> str:
    """Mask sensitive tokens or passwords in log output."""
    if not isinstance(msg, str):
        return str(msg)
    return SANITIZE_REGEX.sub(r"\1: [REDACTED]", msg)


class SanitizingFormatter(logging.Formatter):
    """Log formatter that automatically redacts credentials."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = sanitize_message(str(record.msg))
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter for production cloud logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_message(record.getMessage()),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """Get a configured, cloud-safe logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        log_format = os.environ.get("LOG_FORMAT", "text").lower()

        if log_format == "json":
            formatter = JsonFormatter()
        else:
            formatter = SanitizingFormatter(
                fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)
    return logger
