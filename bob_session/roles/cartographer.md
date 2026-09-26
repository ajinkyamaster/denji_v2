# ROLE 2 — CARTOGRAPHER (tier 2 of the cascade)

Person B deliverable B3. The prompt text between the markers is VERBATIM from
person_b.txt section 6; the two blocks after it are the required additions. The
`<angle-bracket>` placeholders are filled AT RUN TIME by `bob_session/roles/context.py`
— never by hand.

<!-- PROMPT:BEGIN -->
You read the repository's own prose to recover what the code is SUPPOSED to do.

CONTEXT:
  CHANGED SYMBOL: <signature + body>
  SURROUNDING PROSE: <docstrings, comments, README sections, PR/issue text verbatim>
  THE CHANGE: <verbatim diff hunks>

TASK: Find places where the repository's OWN WRITTEN INTENT is now CONTRADICTED by
the change. Quote exactly.

HARD RULES:
  - Every claim must contain a VERBATIM QUOTE that exists byte-for-byte in the supplied
    prose. Paraphrase is rejected. If you cannot quote it, do not claim it.
  - State the contradiction explicitly: the prose says X; the change makes the code do
    Y, and Y != X.
  - Prefer CONTRACTS over descriptions. Prose that states a contract ("the exact shape
    of the string is part of the public contract") is strong evidence. Prose that
    merely describes the old implementation is weak evidence.
  - Do NOT invent intent. If the prose is silent, return an empty claims list. Silence
    is a valid and useful answer.

OUTPUT (strict JSON):
{"claims":[{"claim_type":"intent","role":"cartographer",
  "targets":{"changed_symbol":"app.services.cache_service.write_cache_entry",
             "quote":"the exact shape of the string is still part of the service's public contract",
             "contradiction":"the change replaces the pipe-delimited shape with json.dumps"},
  "citations":[{"path":"app/workers/report_worker.py",
                "symbol":"parse_recent_cache_entries","line":7}],
  "confidence":"high","rationale":"<=200 chars"}]}
<!-- PROMPT:END -->

## INPUTS THIS ROLE MUST RECEIVE

Assembled by `context.assemble_cartographer(unit)`. The sufficiency gate refuses to
render the prompt when no intent artefact exists: no spec exists; do not invent one.

| Bundle field | Required | Placeholder it fills | What it is |
|---|---|---|---|
| `changed_symbol_body` | yes | `<signature + body>` | the changed symbol, signature and body |
| `intent_artefacts` | yes | (rendered into `prose_text`) | docstrings / comments / README sections / PR or issue text, each with `path`, `line`, `kind`, `text` |
| `diff_hunks` | yes | `<verbatim diff hunks>` | the verbatim diff |
| `run_id`, `prompt_version`, `budget` | — | run envelope header | supplied by the assembler |

Blank artefacts are dropped before the gate; if none survive, `intent_artefacts` is
reported missing and **no model call happens** (zero coins).

## WHAT HAPPENS TO YOUR OUTPUT

1. Every claim goes to `testscope_verify`. For `intent` claims the kernel checks that
   the quoted text is byte-present at the cited location **and** that the cited code no
   longer satisfies it. A paraphrase fails the byte-presence check and is rejected.
2. Rejected ⇒ the cascade has spent its two tiers; the unit is UNCONFIRMED and takes
   the safe direction (include and mark). Nothing further is asked of a model.
3. Verified ⇒ accepted; the finding appears in the run with the quote as its evidence.
4. An empty claims list is a valid, budget-respecting answer. Silence is data.
5. Citation defects follow the same rules as every role: missing path ⇒ reject, right
   symbol at a drifted line ⇒ accept with `line_drift`, wrong symbol ⇒ reject.
6. `confidence` affects ordering only. It never affects acceptance. Cite or abstain.
