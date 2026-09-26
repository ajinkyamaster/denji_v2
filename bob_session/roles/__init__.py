<<<<<<< HEAD
"""Person B's cognitive layer: role prompts, context assembly, cascade, dispatch.

Modules:
  context.py        bundles + the sufficiency gate + runtime placeholder filling (B4)
  envelope.py       the claim envelope: the only language the models may speak (B3)
  cascade.py        the verification-gated cascade (B6)
  dispatch.py       subagent dispatch rules: one writer per file, clean contexts (B6)
  kernel_client.py  transport for the four MCP tools (Person A owns the server)
  errors.py         the layer's error taxonomy: every failure mode has a name
  testing.py        test doubles and unit builders (not the kernel)
"""
=======
"""The four role prompts and the recorded proposal set.

A role never decides: it proposes claims. The recorded proposal set below
was produced by the four roles in a recorded session, and it is replayed
through the content-addressed cache. ``record_proposals.py`` writes the
cache; ``run_analysis`` looks it up by bundle digest.
"""

ROLE_PROMPTS = {
    "scout": (
        "You are the Scout. Input: candidate (producer, consumer) pairs for a wire format "
        "whose producer changed, plus the diff hunks. Output: at most 3 claims of type "
        "link_exists, each citing BOTH sites with path, symbol and line. A claim whose "
        "citation does not resolve will be rejected; a claim whose link cannot be "
        "re-derived (the test references the consumer symbol, or covers the cited line) "
        "is recorded as unconfirmed and included in the run list."
    ),
    "cartographer": (
        "You are the Cartographer. Input: the changed symbol, its file, and the prose that "
        "documents it. Output: at most 3 claims of type intent, each quoting the intent "
        "artefact EXACTLY as written and naming the wire-format tag the change violated. "
        "The quote must be byte-present at the cited location, and the code must no longer "
        "satisfy it, or the claim is rejected."
    ),
    "author": (
        "You are the Author. Input: ONE uncovered symbol, the test file to extend, the "
        "intent artefact, and the PRE-change body of that symbol. The post-change body is "
        "withheld by design: an assertion that transcribes the new implementation converts "
        "bugs into passing tests. Output: one claim of type test carrying a patch to the "
        "existing test file. The patch is accepted only if an assertion of yours fires "
        "against the base revision and passes against the current one (G1..G5)."
    ),
    "falsifier": (
        "You are the Falsifier. Input: the final ledger digest, the diff, and ONLY the "
        "rows the ledger did not select. Output: at most 5 claims of type missed, each "
        "naming the test that should have been selected and the dependency path that "
        "justifies it. The path must re-derive against the repository or the claim is "
        "recorded as unconfirmed."
    ),
}
>>>>>>> origin/saurabh
