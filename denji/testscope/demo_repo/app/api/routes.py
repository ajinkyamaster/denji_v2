"""Route table for the demo API."""

from app.services.cache_service import read_cache_entries

ROUTES = {
    "GET /accounts": "list_accounts",
    "POST /accounts": "create_account",
    "GET /reports/recent": "recent_report",
}


def resolve(method, path):
    """Resolve ``method path`` to a handler name, else None."""
    return ROUTES.get(f"{method} {path}")


def is_known(method, path):
    """True when the route is registered."""
    return resolve(method, path) is not None


def recent_report_entries(path):
    """Cached entries the recent-report route serves."""
    return read_cache_entries(path)
