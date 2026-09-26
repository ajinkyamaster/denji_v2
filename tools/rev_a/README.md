# demo-service

Small service used as the target repository of the TestScope demo.

- `app/services/cache_service.py` writes cache entries through a storage
  backend. Entries are serialised before they are stored.
- `app/workers/report_worker.py` reads the cache entries back and aggregates
  them into operator reports. It does not import the cache service.
- `app/services/billing_service.py` settles and refunds amounts.

## Cache file format

Serialised cache entries are written by `cache_service.write_cache_entry`.
Operators grep the cache file during incidents, so the layout is part of the
service's documented surface.

## Running the tests

```
python3 -m pytest
```

The default run excludes the cross-module contract tests and the
pre-existing failures marked `known_broken`; the release pipeline runs
everything with `-m ""`.

This service is the caches public API and nothing else imports it.
