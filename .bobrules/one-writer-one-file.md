# One writer, one file

NEVER dispatch two subagents that can write the same file.

- One author unit writes exactly one test file, and extends an existing file; it
  never creates a new one.
- Two uncovered symbols in the same test file are SERIALISED, never parallel.
- Every other role reads only; the rule exists because the author is the one writer.

- Enforcement: `bob_session/roles/dispatch.py` — `WriterRegistry` refuses a second
  simultaneous claim and `plan_waves` places same-file units in different waves;
  `bob_session/roles/tests/test_dispatch.py` asserts both.
