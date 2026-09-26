# Dashboard — integration notes

The report viewer. Everything in this folder is owned by the front-end
workload and depends on nothing outside it except the report JSON.

## Run it

    cd denji/testscope          # the folder holding BOTH dashboard/ and bob_session/
    python3 -m http.server 8117
    # open http://127.0.0.1:8117/dashboard/

Serving the `dashboard/` folder on its own is the common mistake: the report
lives one directory up, and the page says so by name if it cannot find it.
`file://` will not work — the browser blocks the fetch.

## Files

| File | What it is |
|---|---|
| `index.html` | the page. Every id the renderer writes to is here. |
| `styles.css` | one stylesheet, no build step, no framework |
| `script.js` | fetches the report and renders it. No model is ever called. |
| `mock_report.json` | a hand-written fixture, for working without a real run |
| `make_mock_report.py` | regenerates the fixture deterministically |
| `gates.py` | six checks that must pass, plus a self-test proving each can fail |
| `measure_ui.py` | measures the rendered page in a real browser and prints the evidence |
| `capture_evidence.py` | captures the screenshots used in the evidence pack |

## Checks

    python3 dashboard/gates.py        # 6/6
    python3 dashboard/measure_ui.py   # M1-M6, both colour schemes, 1280px and 640px

Both take a `--url` if the server is not on 8117. `gates.py` starts its own
server when one is not already running.

---

## What was found when this was merged against the real report

Recorded because each of these was a defect that only appeared once the page
was pointed at an artefact this code had not been written against. All five are
fixed; the notes are here so nobody re-introduces them.

### 1. The report was being silently rejected

The page validated `reason` against the three words in the frozen contract —
`syntactic`, `semantic`, `unaffected`. The pipeline emits the same three buckets
under different, more precise names. The validator threw, the loader fell
through to the next candidate, and the page quietly served the **fixture**
while looking entirely normal.

That is the worst failure this page has: not an error, but plausible numbers
from the wrong source. The footer would have said "sample report", but the
screen above it would have looked real.

The check now validates the invariant rather than the spelling: a reason must
not contradict the bucket it sits in. Both vocabularies are accepted, and the
accepted set is one named constant at the top of `script.js`.

**This is a contract deviation and the team should resolve it.** The frozen
interface in the master prompt §5.1 specifies `syntactic | semantic |
unaffected`. The emitted values are `structural_import_closure`,
`representation_coupling`, and `no_import_path_to_changed_module` or
`normalised_inert_change`. Either the interface should be amended to the richer
names, or the pipeline should emit the contract's three. Right now the
dashboard accepts both, which is a workaround, not a resolution.

### 2. The hero screen said "+0" on a report with three real regressions

`run_metadata.model_layer` is `"disabled"` in the current report, and the hero
counted its catch from that flag — so it printed **+0** while the same report
carried six coupling findings and three tests triaged as regressions.

The flag says whether an AI model contributed. It does not say whether coupling
was searched for; the computed analysis finds representation coupling on its
own. Keying the hero to it produced a false statement on the one screen that has
to be true.

The count now comes from the data: newly-relevant tests that triage reports as
regressions. The flag survives only where it belongs, disclosing in the banner
that no model was used.

### 3. The code samples named a test that does not exist

The snippets were written against an earlier revision of the demo repository and
showed `test_report_worker_parses_recent_cache_entries`. The real T-0342 is
`test_recent_entries_round_trip_totals`, in a different file layout, against a
producer with a different signature.

Every line of both panes and the hero sample is now transcribed from
`demo_repo/` as it stands. The `== 7` becoming `== 0` is not illustrative: the
reader returns `{"raw": entry}` for a payload with no `|`, and
`summarise_entries` sums `record.get("count", 0)`.

If the demo repository changes again, **re-transcribe these snippets.** They are
the only content on the page that is not read from the report, and stale
snippets are the one place this page can contradict itself.

### 4. Sentences that assumed exactly one

"The lede said one test; the foot said a test is 'the one that turns red'." With
three regressions both were false. The count-bearing phrases are now generated,
including the agreement, so "one" and "three" both read correctly.

### 5. Layout defects the fixture never exercised

The fixture's prose is short. The real report's is not, and it broke three
measurements that had been passing:

- evidence cells grew to 172px against a 48px median — the two-line clamp the
  renderer's comment already promised had been lost, and is now restored
- `.triage-signal` overflowed its card at 640px, because a long dotted path
  cannot break
- the triage grid's 18rem minimum track was wider than a 640px column, pushing
  the page 32px sideways

Lesson worth keeping: **a fixture that is prettier than the data is a fixture
that hides defects.** The gate suite passes on the fixture and on the real
report, and it only found these three on the real one.

---

## Design decisions, and why

**Ink is the accent.** The most recognisable thing an AI-built dashboard does is
reach for a blue gradient on a dark background. So structure here is drawn in
ink and hairlines, and colour is spent only where it carries meaning: a verdict,
a failure, a warning. If something on this page is coloured, it means something.

**One typeface family, three voices.** Plex Serif for the argument, Plex Sans
for reading, Plex Mono for anything a machine wrote. Weights stay at
400/500/600 — size, space and position carry the hierarchy, so the page never
turns into a wall of bold.

**Pinned to light.** The page is screenshotted, printed and recorded. Appearance
that varies with the reader's OS is appearance nobody can review twice. There is
no `prefers-color-scheme` rule, and a gate fails if one appears.

**Flat.** No gradients, no shadows, no blur, no rounded corners. Depth is a
hairline and a change of surface.

**Column widths are measured, not chosen.** The test-name and module columns are
sized against the longest real value in the report, so a longer name fails a
gate instead of quietly wrapping mid-identifier. Two columns are declared with
`width:` in a form the layout gate can read; the uncovered table deliberately
declares none, because it uses content sizing and explicit widths there would
be both redundant and ambiguous to that gate.

**Absent is not zero.** A field the report does not carry prints "not reported".
Zero is a measurement; a blank is a missing fact, and a page that prints 0 for a
missing field has invented one.

**Text only.** Every DOM write goes through `textContent`. The report contains
strings derived from repository source, so letting one be parsed as markup would
turn any analysed repository into a scripting vector into the reader's browser.

## Activity panel

Shows what is happening, and what already happened, without becoming a console.
Two sources, in order of preference:

1. **A running session**, if it writes `testscope_progress.json` next to the
   report. Optional; polled only while present, so a finished report is asked
   once and then never again.
2. **The report itself**, always. `claims.by_role` says which checks ran and
   what each produced, and `run_metadata.model_layer` says whether a model was
   involved at all.

If no model was used, the panel collapses to the one sentence that is true
rather than showing four rows of work that never happened.

Optional progress file shape — every field optional, a missing or half-written
file is ignored and the panel falls back to source 2:

```json
{
  "current_step": "reading app/workers/report_worker.py",
  "steps": [
    { "id": "scout", "name": "Look for code sharing the changed format",
      "status": "running", "detail": "3 candidate pairs" }
  ]
}
```

`status` is one of `queued`, `running`, `done`, `skipped`. `id` matches the role
names in `ACTIVITY_AGENTS` at the top of `script.js`.

## Note for the team, not acted on

`feature/backend-a` currently has `__pycache__/*.pyc` files and
`.cache/testscope/*.json` committed. Harmless, but a judge browsing the repo
sees build noise in the file list. A `.gitignore` plus
`git rm -r --cached` on those paths would clean it up. Not done here, because
those paths belong to another workload and deleting another owner's tracked
files is not this workload's call.
