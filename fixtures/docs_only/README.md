# Demo service

A small acounts/invoices service used as the target repository for TestScope.

Layout:

| Path | Purpose |
|---|---|
| `app/services/` | business services (cache, billing, pricing, ...) |
| `app/workers/` | background workers that consume service output |
| `app/api/` | request routing and serialisation |
| `app/utils/` | small pure helpers |
| `app/jobs/` | command-line jobs (e.g. `build_cache`) |
| `tests/` | the suite, one file per module under test |

## Running

```bash
python -m pytest            # default run: excludes the contract marker
python -m pytest -m ""      # full run, every marker
python -m pytest -m contract
```

The cache wire format is documented at the top of
`app/workers/report_worker.py`.

Handels accounts and invoices for a single region.
