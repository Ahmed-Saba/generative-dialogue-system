# src/app/core/logging/abc.py

import logging
from app.config.settings import get_settings
from app.core.logging import setup_logging
from .filters import RequestIdFilter, set_request_id

# Initialize settings and logging
settings = get_settings()
setup_logging(settings)

# Use standard logging
logger = logging.getLogger(__name__)
logger.addFilter(RequestIdFilter())

# Set request id
set_request_id("abc-123")

logger.debug("Debug message (only in development) if enabled in settings file or env var LOG_LEVEL=debug is set")
logger.info("Info message", extra={"password": "secret1234"})
logger.warning("Warning message")
logger.error("Error message", extra={"password": "secret1234"})
logger.critical("Critical message")


# src/app/core/logging/abc_run.py
# import logging
# import time
# from app.config import get_settings
# from app.core.logging.builder import setup_logging, stop_queue_logging
# from app.core.logging.filters import set_request_id

# settings = get_settings()
# # for script testing override some settings at runtime if needed:
# settings.LOG_USE_QUEUE = True
# settings.LOG_TO_STDOUT = False
# settings.LOG_DIR = "tmp_logdir"  # or full temp path

# setup_logging(settings)

# logger = logging.getLogger(__name__)
# set_request_id("manual-abc-1")

# logger.info("start message")
# for i in range(5):
#     logger.info("queued msg %d", i, extra={"i": i, "password": "secret1234"})

# # small sleep to let background thread run (not strictly necessary if we stop)
# time.sleep(0.05)

# # flush/stop the listener
# stop_queue_logging()

# print("Done — check logs in", settings.LOG_DIR)


# {"timestamp": "2025-09-26 11:08:38,680", 
#  "level": "INFO", 
#  "logger": "__main__", 
#  "message": "Info message", 
#  "pathname": "f:\\0_Done\\LLM\\Projects\\generative-dialogue-system\\src\\app\\core\\logging\\abc.py", 
#  "lineno": 15, 
#  "request_id": "-", 
#  "service": "gds-api", 
#  "env": "development", 
#  "version": "unknown", 
#  "levelno": 20, 
#  "filename": "abc.py", 
#  "module": "abc", 
#  "exc_info": null, 
#  "exc_text": null, 
#  "stack_info": null, 
#  "funcName": "<module>", 
#  "created": 1758874118.6800747, 
#  "msecs": 680.0, 
#  "relativeCreated": 2433.5093, 
#  "thread": 17208, 
#  "threadName": "MainThread", 
#  "processName": "MainProcess", 
#  "process": 23888, 
#  "taskName": null
#  }

