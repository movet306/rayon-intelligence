"""
fix_psf_url.py - Correct the PSF (polyester staple fiber) scraper URL.

Bug:
  scrapers/sunsirs_prices.py line 100 has:
    ("polyester_staple_fiber", BASE + "frodetail-976.html", "RMB/ton")

  This pointed to SunSirs's *futures* page for polyester staple fiber
  (`frodetail-`), which has both a spot price column and a dominant
  contract column. That page stopped updating on 2026-04-30 because
  the futures market hadn't reopened (futures pages update on
  trading-day cadence, not calendar-day cadence).

  Every other commodity in the COMMODITIES list uses `prodetail-NNN`
  (the spot-price page), which updates daily. PSF was the only one
  pointing to the futures URL — likely a typo or a leftover from an
  early test that selected the futures page for its dominant-contract
  data.

Fix:
  Change `frodetail-976.html` to `prodetail-976.html`. The spot page
  shows daily updates and matches the format the parser already
  expects (since every other material uses it).

  Manual verification on 2026-05-03:
    https://www.sunsirs.com/uk/frodetail-976.html  -> last row 2026-04-30
    https://www.sunsirs.com/uk/prodetail-976.html  -> last row 2026-05-03

After running:
  Run the scraper once to backfill missing dates:
    python scrapers/sunsirs_prices.py
  Then rebuild metrics:
    python scrapers/build_price_metrics.py

Idempotent.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRAPER = REPO / "scrapers" / "sunsirs_prices.py"

src = SCRAPER.read_text(encoding="utf-8")

OLD = '("polyester_staple_fiber",   BASE + "frodetail-976.html",   "RMB/ton"),  # spot + futures'
NEW = '("polyester_staple_fiber",   BASE + "prodetail-976.html",   "RMB/ton"),  # spot (was frodetail; futures page stopped updating Apr 30)'

if "prodetail-976.html" in src and "polyester_staple_fiber" in src and "frodetail-976" not in src:
    print("[skip] PSF URL already fixed")
elif OLD in src:
    src = src.replace(OLD, NEW, 1)
    SCRAPER.write_text(src, encoding="utf-8")
    print("[OK] sunsirs_prices.py: PSF URL fixed (frodetail-976 -> prodetail-976)")
else:
    # Looser match in case whitespace differs
    import re
    pat = re.compile(
        r'\(\s*"polyester_staple_fiber"\s*,\s*BASE\s*\+\s*"frodetail-976\.html"\s*,\s*"RMB/ton"\s*\)\s*,?[^\n]*'
    )
    m = pat.search(src)
    if m:
        replacement = '("polyester_staple_fiber",   BASE + "prodetail-976.html",   "RMB/ton"),  # spot (was frodetail; futures page stopped updating Apr 30)'
        src = src[:m.start()] + replacement + src[m.end():]
        SCRAPER.write_text(src, encoding="utf-8")
        print("[OK] sunsirs_prices.py: PSF URL fixed via regex fallback")
    else:
        print("[X] could not find PSF URL line to patch")
        print("    Inspect scrapers/sunsirs_prices.py manually around line 100.")
        raise SystemExit(1)

print()
print("Next steps:")
print("  1) python scrapers/sunsirs_prices.py        # backfill May 1-3")
print("  2) python scrapers/build_price_metrics.py   # rebuild metrics with new data")
print("  3) Refresh dashboard - PSF line should now extend to May 3")
