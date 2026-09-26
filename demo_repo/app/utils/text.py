"""Text normalisation helpers.

These are deliberately locale-free: ``str.lower`` only, no Unicode case
folding, so results are identical on every machine.
"""

_SLUG_SEPARATORS = " -_/."


def normalise_slug(text):
    """Lower-case ``text`` and reduce it to ``[a-z0-9-]``.

    Separators become ``-``, runs of separators collapse, and leading/trailing
    separators are removed.
    """
    out = []
    for char in text.strip().lower():
        if char.isalnum():
            out.append(char)
        elif char in _SLUG_SEPARATORS:
            out.append("-")
    collapsed = []
    for char in out:
        if char == "-" and collapsed and collapsed[-1] == "-":
            continue
        collapsed.append(char)
    return "".join(collapsed).strip("-")


def word_count(text):
    """Number of whitespace-separated words."""
    return len(text.split())


def truncate(text, limit):
    """Truncate ``text`` to ``limit`` characters, adding an ellipsis marker.

    Returns ``text`` unchanged when it already fits. Raises ``ValueError`` for
    a negative limit.
    """
    if limit < 0:
        raise ValueError("limit must not be negative")
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * limit
    return text[: limit - 3] + "..."
