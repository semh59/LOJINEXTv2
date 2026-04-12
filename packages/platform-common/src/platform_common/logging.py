import logging
import json
import os
import sys
from datetime import datetime, UTC


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "line": record.lineno,
            "service": os.getenv("SERVICE_NAME", "unknown-service"),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level=logging.INFO):
    handler = logging.StreamHandler(sys.stdout)

    if os.getenv("LOG_FORMAT", "JSON").upper() == "JSON":
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Silence verbose libs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
