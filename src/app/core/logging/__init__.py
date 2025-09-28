# src/app/core/logging/
# ├─ __init__.py            # public API: setup_logging, set_request_id, RequestIDMiddleware
# ├─ builder.py             # make_dict_config(settings) + setup_logging(settings)
# ├─ formatters.py          # JsonFormatter, ColorFormatter
# ├─ filters.py             # RequestIdFilter (+ contextvar helpers)
# ├─ middleware.py          # FastAPI/Starlette middleware to set request id
# ├─ utils.py               # get_project_version(), version helpers
# ├─ handlers.py (opt)      # custom handler factories if needed (file/console)
# └─ README.md              # short notes: how to use, env expectations


from .builder import setup_logging, make_dict_config
from .filters import set_request_id, get_request_id, RequestIdFilter
from .middleware import RequestIDMiddleware

__all__ = ["setup_logging","make_dict_config","set_request_id","get_request_id","RequestIDMiddleware"]
