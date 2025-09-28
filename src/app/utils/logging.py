from pathlib import Path
from importlib import metadata as importlib_metadata
from typing import Any
import re

# --------------------
# Find pyproject.toml
# --------------------


def find_pyproject(start: Path, max_up: int = 5) -> Path | None:
    p = start
    for _ in range(max_up):
        candidate = p / "pyproject.toml"
        if candidate.exists():
            return candidate
        if p.parent == p:
            break
        p = p.parent
    return None

# --------------------
# Load pyproject
# --------------------


def load_pyproject_data(pyproject_path: Path) -> dict:
    """
    Parse and return the contents of a pyproject.toml file as a dictionary.
    """
    # Use tomllib (stdlib) when available, else tomli (external dependency).
    # We deliberately allow ImportError to bubble if tomli is missing on older Pythons.
    try:
        import tomllib as _toml_loader  # Python 3.11+
    except ImportError:
        import tomli as _toml_loader    # Python < 3.11; add tomli to deps if needed

    # Open in binary mode because tomllib/tomli expect a bytes file-like object.
    with pyproject_path.open("rb") as f:
        return _toml_loader.load(f)


def get_pyproject_value(
    key: str,
    start: str | Path | None = None,
    max_up: int = 5,
    default: Any = None,
) -> Any:
    """
    Return the value for `key` from the nearest pyproject.toml.

    - `key` is dot-separated for nested keys, e.g. "project.version" or "tool.poetry".
    - `start` is the directory to start searching from (Path or str). Defaults to the module's folder.
    - `max_up` controls how many parent dirs to walk up while searching.
    - returns `default` if the pyproject isn't found, can't be parsed, or the key is missing.

    Simple and predictable — no list-indexing, no metadata lookup; returns whatever is in the TOML.
    """
    try:
        start_path = Path(start).resolve() if start is not None else Path(
            __file__).resolve().parent
    except Exception:
        start_path = Path(__file__).resolve().parent

    pyproject = find_pyproject(start=start_path, max_up=max_up)
    if not pyproject:
        return default

    try:
        data = load_pyproject_data(pyproject)
    except Exception:
        return default

    if not key:
        return default

    cur = data
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default

    return cur


def get_project_name(
    start: Path | str | None = None,
    max_up: int = 5,
    default: str | None = None,
) -> str | None:
    """
    Convenience wrapper for project.name in pyproject.toml.
    """
    return get_pyproject_value("project.name", start=start, max_up=max_up, default=default)


def get_project_version(
    start: Path | str | None = None,
    max_up: int = 5,
    default: str = "unknown",
    prefer_installed: bool = True,
) -> str:
    """
    Convenience wrapper for project.version:

    - If prefer_installed is True and the project has a name, try importlib.metadata.version(name)
      (useful in installed/prod containers).
    - Otherwise fall back to project.version from pyproject.toml.
    - Returns `default` on any failure.
    """
    # Try installed distribution first (optional)
    name = get_project_name(start=start, max_up=max_up, default=None)
    if prefer_installed and name:
        try:
            return importlib_metadata.version(name)
        except Exception:
            # non-fatal: fall back to pyproject value
            pass

    # Fall back to pyproject value
    val = get_pyproject_value(
        "project.version", start=start, max_up=max_up, default=None)
    return val if val is not None else default


def get_dependency_requirement(
    pkg_name: str,
    start: Path | str | None = None,
    max_up: int = 5,
    default: str | None = None,
) -> str | None:
    """
    Look up a package in project.dependencies list and return the full requirement
    string (e.g. "alembic==1.16.5") or `default` if not found.

    This is lightweight parsing of the typical list-of-strings layout from PEP 621.
    """
    deps = get_pyproject_value(
        "project.dependencies", start=start, max_up=max_up, default=None)
    if not isinstance(deps, list):
        return default

    # Match starts-with pkg name, allowing extras [] and whitespace, capture rest
    pat = re.compile(rf"^\s*{re.escape(pkg_name)}(\[.*?\])?\s*(.*)$")
    for item in deps:
        if not isinstance(item, str):
            continue
        m = pat.match(item)
        if m:
            # return the full item (caller can parse spec if they want)
            return item
    return default


__all__ = [
    "find_pyproject",
    "load_pyproject_data",
    "get_pyproject_value",
    "get_project_name",
    "get_project_version",
    "get_dependency_requirement",
]
