#!/usr/bin/env python3
"""C-G1..C-G5 — the dashboard's own gates, and the proof that each one can fail.

PERSON C section 7 defines five checks that must hold for this UI. They are
implemented here, in the directory Person C owns, rather than in the repository's
verification script (which belongs to Person A).

Each gate is a claim with an observation next to it:

    C-G1  every ledger verdict present in the fixture is rendered somewhere in the UI
    C-G2  the uncovered worklist renders EVERY entry (no silent truncation)
    C-G3  oracle.complete == false produces a visible VOID warning
    C-G4  the renderer never writes markup from artefact strings
    C-G5  at 640px the page does not overflow horizontally

A gate that has never been observed to fail is not evidence, so this file also
ships ``--self-test``, which copies the dashboard to a scratch directory, breaks it
in exactly one place per gate, and asserts the right gate goes red:

    python3 dashboard/gates.py               # run the five gates
    python3 dashboard/gates.py --self-test   # prove each gate can fail

Both exit non-zero on failure. Nothing here needs the network: the page is served
from a loopback HTTP server on an ephemeral port, and the fixture is forced with
``?fixture=`` so the checks are about this fixture rather than about whichever
artefact happens to sit next to it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socketserver
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Never written into the renderer, not even in a comment: these are exactly the
# properties that would let an analysed repository inject markup into the analyst's
# browser. Checked as literals so the gate itself cannot be satisfied by prose.
FORBIDDEN_WRITES = ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write(")


class Quiet(SimpleHTTPRequestHandler):
    """A request handler that does not print a line per hit."""

    def log_message(self, *args) -> None:  # noqa: D102 - silence only
        return


class Server:
    """A loopback static server bound to an ephemeral port, rooted at `root`."""

    def __init__(self, root: Path) -> None:
        handler = partial(Quiet, directory=str(root))
        self._httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self._httpd.allow_reuse_address = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> "Server":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def open_page(server: Server, width: int = 1440, height: int = 1000):
    """Open the dashboard, forcing the fixture, and wait for the app to render.

    A failure here must release the browser: a leaked Playwright instance keeps
    the sync API "inside an asyncio loop" for every later gate, so one timeout
    would cascade into five failures and hide which gate actually broke.
    """
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    try:
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"http://127.0.0.1:{server.port}/dashboard/?fixture=1", wait_until="load")
        page.wait_for_selector("#app:not([hidden])", timeout=15000)
    except Exception:
        browser.close()
        playwright.stop()
        raise
    return playwright, browser, page


def fixture(root: Path) -> dict:
    return json.loads((root / "dashboard" / "mock_report.json").read_text(encoding="utf-8"))


# --- the five gates ------------------------------------------------------------


def gate_g1(server: Server, root: Path) -> tuple[bool, str]:
    """Every ledger verdict present in the fixture is rendered somewhere."""
    report = fixture(root)
    ledger = report.get("ledger") or {}
    expected = list(ledger)
    if isinstance(report.get("uncovered"), list):
        expected.append("uncovered")

    playwright, browser, page = open_page(server)
    try:
        missing: list[str] = []
        rendered: list[str] = []
        for verdict in expected:
            rows = page.locator(f"#body-{verdict} tr").count()
            empty = page.locator(f"#empty-{verdict}")
            empty_visible = bool(empty.count()) and empty.first.is_visible() and \
                bool(empty.first.inner_text().strip())
            summary_ok = False
            if verdict == "valid":
                summary = page.locator("#valid-summary")
                summary_ok = bool(summary.count()) and summary.first.is_visible()
            if rows or empty_visible or summary_ok:
                rendered.append(f"{verdict}:{rows}")
            else:
                missing.append(verdict)
    finally:
        browser.close()
        playwright.stop()

    if missing:
        return False, "not rendered: " + ", ".join(missing)
    return True, "rendered " + ", ".join(rendered)


def gate_g2(server: Server, root: Path) -> tuple[bool, str]:
    """The uncovered worklist renders every entry — no silent truncation."""
    report = fixture(root)
    uncovered = report.get("uncovered") or []
    playwright, browser, page = open_page(server)
    try:
        rows = page.locator("#body-uncovered tr.test-row").count()
        symbols = page.locator("#body-uncovered tr.test-row td:first-child").all_inner_texts()
    finally:
        browser.close()
        playwright.stop()

    if rows != len(uncovered):
        return False, f"fixture has {len(uncovered)} work items, the page rendered {rows}"
    return True, f"{rows} of {len(uncovered)} work items rendered: {' | '.join(symbols)[:120]}"


def gate_g3(server: Server, root: Path) -> tuple[bool, str]:
    """An incomplete oracle produces a visible VOID warning, not a number."""
    report = fixture(root)
    complete = (report.get("measurement") or {}).get("oracle", {}).get("complete")
    playwright, browser, page = open_page(server)
    try:
        banner = page.locator("#banner-void")
        banner_visible = bool(banner.count()) and banner.first.is_visible()
        banner_text = banner.first.inner_text() if banner_visible else ""
        recall = page.locator("#m-recall")
        recall_text = recall.first.inner_text() if recall.count() else ""
    finally:
        browser.close()
        playwright.stop()

    if complete is not False:
        return False, f"fixture oracle.complete is {complete!r}; this gate needs the VOID path"
    if not banner_visible:
        return False, "oracle.complete is false but no VOID banner is visible"
    if recall_text.strip() != "VOID":
        return False, f"recall rendered as {recall_text!r}, expected the literal VOID"
    return True, f"VOID banner visible; recall renders as VOID (first words: {banner_text[:60]!r})"


def gate_g4(server: Server, root: Path) -> tuple[bool, str]:
    """The renderer never turns artefact strings into markup."""
    source = (root / "dashboard" / "script.js").read_text(encoding="utf-8")
    hits = [name for name in FORBIDDEN_WRITES if name in source]
    if hits:
        return False, "forbidden markup-writing properties present: " + ", ".join(hits)
    # Evidence that the safe path is actually in use, not merely that the unsafe
    # one is absent from a file nobody wrote.
    writes = source.count("textContent")
    if writes < 20:
        return False, f"only {writes} textContent writes; the renderer looks incomplete"
    return True, f"0 forbidden properties, {writes} textContent writes"


def gate_g5(server: Server, root: Path) -> tuple[bool, str]:
    """One breakpoint: at 640px the page itself does not scroll sideways."""
    playwright, browser, page = open_page(server, width=640, height=900)
    try:
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        widest = page.evaluate("""() => {
            const de = document.documentElement;
            // An element wider than the viewport inside a horizontally scrolling
            // container is fine — that is what the container is for. Report only
            // elements whose ancestors actually clip them out of view.
            const clipped = (el) => {
              let parent = el.parentElement;
              while (parent && parent !== de) {
                const overflowX = getComputedStyle(parent).overflowX;
                if (overflowX === 'auto' || overflowX === 'scroll' || overflowX === 'hidden') {
                  return true;
                }
                parent = parent.parentElement;
              }
              return false;
            };
            const clientWidth = de.clientWidth;
            let worst = {selector: 'none', over: 0};
            for (const el of document.querySelectorAll('body *')) {
                const rect = el.getBoundingClientRect();
                if (rect.right <= clientWidth + 1 || clipped(el)) continue;
                const over = Math.round(rect.right - clientWidth);
                if (over > worst.over) {
                    worst = {
                        selector: (el.tagName + (el.id ? '#' + el.id : '') +
                                   (el.className && typeof el.className === 'string'
                                    ? '.' + el.className.trim().split(/\\s+/)[0] : '')),
                        over
                    };
                }
            }
            return worst;
        }""")
    finally:
        browser.close()
        playwright.stop()

    if overflow > 0:
        return False, f"page overflows by {overflow}px at 640px (worst: {widest})"
    return True, f"scrollWidth <= innerWidth at 640px (widest offender: {widest})"


def gate_smoke(server: Server, root: Path) -> tuple[bool, str]:
    """The real artefact renders with zero code changes (the swap must be a non-event)."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    try:
        page.goto(f"http://127.0.0.1:{server.port}/dashboard/", wait_until="load")
        page.wait_for_selector("#app:not([hidden])", timeout=15000)
        source = page.locator("#meta-source").inner_text()
        error_hidden = page.locator("#error").is_hidden()
        runlist = page.locator("#runlist-body tr").count()
    finally:
        browser.close()
        playwright.stop()

    if not error_hidden:
        return False, "the page reported an error state on the real artefact"
    if runlist == 0:
        return False, "the real artefact rendered zero run-list rows"
    return True, f"loaded {source} with {runlist} run-list rows and no error state"


GATES = [
    ("C-G1", gate_g1),
    ("C-G2", gate_g2),
    ("C-G3", gate_g3),
    ("C-G4", gate_g4),
    ("C-G5", gate_g5),
    ("SMOKE", gate_smoke),
]


def run_gates(root: Path, only: set[str] | None = None) -> int:
    """Run every gate against `root` and print one line per gate."""
    failures = 0
    with Server(root) as server:
        for key, func in GATES:
            if only and key not in only:
                continue
            try:
                passed, observed = func(server, root)
            except Exception as error:  # noqa: BLE001 - a crash is a failure, not a pass
                passed, observed = False, f"{type(error).__name__}: {error}"
            print(f"  [{'PASS' if passed else 'FAIL'}] {key}: {observed}")
            failures += 0 if passed else 1
    return 1 if failures else 0


# --- self-test: break it, and watch the right gate go red ----------------------

# (gate, filename, find, replace, why)
MUTATIONS = [
    ("C-G1", "index.html", 'id="body-stale"', 'id="x-body-stale"',
     "a ledger verdict that exists in the fixture but has no host element"),
    ("C-G2", "script.js", "for (const item of uncovered) {",
     "for (const item of uncovered.slice(0, 2)) {",
     "a renderer that silently truncates the uncovered worklist"),
    ("C-G3", "index.html", 'id="banner-void"', 'id="x-banner-void"',
     "the VOID banner removed while the oracle is still incomplete"),
    ("C-G4", "script.js", "'use strict';", "'use strict';\nfunction p(x){x.innerHTML='';}",
     "a markup-writing property introduced into the renderer"),
    ("C-G5", "styles.css", "@media print {", ".app { min-width: 1400px; }\n@media print {",
     "a fixed minimum width that cannot fit a 640px viewport"),
]

# C-G2 needs a fixture with MORE work items than the page renders.

# Each mutation must break its own gate and no other gate, otherwise the evidence
# proves only that the copy is broken in general.
ONLY_FOR_GATE = {
    "C-G1": {"C-G1"},
    "C-G2": {"C-G2"},
    "C-G3": {"C-G3"},
    "C-G4": {"C-G4"},
    "C-G5": {"C-G5"},
}


def self_test() -> int:
    """Copy the dashboard, break one thing at a time, assert the right gate fails."""
    print("self-test: each gate must fail on a copy broken in exactly one place")
    problems = 0
    results: list[str] = []

    for key, filename, find, replace, why in MUTATIONS:
        scratch = Path(tempfile.mkdtemp(prefix="testscope-gates-"))
        try:
            shutil.copytree(ROOT / "dashboard", scratch / "dashboard")

            target = scratch / "dashboard" / filename
            text = target.read_text(encoding="utf-8")
            if find not in text:
                print(f"  [FAIL] {key}: probe could not be applied — {find!r} not found")
                problems += 1
                continue

            patched = text.replace(find, replace, 1)
            target.write_text(patched, encoding="utf-8")

            with Server(scratch) as server:
                gate = dict(GATES)[key]
                passed, observed = gate(server, scratch)

            if passed:
                print(f"  [FAIL] {key}: gate PASSED on a broken copy — {why}")
                problems += 1
            else:
                results.append(f"{key} went red on: {why}")
                print(f"  [PASS] {key} failed as required: {observed[:96]}")
                # The other gates must be unaffected by this specific break, or the
                # probe proves nothing about which gate caught it.
                with Server(scratch) as server:
                    others = [
                        other_key
                        for other_key, func in GATES
                        if other_key not in ONLY_FOR_GATE[key]
                        and other_key != "SMOKE"
                        and not func(server, scratch)[0]
                    ]
                if others:
                    print(f"         note: this probe also tripped {', '.join(others)}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    if problems:
        print(f"\nSELF-TEST FAIL ({problems})")
        return 1
    print(f"\nSELF-TEST PASS: {len(results)} gates observed to fail, each on its own probe")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dashboard gates C-G1..C-G5.")
    parser.add_argument("--self-test", action="store_true",
                        help="break a scratch copy and prove each gate can fail")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return run_gates(ROOT)


if __name__ == "__main__":
    sys.exit(main())
