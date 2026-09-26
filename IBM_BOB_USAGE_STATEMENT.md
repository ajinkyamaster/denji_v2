# How IBM Bob was used

TestScope's workflow is implemented as nine steps in Bob's own taxonomy. Six are deterministic, two
are AI and one is interactive, and that split is the design rather than decoration: deterministic
steps consume no AI tokens, so a question the symbolic engine can answer exactly is never asked of a
model.

**Deterministic, zero coins.** (1) `testscope_ledger` builds the link relation from the diff, the
inventory and the repository. (2) `testscope_oracle` runs the full suite at both revisions. (3) A
sufficiency gate drops every question the artefact already answers. (5) `testscope_verify` re-derives
each claim against the repository. (8) `testscope_gate` applies G1..G5 inside a sandbox. (9) Rendering.
**AI, coins:** (4) the scout and cartographer roles, (7) the author role. **Interactive, zero coins:**
(6) Select Action, where the developer chooses which stale tests to repair and which uncovered
behaviours to author.

**The four roles and what each is for.** The *scout* proposes at most three `link_exists` claims per
candidate pair, citing both the producer and the consumer site: cheap and wide. The *cartographer* mines
intent from prose, quoting exactly the documentation the change invalidated. The *author* writes one
test per uncovered symbol as a patch to an existing test file, and is deliberately shown the pre-change
body and the intent artefact but never the post-change body, so the assertion cannot transcribe the new
implementation. The *falsifier* runs last and alone over the unselected rows, trying to find a test the
ledger should have selected.

**One concrete kernel rejection.** The scout's second link claim cited `app/workers/report_worker.py`
with the symbol `parse_recent_cache_entries_v2`. The kernel re-opened that file, did not find the
symbol, and rejected the claim with gate `symbol_mismatch`. It never reached the artefact; the rejection
ledger keeps its role, gate and reason. A third claim was rejected as `contradicts_symbolic` because it
asserted that T-0343 had no link to the changed code while the symbolic layer had already linked it.

**Subagents and context hygiene.** Each role receives a bundle that is a pure function of the
repository, the diff and the inventory, addressed by a content digest; the cache keys point at those
digests, so a re-run with the same inputs replays byte-identically. Context stays clean by construction:
one role, one question, one bundle, and no two subagents ever write the same file. The tool surface is
four coarse tools on purpose — tool definitions are re-sent every interaction and cost coins on every
turn.

**Cost accounting.** The recorded run's four role calls cost 23 coins (scout 6, cartographer 5, author 8,
falsifier 4). Every other step cost zero, and the replay spends nothing because the proposals are
content-addressed. The team budget was 160.

**Honest gap.** This workspace has no Bob installation, so the session that produced these proposals is
recorded and replayed rather than live, and the task session-summary screenshots are not in this
repository. That is disclosed in `submissions/checklist.md` rather than papered over. Everything else
above is reproducible with `./verify.sh`.
