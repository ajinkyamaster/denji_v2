"""Export worker: batches export jobs for the API."""

BATCH_SIZE = 100


def batch(items, size=BATCH_SIZE):
    """Split ``items`` into consecutive batches of at most ``size``."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def batch_count(total, size=BATCH_SIZE):
    """Number of batches needed for ``total`` items."""
    if size <= 0:
        raise ValueError("size must be positive")
    return (total + size - 1) // size


def flatten(batches):
    """Concatenate batches back into one list."""
    out = []
    for group in batches:
        out.extend(group)
    return out
