# ROLE 3 — AUTHOR (one test for one uncovered symbol)

Person B deliverable B3. The prompt text between the markers is VERBATIM from
person_b.txt section 6; the two blocks after it are the required additions. This
prompt has no `<angle-bracket>` context placeholders, so the assembler appends its
bundle as JSON at run time — never hand-filled.

<!-- PROMPT:BEGIN -->
You are writing ONE regression test for ONE uncovered behaviour.

CONTEXT: you are given the EXISTING TEST CLASS to extend, the uncovered symbol's
signature, the PREVIOUS implementation, and (when it exists) a written intent
artefact. THE CURRENT IMPLEMENTATION IS DELIBERATELY WITHHELD. Do not ask for it, and
do not assume it. Extend the existing test file; do not create a new file.

TASK: Add ONE test that pins the intended behaviour of the uncovered symbol.

HARD RULES:
  - Extend the existing test class. Match its imports, fixtures and helper usage.
  - Assert BEHAVIOUR, not implementation: assert on the contract that the intent
    artefact or the previous implementation describes. Do NOT assert on internal
    calls, private attributes, or the literal wording of log messages.
  - The test MUST FAIL against the previous implementation and PASS against the
    current one. A test that passes against the old code pins nothing and is discarded.
  - No network, no sleeps, no wall-clock time, no randomness, no absolute paths.
  - Deterministic, and independent of test execution order.

OUTPUT: a unified diff against the existing test file, plus:
{"claims":[{"claim_type":"test","role":"author",
  "targets":{"symbol":"...","file":"demo_repo/tests/services/test_cache_service.py",
             "test_name":"test_...","behaviour_pinned":"one sentence"},
  "citations":[{"path":"<the intent artefact you relied on>","symbol":"...","line":N}],
  "confidence":"med","rationale":"<=200 chars"}]}

WHAT HAPPENS TO YOUR OUTPUT — the gates, and each has a reason:
  G1  BUILDABLE      the file imports and collects.
  G2  PASSES 5x      five executions against the CURRENT revision; it must pass every
                     time. A test that passes only sometimes is flaky and discarded.
  G3  PATCH TEST     one execution against the PREVIOUS revision, and an ASSERTION
                     must fire. A collection or import error does NOT satisfy this,
                     because that proves the symbol is absent, not that behaviour
                     changed.
  G4  STRENGTH       mutation analysis restricted to the changed lines.
  G5  SPEC-ANCHORED  only when an intent artefact exists; otherwise null.
You will be told which gate failed and why, and you may retry EXACTLY ONCE. If you
claim the behaviour is CORRECT rather than merely PINNED, you are overclaiming: say
"pinned". See A2 for why that distinction is not pedantry.
<!-- PROMPT:END -->

## INPUTS THIS ROLE MUST RECEIVE

Assembled by `context.assemble_author(unit)`. The sufficiency gate refuses to render
the prompt unless the signature, the test class to extend, and the PRE-change body are
all present.

| Bundle field | Required | What it is |
|---|---|---|
| `symbol` | yes | the uncovered symbol's dotted name |
| `symbol_signature` | yes | its signature |
| `test_class_file` | yes | the EXISTING test file to extend (the only legal target) |
| `test_class` | no | the class name to extend (empty string when absent) |
| `test_class_source` | yes | that file's source, so imports/fixtures/helpers can be matched |
| `intent_artefact` | **optional** | docstring / README / PR text; when absent, G5 is `null` and the claim says *pinned*, never *correct* |
| `pre_change_body` | yes | the PREVIOUS implementation |
| `withheld_fields` | — | records `["post_change_body"]` when the unit carried one; the CONTENT is never copied |
| `run_id`, `prompt_version`, `budget` | — | run envelope header |

**The post-change implementation body is deliberately WITHHELD.** If the author can
read the new code it will transcribe it and the test becomes a snapshot that can never
disagree with the code — green tests forever, no signal. A unit test asserts the
sentinel never reaches the rendered prompt, even when the unit supplies it.

## WHAT HAPPENS TO YOUR OUTPUT

1. The claim is validated as a `test` envelope whose `targets.patch` is a unified diff
   against `test_class_file`. A claim that targets any other file is discarded before
   the gate: the role extends an existing file and creates none.
2. One test per uncovered symbol (`<= 1` claim). Two symbols in the same test file are
   serialised, never written in parallel.
3. Adjudication is `testscope_gate` — **execution, not opinion** — and it requires an
   explicit human click in Bob. Nothing authored enters the suite unless the gate
   accepts it.
4. Gates and their defined behaviour: G1 buildable; G2 passes 5× (anti-flake); G3 the
   assertion must FIRE against the previous revision — a collection or import error
   does NOT satisfy G3; G4 mutation strength restricted to the changed lines; G5
   specification anchoring only when an intent artefact exists.
5. You may retry EXACTLY ONCE. Beyond that the symbol stays in the uncovered worklist.
6. Wording discipline: an accepted test "pins" the behaviour. It does not prove the
   change was correct. With no intent artefact, `SPECIFIES` is not claimed at all.
