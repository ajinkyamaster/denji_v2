# TestScope rules (enforced by configuration, not by request)

1. **No model verdict may reach the artefact without kernel verification.**
   `testscope_verify` is the only door. A claim's citations are obligations:
   path exists, symbol present, relation re-derivable. Anything that does not
   re-derive is rejected or recorded as `unconfirmed`.

2. **The deterministic engine decides everything it can decide exactly.**
   Never ask a model a question `testscope_ledger` answers: structural
   closure, representation coupling, uncovered symbols, staleness. Model
   calls cost coins that do not replenish.

3. **Never let two subagents write one file.** The Author role is one file per
   uncovered symbol; the scout and cartographer roles write no files at all.

4. **Determinism is not requested, it is constructed.** Model output enters
   through the content-addressed proposal cache; the artefact is a pure
   function of the inputs and the kernel's verdicts. Never write model output
   directly into the artefact.

5. **Publish a zero rather than hide one.** The model layer's marginal value is
   measured against the oracle and reported even when it is nothing.

6. **Never claim more than the artefact can prove.** No "first ever", no
   completeness guarantee, no precision claim from a lower-bound instrument.
