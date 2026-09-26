"""Runtime configuration for the demo service.

Defaults live here; deployments override them through :func:`load_config`.
Unknown keys are rejected loudly rather than ignored: silently dropping a
mis-spelled configuration key is how a production setting goes missing.
"""

DEFAULTS = {
    "region": "eu-west",
    "retries": 3,
    "timeout_s": 30,
    "verbose": False,
}


def load_config(overrides=None):
    """Return ``DEFAULTS`` merged with ``overrides``.

    Raises ``KeyError`` if an override names a key that does not exist, and
    ``TypeError`` if an override changes the type of a default.
    """
    merged = dict(DEFAULTS)
    if overrides:
        for key, value in overrides.items():
            if key not in merged:
                raise KeyError(f"unknown configuration key: {key}")
            if not isinstance(value, type(merged[key])):
                raise TypeError(f"configuration key {key} expects {type(merged[key]).__name__}")
            merged[key] = value
    return merged


def is_valid_key(key):
    """True when ``key`` is a known configuration key."""
    return isinstance(key, str) and key in DEFAULTS


def describe(config):
    """A stable, sorted ``key=value`` rendering of a configuration mapping."""
    return ",".join(f"{key}={config[key]}" for key in sorted(config))
