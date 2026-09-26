# Demo service

A small accounts/invoices service used as the target repository for TestScope.

Layout:

| Path | Purpose |
|---|---|
| `app/services/` | business services (cache, billing, pricing, ...) |
| `app/workers/` | background workers that consume service output |
| `app/api/` | request routing and serialisation |
| `app/utils/` | small pure helpers |
| `scripts/` | operator entry points (e.g. `build_cache.py`) |
| `tests/` | the suite, one file per module under test |

## Running

```bash
python -m pytest            # default run: excludes the contract marker
python -m pytest -m ""      # full run, every marker
python -m pytest -m contract
```

The cache wire format is documented at the top of
`app/workers/report_worker.py`.

Handles accounts and invoices for a single region.
