"""Structured JSON logging with contextvars trace IDs."""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

_trace_id_var: ContextVar[str] = ContextVar("omem_trace_id", default="")


def set_trace_id(tid: str) -> None:
    _trace_id_var.set(tid)


def get_trace_id() -> str:
    return _trace_id_var.get("")


def new_trace_id() -> str:
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
            "trace_id": _trace_id_var.get(""),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


_HANDLER = None


def get_logger(name: str) -> logging.Logger:
    global _HANDLER
    import sys

    logger = logging.getLogger(name)
    if _HANDLER is None:
        _HANDLER = logging.StreamHandler(sys.stderr)
        _HANDLER.setFormatter(JSONFormatter())
    if _HANDLER not in logger.handlers:
        logger.addHandler(_HANDLER)
    return logger
