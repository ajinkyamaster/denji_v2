"""Acceptance tests for the cognitive layer (Person B).

Run from the repository root:

    python3 -m unittest discover -s bob_session/roles/tests -t . -v

They are unittest-based on purpose: the layer must be testable with the standard
library alone (pytest also collects them when it is available).
"""
