"""
update_roadmap_pi_1_5.py - Mark PI-1.5 done and add PI-1.5b phase.

Updates docs/PRICE_INTEL_ROADMAP.md:
  - PI-1.5 status -> DONE (visual stabilization complete)
  - new sub-phase PI-1.5b added: Polyester chain topology correction
  - decision log entry for the topology split

Idempotent.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
ROADMAP = REPO / "docs" / "PRICE_INTEL_ROADMAP.md"

src = ROADMAP.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Mark PI-1.5 row as done
# ─────────────────────────────────────────────────────────────────────────────
OLD_15_ROW = "| 1.5 | **Polyester chain chart fix.** Add PTA line (currently in boxes but missing from chart). Align all series start dates. Label dashed lines (forecast / MA / etc.). Move sigma into top boxes; remove redundant detail cards. | TODO |"
NEW_15_ROW = "| 1.5 | **Polyester chain chart fix (visual stabilization).** Added PTA line (teal, distinct from DTY). Aligned all series x-axis to common start. Removed MA7 dashed ghost traces. Moved sigma into chain-flow node footers. Hid redundant detail cards (HTML preserved, display:none). Hid rangeslider strip. **Topology correction (linear chain misrepresents staple/filament branches) split out as PI-1.5b.** | DONE |"

if "DONE | <!-- PI-1.5 marker -->" in src or "**Polyester chain chart fix (visual stabilization)**" in src:
    print("[skip] PI-1.5 already marked done")
elif OLD_15_ROW in src:
    src = src.replace(OLD_15_ROW, NEW_15_ROW)
    print("[OK]  PI-1.5 marked DONE")
else:
    print("[X]   PI-1.5 row not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Insert PI-1.5b sub-phase right after PI-1's table (before PI-2 heading)
# ─────────────────────────────────────────────────────────────────────────────
PI_15B_BLOCK = """
### PI-1.5b — Polyester Chain Topology Correction (1 day)

**Why this is a separate phase:** the current chain visualization (PTA → PSF → FDY → POY → DTY in a single line) is technically incorrect. PSF is the staple branch; POY/FDY/DTY are filament branches. PSF is not the upstream of FDY, and POY does not feed FDY. Forcing all five into a fake linear chain misrepresents the underlying chemistry to anyone who reads the dashboard.

**Industrially correct topology:**
```
                ┌─→ PSF                           (staple branch)
PTA → polymer ──┤
                └─→ POY → DTY  (filament branch, with FDY as parallel filament product)
```

**Scope:**

| # | Task | Status |
|---|---|---|
| 1.5b.1 | Replace linear `POLY_CHAIN` array with a branched structure that the renderer understands. | TODO |
| 1.5b.2 | Update `_renderChainFlow` to draw two branches under PTA: staple (PSF) and filament (POY → DTY). FDY rendered as a parallel reference node alongside the filament branch, not as a downstream step. | TODO |
| 1.5b.3 | Update section title from "Polyester Zinciri — PTA → PSF → FDY → POY → DTY" to a topology-accurate string (e.g. "Polyester Chain — Staple & Filament"). | TODO |
| 1.5b.4 | Update legend ordering in chart so it reflects branch grouping rather than the false linear sequence. | TODO |
| 1.5b.5 | Update `CHAIN_UPSTREAM` mapping to match the corrected topology (PSF and POY both point to PTA; DTY points to POY; FDY points to PTA as a parallel filament product). | TODO |

**Out of scope:**
- Adding a "polymer/melt" intermediate node. We don't have data for it; inserting a dummy node would introduce a different kind of misrepresentation.
- Changing the underlying spread / divergence calculations. Those are already pair-based (FDY−PSF, DTY−POY) and remain valid.

**Reversal:** revert `POLY_CHAIN` and `CHAIN_UPSTREAM` to their pre-1.5b state; revert `_renderChainFlow` to the linear loop.

"""

# Insert immediately before "### PI-2 — Rayon Relevance Engine"
PI_2_HEADER = "### PI-2 — Rayon Relevance Engine"

if "### PI-1.5b — Polyester Chain Topology Correction" in src:
    print("[skip] PI-1.5b section already present")
elif PI_2_HEADER in src:
    src = src.replace(PI_2_HEADER, PI_15B_BLOCK + PI_2_HEADER)
    print("[OK]  PI-1.5b section inserted before PI-2")
else:
    print("[X]   PI-2 header not found, cannot anchor insertion")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Update sequencing diagram
# ─────────────────────────────────────────────────────────────────────────────
OLD_SEQ = """```
PI-0  Data Safety Map        ── DONE (this doc)
   ↓
PI-1  Cleanup                ── ~1 week
   ↓
PI-2  Rayon Relevance        ── 1–2 weeks
   ↓
PI-4-skeleton                ── 2–3 days  (high leverage, pulled forward)
   ↓
PI-3  Source Stack           ── 1 week
   ↓
PI-4-full Pass-through       ── 1–2 weeks (highest value)
   ↓
PI-5A Calibration            ── 2 weeks
   ↓
PI-5B Expansion              ── ~1 month
```"""

NEW_SEQ = """```
PI-0  Data Safety Map        ── DONE
   ↓
PI-1  Cleanup                ── in progress
       1.1 Signal dedup           ── DONE
       1.2 KPI strip               ── DONE
       1.5 Polyester chart visual  ── DONE
       1.5b Polyester topology     ── ~1 day (new)
       1.3, 1.4, 1.6–1.9          ── ~3-4 days
   ↓
PI-2  Rayon Relevance        ── 1–2 weeks
   ↓
PI-4-skeleton                ── 2–3 days  (high leverage, pulled forward)
   ↓
PI-3  Source Stack           ── 1 week
   ↓
PI-4-full Pass-through       ── 1–2 weeks (highest value)
   ↓
PI-5A Calibration            ── 2 weeks
   ↓
PI-5B Expansion              ── ~1 month
```"""

if NEW_SEQ in src:
    print("[skip] sequencing diagram already updated")
elif OLD_SEQ in src:
    src = src.replace(OLD_SEQ, NEW_SEQ)
    print("[OK]  sequencing diagram updated")
else:
    print("[!]   sequencing diagram not in expected form, skipping that update")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Append decision log entries
# ─────────────────────────────────────────────────────────────────────────────
NEW_LOG = """- **2026-04-29:** PI-1.2 (KPI strip) and PI-1.1 (signal dedup) shipped (commits `6ccc00b`, `dbb5794`). Feed reduced from 30+ duplicate cards to 9 distinct patterns; KPI strip now scoped to Price Intelligence with correct data source.
- **2026-04-29:** PI-1.5 closed as **visual stabilization** only. Topology correction split out into new sub-phase PI-1.5b. Reason: the chart-order issue (linear chain misrepresents staple vs filament branches) is a modeling problem, not a polish problem, and trying to fold it into PI-1.5 would have been scope creep."""

# Append to the existing Decision Log section
if "PI-1.5 closed as **visual stabilization**" in src:
    print("[skip] decision log entries already present")
elif "## Decision Log" in src:
    src = src.rstrip() + "\n" + NEW_LOG + "\n"
    print("[OK]  decision log entries appended")
else:
    print("[!]   no Decision Log section, skipping")

ROADMAP.write_text(src, encoding="utf-8")
print("\nDone. Verify with:  git diff docs/PRICE_INTEL_ROADMAP.md")
