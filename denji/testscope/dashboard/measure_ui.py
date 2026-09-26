#!/usr/bin/env python3
"""Measure the dashboard in a real browser, and print the evidence.

Why this exists: every layout claim in this repository is a measurement, not an
opinion. "The columns fit", "rows are not stretched", "collapsed means collapsed" and
"the page is light regardless of the viewer's OS" are all checkable facts, and a claim
that cannot be measured must not be claimed.

Usage
    python3 -m http.server 8117          # from the repository ROOT, in another shell
    python3 dashboard/measure_ui.py      # add --url/--width/--height to override

Exit code is non-zero if any hard check fails. Soft measurements (M2) are reported
with their counts even when they pass, because "zero violations" is the useful sentence
to paste into the evidence, not "PASS".
"""

from __future__ import annotations

import argparse
import statistics
import sys

from playwright.sync_api import sync_playwright

DARK = "#161616"  # the Carbon dark background, which must never be what a judge sees


def luminance(rgb: str) -> float:
    """Relative luminance of 'rgb(r, g, b)'; 1.0 is white."""
    numbers = [float(part) for part in rgb[rgb.index("(") + 1 : rgb.index(")")].split(",")[:3]]
    return sum(value / 255 for value in numbers) / 3


def measure(page, label: str) -> list[str]:
    """Run every measurement against the current page. Returns the hard failures."""
    failures: list[str] = []

    problems = page.evaluate(
        """() => {
        const out = [];
        // An element whose ancestors intentionally scroll (the wide ledger tables)
        // is clipped on purpose, not overflowing; and .sr-only helpers are 1px by
        // design. Everything else must hold its own text.
        const clipped = (el) => {
          for (let p = el.parentElement; p; p = p.parentElement) {
            const o = getComputedStyle(p);
            if (o.overflowX === 'auto' || o.overflowX === 'scroll') return true;
          }
          return false;
        };
        for (const cell of document.querySelectorAll('td, th')) {
          if (cell.scrollWidth > cell.clientWidth + 1) {
            out.push(`${cell.tagName} "${cell.textContent.trim().slice(0, 40)}" `
                   + `needs ${cell.scrollWidth}px, has ${cell.clientWidth}px`);
          }
        }
        // The bug class a table-only check misses: a bare identifier in prose
        // (a dd, a li, a heading) wider than its column spills onto its neighbour.
        for (const block of document.querySelectorAll('dd, dt, li, p, h2, h3, .action, .count')) {
          if (block.classList.contains('sr-only') || clipped(block)) continue;
          if (block.scrollWidth > block.clientWidth + 1) {
            out.push(`${block.tagName}.${block.className || '-'} `
                   + `"${block.textContent.trim().slice(0, 40)}" `
                   + `needs ${block.scrollWidth}px, has ${block.clientWidth}px`);
          }
        }
        return out;
      }"""
    )
    print(f"  M1 clipped cells / blocks        : {len(problems)}  {problems[:2]}")
    if problems:
        failures.append(f"M1 {len(problems)} cells overflow: {problems[0]}")

    heights = page.evaluate(
        """() => [...document.querySelectorAll('tbody tr.test-row')]
           .map(r => r.getBoundingClientRect().height)
           .filter(h => h > 0)"""
    )
    if heights:
        median = statistics.median(heights)
        stretched = [h for h in heights if h > 1.5 * median]
        print(
            f"  M2 rows over 1.5x median        : {len(stretched)} "
            f"(median {median:.1f}px, max {max(heights):.1f}px, {len(heights)} rows)"
        )
        if stretched:
            failures.append(f"M2 {len(stretched)} stretched rows (max {max(heights):.0f}px)")
    else:
        print("  M2 rows over 1.5x median        : no rows rendered (lazy sections collapsed)")

    stats = page.evaluate(
        """() => ({
        // M3, precisely: BODY rows inside a collapsed section must be 0 before
        // the first expand (the valid bucket is built lazily, on click).
        sectionRows: [...document.querySelectorAll('details:not([open])')]
          .reduce((n, el) => n + el.querySelectorAll('tbody tr').length, 0),
        // These are a different thing: one hidden detail row per rendered test
        // row, existing so a click can reveal the why. Reported, not failed.
        disclosureRows: document.querySelectorAll('tr.detail-row[hidden]').length,
        rendered: document.querySelectorAll('tbody tr').length
      })"""
    )
    section_rows = stats["sectionRows"]
    disclosure_rows = stats["disclosureRows"]
    rendered = stats["rendered"]
    print(
        f"  M3 rows in collapsed sections    : {section_rows} (expect 0) · "
        f"{disclosure_rows} disclosure rows pending their click · {rendered} rendered"
    )
    if section_rows > 0:
        failures.append(f"M3 {section_rows} body rows exist inside collapsed sections")

    background = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    print(f"  M4 body background (OS dark)     : {background}")
    if luminance(background) < 0.8:
        failures.append(f"M4 the page followed the viewer's OS: body is {background}")
        if background.startswith("rgb(22"):  # the documented dark-mode value
            failures.append(f"M4 that is Carbon dark {DARK}; appearance must be deterministic")

    tokens = page.evaluate(
        """() => {
        const body = getComputedStyle(document.body);
        return { font: body.fontFamily, size: body.fontSize, colour: body.color };
      }"""
    )
    print(f"  M5 resolved body tokens          : {tokens['font']} / {tokens['size']} / {tokens['colour']}")
    if "IBM Plex" not in tokens["font"]:
        failures.append(f"M5 the Carbon font stack is not resolving: {tokens['font']}")

    loaded = page.evaluate(
        """() => ({
        sans: document.fonts.check('14px "IBM Plex Sans"'),
        mono: document.fonts.check('13px "IBM Plex Mono"')
      })"""
    )
    # Reported rather than failed: whether the webfont arrived depends on network
    # access at view time, and the stack degrades to a system face by design. What
    # must never change is the declared stack, checked above.
    print(f"  M5b webfont actually loaded     : sans={loaded['sans']} mono={loaded['mono']}")

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - window.innerWidth"
    )
    print(f"  M6 page overflow at {label}      : {overflow}px")
    if overflow > 0:
        failures.append(f"M6 the page overflows horizontally by {overflow}px at {label}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the dashboard's layout rules.")
    parser.add_argument("--url", default="http://127.0.0.1:8117/dashboard/")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args(argv)

    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.url, wait_until="networkidle")
        print(f"desktop {args.width}x{args.height}  {args.url}")
        failures += measure(page, "desktop")

        # Same page, viewed by someone whose OS is in dark mode. The artifact must not
        # change: it is screenshotted and recorded, and a judge's OS is not our input.
        page.emulate_media(color_scheme="dark")
        page.reload(wait_until="networkidle")
        print("same page, OS colour scheme = dark:")
        failures += measure(page, "desktop / OS dark")

        # The breakpoint rule: the page never gains a horizontal scrollbar; wide tables
        # scroll inside their own container instead.
        page.set_viewport_size({"width": 640, "height": 900})
        page.reload(wait_until="networkidle")
        print("narrow viewport 640x900:")
        failures += measure(page, "640px")

        browser.close()

    if failures:
        print(f"\nFAIL ({len(failures)}):")
        for line in failures:
            print("  -", line)
        return 1
    print("\nPASS: every measured layout rule holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
