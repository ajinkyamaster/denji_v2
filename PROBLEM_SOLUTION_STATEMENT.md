# The problem and the solution

**The problem.** Existing change-impact tools use coverage or import graphs. Both are one-sided oracles: they prove a test *executed* something, but cannot prove it did *not* need to run. A tool excluding tests on this basis is built on the wrong abstraction.

This is provable inside the demo repository. Revision B changes `cache_service.write_cache_entry`
from pipe-delimited text to `json.dumps`. In `report_worker` — a module that imports nothing from the
cache service and is absent from its import closure — `parse_recent_cache_entries` still splits on
the pipe character. Under the default marker set the suite is green at both revisions, so the
regression is invisible to a normal test run; under all markers three contract tests pass at
revision A and fail at revision B. No import-graph precision finds that edge: the dependency is on a
wire format, not on a symbol.

**The solution.** TestScope makes the test-to-code link relation the single object of analysis and
asks four questions of it: which tests must run, which are STALE because they assert behaviour the
change removed, which became NEWLY RELEVANT through hidden coupling, and which changed behaviour has
NO TEST at all. The four answers share one evidence base, one verifier and one invalidator, so they
cannot contradict each other. Two properties make them trustworthy: every claim is re-derived
against the repository by a deterministic kernel before it counts, and the model layer may only *add*
tests, so a wrong or unavailable model degrades to the deterministic baseline instead of corrupting
it.

**Built versus specified.** Built: the symbolic engine (structural closure, representation coupling,
stale detection, uncovered work items, red triage, priority order); the executed oracle with
computed completeness, flakiness exclusion and blindness reporting; the kernel with its rejection
ledger and safe direction; the G1..G5 filtration with mutation strength restricted to the changed
lines; the measurement harness; and a scorecard whose every gate was observed to fail when
deliberately corrupted. Specified, not built: incremental maintenance of the link relation across
commits, and the live Bob session — disclosed in `submissions/checklist.md`.

**The numbers, with their limits.** On the demo change 48 of 500 tests are selected, a 90.4%
reduction. Against executed ground truth of three discriminating tests, recall is 1.0 with an empty
missed list — and that ground truth is a *lower bound*: a test can be affected and still pass twice,
so over-selection is invisible to it and no precision is claimed. The model layer contributed one
additional true positive for 23 recorded coins: without it recall is 0.67, with it 1.0. Three tests
are stale, two changed behaviours had no test, and the price of safety — tests beyond the structural
closure — is seven. No completeness guarantee is claimed: by Rice's theorem, deciding whether a
change affects a test is undecidable, so what is offered is measured recall with its direction
stated, and monotone soundness, which is testable.
