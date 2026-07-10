import logging
import uuid
import json
from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils.deprecation import MiddlewareMixin

_request_id = ContextVar("request_id", default="-")
_username = ContextVar("username", default="-")


class RequestContextFilter(logging.Filter):
    """
    Inject request_id and user into log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        record.user = _username.get()
        return True


class ZurichFormatter(logging.Formatter):
    """
    Format timestamps in Europe/Zurich timezone.
    """

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=ZoneInfo("Europe/Zurich"))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class ZurichJsonFormatter(logging.Formatter):
    """
    JSONL formatter with Europe/Zurich timestamps.
    """

    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created, tz=ZoneInfo("Europe/Zurich")).strftime(
            "%Y-%m-%d %H:%M:%S %z"
        )
        payload = {
            "time": dt,
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "user": getattr(record, "user", "-"),
        }
        message = record.getMessage()
        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["message"] = message
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)




class RequestContextMiddleware(MiddlewareMixin):
    """
    Attach request context for logging.
    """

    def process_request(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        _request_id.set(request_id)
        user = getattr(request, "user", None)
        username = getattr(user, "username", None) if user and user.is_authenticated else "anonymous"
        _username.set(username)
        request.request_id = request_id

    def process_response(self, request, response):
        response["X-Request-ID"] = getattr(request, "request_id", "-")
        return response
