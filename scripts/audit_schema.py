"""
Schema / Data Audit for Operations Intelligence M2.1 planning.
Version 2 — uses actual fact-table schema discovered via discover_schema.py.

Real schema highlights:
  - Counterparty: cari_hesap_aciklamasi (name) + vergi_numarasi (tax id)
  - Account: hesap_kodu, hesap_aciklamasi
  - Date: fatura_tarihi
  - Amounts: net_tutar_y (TL), net_tutar_d (foreign), para_birimi_d (currency)
  - Bucket/subtype: business_bucket, subtype
  - Classification flags: is_core_business_relevant, is_cost_model_relevant,
    review_flag, confidence_level, project_use_case

Outputs:
  - Terminal printout (live progress)
  - audit_report.md saved at project root

Read-only.

Usage:
    python scripts/audit_schema.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor


REPORT_PATH = Path("audit_report.md")
FACT_TABLES = ["fact_purchase_lines_clean", "fact_sales_lines_clean"]


# ────────────────────────────────────────────────────────────────────────────
# Output capture
# ────────────────────────────────────────────────────────────────────────────


class Tee:
    def __init__(self):
        self.markdown_lines = []

    def progress(self, msg=""):
        print(msg)

    def md(self, line=""):
        self.markdown_lines.append(line)

    def both(self, line=""):
        print(line)
        self.markdown_lines.append(line)


tee = Tee()


# ────────────────────────────────────────────────────────────────────────────
# DB
# ────────────────────────────────────────────────────────────────────────────


load_dotenv()
DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

conn = psycopg2.connect(DB_URL)


def q(sql, params=None):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params or [])
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception:
        conn.rollback()
        cur.close()
        raise


def q_safe(sql, params=None):
    try:
        return q(sql, params)
    except Exception:
        return []


# ────────────────────────────────────────────────────────────────────────────
# Section 1
# ────────────────────────────────────────────────────────────────────────────


def section_overview():
    tee.md("# Operations Intelligence — Schema / Data Audit")
    tee.md(f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")
    tee.md(
        "Produced by `scripts/audit_schema.py` to support M2.1 planning. "
        "Inventories which dimensions are usable as filters/explorers, "
        "separates real from unreliable, and proposes data contracts for "
        "the Counterparty Explorer and Account Explorer modules."
    )

    tee.progress("\n[1/9] Fact tables overview...")
    tee.md("\n## 1. Fact Tables Overview\n")
    tee.md("| Table | Rows | Earliest | Latest | Span (years) |")
    tee.md("|---|---:|---|---|---:|")

    for tbl in FACT_TABLES:
        row = q(f"""
            SELECT COUNT(*) AS n,
                   MIN(fatura_tarihi)::date AS earliest,
                   MAX(fatura_tarihi)::date AS latest
            FROM {tbl}
        """)[0]
        if row['earliest'] and row['latest']:
            years = round((row['latest'] - row['earliest']).days / 365.25, 1)
        else:
            years = "—"
        tee.md(
            f"| `{tbl}` | {row['n']:,} | {row['earliest']} | "
            f"{row['latest']} | {years} |"
        )


# ────────────────────────────────────────────────────────────────────────────
# Section 2
# ────────────────────────────────────────────────────────────────────────────


FILTER_RELEVANT_COLS = [
    "fatura_tarihi",
    "cari_hesap_aciklamasi", "vergi_numarasi", "vergi_dairesi",
    "clean_counterparty_type",
    "hesap_kodu", "hesap_aciklamasi",
    "account_prefix_3", "account_class_main", "account_class_sub",
    "business_bucket", "subtype", "project_use_case",
    "is_core_business_relevant", "is_cost_model_relevant",
    "review_flag", "confidence_level", "classification_version",
    "para_birimi_d",
    "e_fatura_seri_numarasi", "is_prepayment", "realized_in_procurement",
    "birim_cinsi", "miktar",
    "clean_unit_group", "clean_product_type",
]


def profile_column(table, column):
    exists = q("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, [table, column])
    if not exists:
        return None

    total = q(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
    if total == 0:
        return {"null_pct": None, "distinct": 0, "top": []}

    null_count_rows = q_safe(f"""
        SELECT COUNT(*) AS n FROM {table}
        WHERE "{column}" IS NULL OR "{column}"::text = ''
    """)
    null_count = null_count_rows[0]["n"] if null_count_rows else 0
    null_pct = round(100.0 * null_count / total, 1)

    distinct_rows = q_safe(f'SELECT COUNT(DISTINCT "{column}") AS n FROM {table}')
    distinct = distinct_rows[0]["n"] if distinct_rows else 0

    top = q_safe(f"""
        SELECT "{column}"::text AS val, COUNT(*) AS n
        FROM {table}
        WHERE "{column}" IS NOT NULL
        GROUP BY "{column}"
        ORDER BY n DESC
        LIMIT 3
    """)

    return {
        "null_pct": null_pct,
        "distinct": distinct,
        "top": [(r["val"], r["n"]) for r in top],
    }


def section_filter_relevant_profile():
    tee.progress("\n[2/9] Filter-relevant column profiles...")

    tee.md("\n## 2. Filter-Relevant Column Profile\n")
    tee.md(
        "Columns that are candidates for filters, dropdowns, or drill-down. "
        "NULL % and distinct count tell us viability — high NULL = unreliable; "
        "very high distinct = needs search-typeahead.\n"
    )
    tee.md(
        "Markers: ⚠️ = NULL ≥50% — ❌ = NULL ≥90% (essentially empty)\n"
    )

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side} — `{tbl}`\n")
        tee.md("| Column | NULL % | Distinct | Top 3 values (count) |")
        tee.md("|---|---:|---:|---|")

        for col in FILTER_RELEVANT_COLS:
            p = profile_column(tbl, col)
            if p is None:
                continue
            top_str = "; ".join(
                f"`{str(v)[:25]}` ({n:,})" for v, n in p["top"]
            ) if p["top"] else "—"
            null_marker = ""
            if p["null_pct"] is not None:
                if p["null_pct"] >= 90:
                    null_marker = " ❌"
                elif p["null_pct"] >= 50:
                    null_marker = " ⚠️"
            null_str = f"{p['null_pct']}%{null_marker}" if p["null_pct"] is not None else "—"
            tee.md(f"| `{col}` | {null_str} | {p['distinct']:,} | {top_str} |")


# ────────────────────────────────────────────────────────────────────────────
# Section 3 — Counterparty universe
# ────────────────────────────────────────────────────────────────────────────


def section_counterparty_universe():
    tee.progress("\n[3/9] Counterparty universe...")

    tee.md("\n## 3. Counterparty Universe\n")
    tee.md(
        "**No `cari_hesap_kodu` field exists.** Counterparties are identified "
        "by `cari_hesap_aciklamasi` (name) + `vergi_numarasi` (tax id). "
        "Tax id is the canonical join key.\n"
    )

    for tbl in FACT_TABLES:
        side = "ALIŞ (suppliers)" if "purchase" in tbl else "SATIŞ (customers)"
        tee.md(f"\n### {side}\n")

        rows = q(f"""
            SELECT
                COUNT(DISTINCT cari_hesap_aciklamasi) AS distinct_names,
                COUNT(DISTINCT vergi_numarasi) AS distinct_tax_ids,
                COUNT(*) FILTER (WHERE cari_hesap_aciklamasi IS NULL
                                   OR cari_hesap_aciklamasi = '') AS null_names,
                COUNT(*) FILTER (WHERE vergi_numarasi IS NULL
                                   OR vergi_numarasi = '') AS null_tax,
                COUNT(*) AS total_rows
            FROM {tbl}
        """)[0]

        tee.md(f"- **Distinct names:** {rows['distinct_names']:,}")
        tee.md(f"- **Distinct tax ids:** {rows['distinct_tax_ids']:,}")
        tee.md(
            f"- **NULL names:** {rows['null_names']:,} / {rows['total_rows']:,} "
            f"({100.0 * rows['null_names'] / rows['total_rows']:.1f}%)"
        )
        tee.md(
            f"- **NULL tax ids:** {rows['null_tax']:,} / {rows['total_rows']:,} "
            f"({100.0 * rows['null_tax'] / rows['total_rows']:.1f}%)"
        )

        tax_to_names = q(f"""
            SELECT COUNT(*) AS n FROM (
                SELECT vergi_numarasi
                FROM {tbl}
                WHERE vergi_numarasi IS NOT NULL AND vergi_numarasi <> ''
                  AND cari_hesap_aciklamasi IS NOT NULL
                  AND cari_hesap_aciklamasi <> ''
                GROUP BY vergi_numarasi
                HAVING COUNT(DISTINCT cari_hesap_aciklamasi) > 1
            ) t
        """)[0]["n"]

        name_to_taxes = q(f"""
            SELECT COUNT(*) AS n FROM (
                SELECT cari_hesap_aciklamasi
                FROM {tbl}
                WHERE vergi_numarasi IS NOT NULL AND vergi_numarasi <> ''
                  AND cari_hesap_aciklamasi IS NOT NULL
                  AND cari_hesap_aciklamasi <> ''
                GROUP BY cari_hesap_aciklamasi
                HAVING COUNT(DISTINCT vergi_numarasi) > 1
            ) t
        """)[0]["n"]

        if tax_to_names > 0:
            tee.md(
                f"- ⚠️ **Tax-id name drift:** {tax_to_names} tax ids have "
                "multiple name spellings → use tax id as canonical key, "
                "pick most-recent name for display."
            )
        if name_to_taxes > 0:
            tee.md(
                f"- ⚠️ **Name collision:** {name_to_taxes} names appear "
                "under multiple tax ids → never group by name alone."
            )

        types = q_safe(f"""
            SELECT clean_counterparty_type AS t, COUNT(*) AS n
            FROM {tbl}
            WHERE clean_counterparty_type IS NOT NULL
            GROUP BY 1 ORDER BY n DESC
        """)
        if types:
            tee.md(f"\n**Counterparty types in {side}:**")
            tee.md("| Type | Rows |")
            tee.md("|---|---:|")
            for r in types:
                tee.md(f"| `{r['t']}` | {r['n']:,} |")

        top = q(f"""
            SELECT cari_hesap_aciklamasi AS name,
                   COUNT(*) AS rows,
                   COUNT(DISTINCT vergi_numarasi) AS tax_ids,
                   SUM(net_tutar_y)::float AS amount_tl
            FROM {tbl}
            WHERE cari_hesap_aciklamasi IS NOT NULL
              AND cari_hesap_aciklamasi <> ''
            GROUP BY 1
            ORDER BY amount_tl DESC NULLS LAST
            LIMIT 5
        """)
        tee.md(f"\n**Top 5 by TL amount in {side}:**")
        tee.md("| Name | Rows | Tax ids | TL amount |")
        tee.md("|---|---:|---:|---:|")
        for r in top:
            amt = r["amount_tl"] or 0
            tee.md(f"| {r['name'][:50]} | {r['rows']:,} | {r['tax_ids']} | {amt:,.0f} |")


# ────────────────────────────────────────────────────────────────────────────
# Section 4 — Account code universe
# ────────────────────────────────────────────────────────────────────────────


def section_account_universe():
    tee.progress("\n[4/9] Account code universe...")

    tee.md("\n## 4. Account Code Universe\n")
    tee.md(
        "Account codes (`hesap_kodu`) are the raw material for the Account "
        "Explorer. `account_prefix_3` (e.g. 689, 611, 612, 159) is the "
        "high-level chart-of-accounts class.\n"
    )

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side}\n")
        row = q(f"""
            SELECT
                COUNT(DISTINCT hesap_kodu) AS distinct_codes,
                COUNT(DISTINCT account_prefix_3) AS distinct_prefixes,
                COUNT(*) FILTER (WHERE business_bucket IS NULL) AS unbucketed,
                COUNT(*) AS total_rows
            FROM {tbl}
        """)[0]
        tee.md(f"- **Distinct full codes:** {row['distinct_codes']:,}")
        tee.md(f"- **Distinct 3-digit prefixes:** {row['distinct_prefixes']}")
        tee.md(
            f"- **Rows without bucket:** {row['unbucketed']:,} / "
            f"{row['total_rows']:,} "
            f"({100.0 * row['unbucketed'] / row['total_rows']:.1f}%)"
        )

        top = q(f"""
            SELECT hesap_kodu, hesap_aciklamasi, business_bucket,
                   COUNT(*) AS rows,
                   SUM(net_tutar_y)::float AS amount_tl
            FROM {tbl}
            WHERE hesap_kodu IS NOT NULL
            GROUP BY 1, 2, 3
            ORDER BY amount_tl DESC NULLS LAST
            LIMIT 10
        """)
        tee.md("\n**Top 10 by TL amount:**")
        tee.md("| Code | Description | Bucket | Rows | TL |")
        tee.md("|---|---|---|---:|---:|")
        for r in top:
            desc = (r["hesap_aciklamasi"] or "")[:35]
            bucket = r["business_bucket"] or "—"
            amt = r["amount_tl"] or 0
            tee.md(
                f"| `{r['hesap_kodu']}` | {desc} | {bucket} | "
                f"{r['rows']:,} | {amt:,.0f} |"
            )


# ────────────────────────────────────────────────────────────────────────────
# Section 5 — Currency landscape
# ────────────────────────────────────────────────────────────────────────────


def section_currency():
    tee.progress("\n[5/9] Currency landscape...")

    tee.md("\n## 5. Currency Landscape\n")
    tee.md(
        "Currency mix per side. `net_tutar_y` is always TL (translated at "
        "invoice date); `net_tutar_d` is the original-currency amount. "
        "`para_birimi_d` flags the original currency.\n"
    )

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side}\n")

        rows = q(f"""
            SELECT COALESCE(para_birimi_d, '<null>') AS ccy,
                   COUNT(*) AS rows,
                   SUM(net_tutar_y)::float AS amount_tl
            FROM {tbl}
            GROUP BY 1
            ORDER BY rows DESC
        """)
        total_rows = sum(r["rows"] for r in rows)
        tee.md("| Original currency | Rows | Row % | TL amount |")
        tee.md("|---|---:|---:|---:|")
        for r in rows:
            pct = 100.0 * r["rows"] / total_rows
            amt = r["amount_tl"] or 0
            tee.md(f"| `{r['ccy']}` | {r['rows']:,} | {pct:.1f}% | {amt:,.0f} |")


# ────────────────────────────────────────────────────────────────────────────
# Section 6 — Bucket / subtype distribution
# ────────────────────────────────────────────────────────────────────────────


def section_bucket_subtype():
    tee.progress("\n[6/9] Bucket / subtype distribution...")

    tee.md("\n## 6. Bucket / Subtype Distribution\n")

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side}\n")
        rows = q(f"""
            SELECT business_bucket,
                   COUNT(DISTINCT subtype) AS distinct_subtypes,
                   COUNT(*) AS rows,
                   SUM(net_tutar_y)::float AS amount_tl,
                   COUNT(*) FILTER (WHERE subtype IS NULL OR subtype = '') AS subtype_null
            FROM {tbl}
            GROUP BY 1
            ORDER BY amount_tl DESC NULLS LAST
        """)
        tee.md("| Bucket | Subtypes | Rows | TL | Subtype NULL % |")
        tee.md("|---|---:|---:|---:|---:|")
        for r in rows:
            bucket = r["business_bucket"] or "<null>"
            amt = r["amount_tl"] or 0
            null_pct = (
                f"{100.0 * r['subtype_null'] / r['rows']:.0f}%"
                if r["rows"] else "—"
            )
            tee.md(
                f"| `{bucket}` | {r['distinct_subtypes']} | {r['rows']:,} | "
                f"{amt:,.0f} | {null_pct} |"
            )

    tee.md("\n### Project use-case classification (cross-cutting)\n")
    tee.md(
        "`project_use_case` tags rows by analytical purpose — useful for "
        "filtering noise out of analyses.\n"
    )
    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        rows = q_safe(f"""
            SELECT project_use_case, COUNT(*) AS rows,
                   SUM(net_tutar_y)::float AS amount_tl
            FROM {tbl}
            WHERE project_use_case IS NOT NULL
            GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        """)
        if rows:
            tee.md(f"\n**{side}:**")
            tee.md("| Use case | Rows | TL |")
            tee.md("|---|---:|---:|")
            for r in rows:
                amt = r["amount_tl"] or 0
                tee.md(f"| `{r['project_use_case']}` | {r['rows']:,} | {amt:,.0f} |")

    tee.md("\n### Classification quality\n")
    tee.md(
        "Indicates how trustworthy bucketing is — important for explorers "
        "to surface flagged rows.\n"
    )
    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        conf = q_safe(f"""
            SELECT confidence_level, COUNT(*) AS rows
            FROM {tbl}
            GROUP BY 1 ORDER BY rows DESC
        """)
        flag = q_safe(f"""
            SELECT COUNT(*) FILTER (WHERE review_flag) AS flagged,
                   COUNT(*) AS total
            FROM {tbl}
        """)
        if conf and flag:
            tee.md(f"\n**{side}:**")
            tee.md(
                f"- review_flag = TRUE: {flag[0]['flagged']:,} / "
                f"{flag[0]['total']:,} "
                f"({100.0 * flag[0]['flagged'] / flag[0]['total']:.1f}%)"
            )
            tee.md("- confidence_level distribution:")
            for r in conf:
                tee.md(f"  - `{r['confidence_level']}`: {r['rows']:,}")


# ────────────────────────────────────────────────────────────────────────────
# Section 7 — Time coverage
# ────────────────────────────────────────────────────────────────────────────


def section_time_coverage():
    tee.progress("\n[7/9] Time coverage...")

    tee.md("\n## 7. Time Coverage\n")

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side}\n")
        rows = q(f"""
            WITH per_month AS (
                SELECT DATE_TRUNC('month', fatura_tarihi)::date AS month,
                       COUNT(*) AS rows
                FROM {tbl}
                WHERE fatura_tarihi IS NOT NULL
                GROUP BY 1
            )
            SELECT MIN(month) AS first_month,
                   MAX(month) AS last_month,
                   COUNT(*) AS active_months,
                   AVG(rows)::int AS avg_rows,
                   MIN(rows) AS min_rows,
                   MAX(rows) AS max_rows
            FROM per_month
        """)[0]
        tee.md(f"- First month: **{rows['first_month']}**")
        tee.md(f"- Last month:  **{rows['last_month']}**")
        tee.md(f"- Active months: **{rows['active_months']}**")
        tee.md(
            f"- Rows/month: avg **{rows['avg_rows']:,}**, "
            f"min **{rows['min_rows']:,}**, max **{rows['max_rows']:,}**"
        )


# ────────────────────────────────────────────────────────────────────────────
# Section 8 — Capabilities verdict
# ────────────────────────────────────────────────────────────────────────────


def section_capabilities_verdict():
    tee.progress("\n[8/9] Capabilities verdict...")

    tee.md("\n## 8. Capabilities Verdict\n")
    tee.md(
        "Final classification of dimensions for M2.1 scope decisions.\n"
    )

    tee.md("### 8.1 Available Dimensions (use directly)\n")
    tee.md(
        "Low NULL %, consistent values, suitable for filters or explorers "
        "without normalization.\n"
    )
    tee.md("| Dimension | Field | Filter type | Scope |")
    tee.md("|---|---|---|---|")
    tee.md("| Date | `fatura_tarihi` | Range picker | Global |")
    tee.md("| Side (ALIŞ/SATIŞ) | table-level | Toggle | Global |")
    tee.md("| Bucket | `business_bucket` | Multi-select dropdown | Global (cascades) |")
    tee.md("| Subtype | `subtype` | Multi-select (within bucket) | Local |")
    tee.md("| Account code | `hesap_kodu` + `account_prefix_3` | Search-typeahead | Local (Account Explorer) |")
    tee.md("| Counterparty | `vergi_numarasi` (canonical) + `cari_hesap_aciklamasi` (display) | Search-typeahead | Local (Counterparty Explorer) |")
    tee.md("| Counterparty type | `clean_counterparty_type` | Dropdown | Global filter |")
    tee.md("| Original currency | `para_birimi_d` | Dropdown | Global |")
    tee.md("| Core/cost relevance | `is_core_business_relevant`, `is_cost_model_relevant` | Toggle | Global |")
    tee.md("| Project use case | `project_use_case` | Dropdown | Global filter (noise-exclusion) |")
    tee.md("| Confidence level | `confidence_level` | Dropdown | Global (data-quality view) |")
    tee.md("| Prepayment flag | `is_prepayment` | Toggle | Global |")
    tee.md("| Classification version | `classification_version` | Dropdown | Global (default = latest) |")

    tee.md("\n### 8.2 Unavailable / Unreliable Dimensions (do NOT show in UI)\n")
    tee.md(
        "Dimensions a typical BI dashboard would expect, but which do not "
        "exist in this dataset. **The UI must not invent these.**\n"
    )
    tee.md("| Dimension | Status | Why |")
    tee.md("|---|---|---|")
    tee.md(
        "| Company / legal entity | ❌ MISSING | "
        "Single-entity company (Rayon Tekstil); no per-row company tag. |"
    )
    tee.md(
        "| Country / domestic-export split | ❌ MISSING | "
        "No country field on counterparties. Tax id is Turkish format; "
        "foreign customers need separate enrichment (M4 scope). |"
    )
    tee.md(
        "| Branch / cost center | ❌ MISSING | "
        "No branch/cost-center field. Single Çorlu plant assumed. |"
    )
    tee.md(
        "| Product code | ⚠️ PARTIAL | "
        "`clean_product_type` exists but `clean_unit_group`/`miktar` not "
        "consistently populated → usable as facet, not as quantity-driver. |"
    )
    tee.md(
        "| Volume × price decomposition | ⚠️ PARTIAL | "
        "`miktar` + `birim_cinsi` exist but mixed units across products; "
        "cannot do clean variance decomposition without unit-group "
        "rationalization. |"
    )

    tee.md("\n### 8.3 Normalization-Needed Dimensions\n")
    tee.md(
        "These exist but need cleaning before becoming reliable filters or "
        "explorer keys.\n"
    )

    norm_items = []
    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"

        tax_drift = q(f"""
            SELECT COUNT(*) AS n FROM (
                SELECT vergi_numarasi
                FROM {tbl}
                WHERE vergi_numarasi IS NOT NULL AND vergi_numarasi <> ''
                  AND cari_hesap_aciklamasi IS NOT NULL
                  AND cari_hesap_aciklamasi <> ''
                GROUP BY vergi_numarasi
                HAVING COUNT(DISTINCT cari_hesap_aciklamasi) > 1
            ) t
        """)[0]["n"]

        name_collision = q(f"""
            SELECT COUNT(*) AS n FROM (
                SELECT cari_hesap_aciklamasi
                FROM {tbl}
                WHERE vergi_numarasi IS NOT NULL AND vergi_numarasi <> ''
                  AND cari_hesap_aciklamasi IS NOT NULL
                  AND cari_hesap_aciklamasi <> ''
                GROUP BY cari_hesap_aciklamasi
                HAVING COUNT(DISTINCT vergi_numarasi) > 1
            ) t
        """)[0]["n"]

        if tax_drift > 0:
            norm_items.append((
                f"Counterparty display name ({side})",
                f"{tax_drift} tax ids have multiple name spellings",
                "Build dim_counterparty view: tax_id → most-recent name."
            ))
        if name_collision > 0:
            norm_items.append((
                f"Counterparty grouping by name ({side})",
                f"{name_collision} names appear under multiple tax ids",
                "Never group by name alone — use vergi_numarasi as canonical key."
            ))

    if norm_items:
        tee.md("| Dimension | Issue | Recommended action |")
        tee.md("|---|---|---|")
        for item in norm_items:
            tee.md(f"| {item[0]} | {item[1]} | {item[2]} |")
    else:
        tee.md("_No normalization issues detected._")


# ────────────────────────────────────────────────────────────────────────────
# Section 9 — Recommendations
# ────────────────────────────────────────────────────────────────────────────


def section_recommendations():
    tee.progress("\n[9/9] Recommendations & data contracts...")

    tee.md("\n## 9. Recommendations & Data Contracts\n")

    tee.md("### 9.1 Recommended Global Filters\n")
    tee.md("Apply across all panels. Each is backed by a real DB field.\n")
    tee.md("| Filter | Source field | Why viable | Default |")
    tee.md("|---|---|---|---|")
    tee.md(
        "| Date range | `fatura_tarihi` | Universal, fully populated | Last 24 months |\n"
        "| Currency basis | `para_birimi_d` + amount columns | TL primary always; USD/EUR for invoiced subset | TL |\n"
        "| Side | table-level | Fundamental partition | (per panel) |\n"
        "| Core/cost relevance | classification flags | Pre-classified; removes noise | Core-relevant ON |\n"
        "| Project use case | `project_use_case` | Excludes `non_core_noise_exclusion` rows | exclude noise |\n"
        "| Classification version | `classification_version` | Pin to v3 | v3 (latest) |"
    )

    tee.md("\n### 9.2 Recommended Local Filters (per panel)\n")
    tee.md("| Panel | Local filters | Why local |")
    tee.md("|---|---|---|")
    tee.md(
        "| Procurement | bucket multiselect, supplier search | Bucket-specific drill |\n"
        "| Cost Structure | bucket multiselect, account-prefix dropdown | Account-level breakdown |\n"
        "| Revenue Reality | customer search, contra-source toggle | Customer-driven drilldown |\n"
        "| Counterparty Explorer | mode toggle (supplier/customer), counterparty search | Module-defining |\n"
        "| Account Explorer | account search, prefix filter, side, bucket | Code-driven view |"
    )

    tee.md("\n### 9.3 Counterparty Explorer — Data Contract\n")
    tee.md(
        "Two endpoints. **Canonical key is `vergi_numarasi`**, display name "
        "is the most recent `cari_hesap_aciklamasi` for that tax id.\n"
    )
    tee.md("```")
    tee.md("GET /api/internal/counterparties")
    tee.md("    ?side={purchase|sales}     # required")
    tee.md("    &q={search}                # optional, matches name OR tax id")
    tee.md("    &type={...}                # optional, clean_counterparty_type")
    tee.md("    &limit=50")
    tee.md("→ [{ vergi_numarasi, display_name, counterparty_type,")
    tee.md("     total_tl_24m, row_count, last_seen, flag_review_pct }, ...]")
    tee.md("")
    tee.md("GET /api/internal/counterparty/detail")
    tee.md("    ?side={purchase|sales}     # required")
    tee.md("    &vergi_numarasi={...}      # required (canonical key)")
    tee.md("    &months=24                 # default 24")
    tee.md("→ {")
    tee.md("    vergi_numarasi, display_name, name_variants[],")
    tee.md("    summary: { total_tl, total_usd, total_eur,")
    tee.md("               row_count, first_invoice, last_invoice,")
    tee.md("               share_of_total_pct },")
    tee.md("    monthly_trend: [{ month, amount_tl, row_count }, ...],")
    tee.md("    bucket_split: [{ bucket, amount_tl, share_pct, rows }, ...],")
    tee.md("    subtype_split: [{ subtype, amount_tl, rows }, ...],")
    tee.md("    currency_split: [{ ccy, amount_tl_equivalent, rows }, ...],")
    tee.md("    top_accounts: [{ hesap_kodu, hesap_aciklamasi, amount_tl, rows }, ...],")
    tee.md("    classification_quality: { confidence_high_pct, review_flagged_pct },")
    tee.md("    recent_rows: [...]  // last 20")
    tee.md("  }")
    tee.md("```")

    tee.md("\n### 9.4 Account Explorer — Data Contract (next phase)\n")
    tee.md("```")
    tee.md("GET /api/internal/accounts")
    tee.md("    ?side={purchase|sales}")
    tee.md("    &q={search}")
    tee.md("    &prefix={3-digit}")
    tee.md("    &bucket={...}")
    tee.md("    &limit=50")
    tee.md("→ [{ hesap_kodu, hesap_aciklamasi, account_prefix_3,")
    tee.md("     business_bucket, subtype, total_tl_24m, rows }, ...]")
    tee.md("")
    tee.md("GET /api/internal/account/detail")
    tee.md("    ?side={purchase|sales}")
    tee.md("    &hesap_kodu={code}")
    tee.md("→ {")
    tee.md("    hesap_kodu, hesap_aciklamasi,")
    tee.md("    classification: { account_prefix_3, account_class_main,")
    tee.md("                      business_bucket, subtype, project_use_case,")
    tee.md("                      classification_version, confidence_level,")
    tee.md("                      review_flag_pct },")
    tee.md("    summary: { total_tl, rows, first, last },")
    tee.md("    monthly_trend: [...],")
    tee.md("    top_counterparties: [{ vergi_numarasi, display_name, amount_tl, rows }, ...],")
    tee.md("    recent_rows: [...]")
    tee.md("  }")
    tee.md("```")

    tee.md("\n### 9.5 Hidden in MVP (defer)\n")
    tee.md(
        "- **Variance decomposition (volume × price × FX)** — needs unit "
        "rationalization across `miktar`/`birim_cinsi`.\n"
        "- **Export/domestic split** — requires counterparty country "
        "enrichment (M4: external API + manual mapping).\n"
        "- **Compare-period mode** — premature before single-period "
        "explorer usage proves the design.\n"
        "- **Saved presets / Excel export** — polish-tier (M2.3).\n"
        "- **Drill-down drawers in existing panels** — wait until "
        "Counterparty Explorer is live; reuse its detail panel.\n"
    )

    tee.md("\n### 9.6 Recommended Build Sequence (M2.1 → M2.2)\n")
    tee.md(
        "1. **`dim_counterparty` view** — canonical "
        "tax_id → most-recent display name + counterparty_type + "
        "summary stats. Foundation for both explorers.\n"
        "2. **`/api/internal/counterparties` (list endpoint)** — "
        "powers search-typeahead.\n"
        "3. **`/api/internal/counterparty/detail`** — full panel data.\n"
        "4. **Counterparty Explorer UI** — sidebar nav item, mode toggle, "
        "search input, detail panel.\n"
        "5. **One-week real-usage observation period.**\n"
        "6. **Account Explorer** (same pattern).\n"
        "7. **Global filter bar** — only after explorers prove which "
        "filters are actually used.\n"
        "8. **Drill-down drawers in existing panels** — reuse explorer "
        "detail components.\n"
    )


# ────────────────────────────────────────────────────────────────────────────
# Appendix — Full column profile
# ────────────────────────────────────────────────────────────────────────────


def section_full_profile_appendix():
    tee.progress("\n[appendix] Full column profile (this may take a moment)...")

    tee.md("\n## Appendix A — Full Column Profile\n")
    tee.md(
        "Every column in both fact tables. Reference for future feature work.\n"
    )

    for tbl in FACT_TABLES:
        side = "ALIŞ" if "purchase" in tbl else "SATIŞ"
        tee.md(f"\n### {side} — `{tbl}` (all columns)\n")

        cols = q("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, [tbl])

        tee.md("| Column | Type | Nullable | NULL % | Distinct |")
        tee.md("|---|---|:---:|---:|---:|")

        for c in cols:
            colname = c["column_name"]
            try:
                p = profile_column(tbl, colname)
                if p is None:
                    continue
                null_pct = f"{p['null_pct']}%" if p["null_pct"] is not None else "—"
                tee.md(
                    f"| `{colname}` | {c['data_type']} | "
                    f"{c['is_nullable']} | {null_pct} | {p['distinct']:,} |"
                )
            except Exception:
                conn.rollback()


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main():
    tee.progress("=" * 70)
    tee.progress("OPERATIONS INTELLIGENCE — SCHEMA / DATA AUDIT")
    tee.progress("=" * 70)

    section_overview()
    section_filter_relevant_profile()
    section_counterparty_universe()
    section_account_universe()
    section_currency()
    section_bucket_subtype()
    section_time_coverage()
    section_capabilities_verdict()
    section_recommendations()
    section_full_profile_appendix()

    REPORT_PATH.write_text("\n".join(tee.markdown_lines), encoding="utf-8")

    tee.progress("\n" + "=" * 70)
    tee.progress(f"Report written to: {REPORT_PATH.resolve()}")
    tee.progress("=" * 70)
    tee.progress("\nNext: open audit_report.md and review sections 8 + 9.")


if __name__ == "__main__":
    try:
        main()
    finally:
        conn.close()
