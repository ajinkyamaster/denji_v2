"""JSON-ish response serialisation helpers."""

from app.services.cache_service import read_cache_entries


def serialise_account(account):
    """Render an account record as sorted ``key=value`` pairs."""
    return ";".join(f"{key}={account[key]}" for key in sorted(account))


def serialise_error(code, message):
    """Render an error payload."""
    return f"error {code}: {message}"


def serialise_recent(path):
    """Serialise the cached entries as a single newline-joined string."""
    return "\n".join(read_cache_entries(path))
