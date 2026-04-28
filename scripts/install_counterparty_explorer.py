"""
Install Counterparty Explorer v1 (M2.1) into the dashboard.

What this does:
  1. Adds two endpoints to dashboard/server.py:
       GET /api/internal/counterparties           (list, with smart search)
       GET /api/internal/counterparty/detail      (panel data)
  2. Adds the Counterparty Explorer section to dashboard/static/index.html
  3. Adds the loader/render JS to dashboard/static/app.v5.js
  4. Adds Counterparty Explorer CSS to dashboard/static/style.v5.css
  5. Adds a sidebar nav item "Counterparty Explorer"

Backups created with .bak_m21 suffix.
Idempotent — re-running detects already-installed markers and skips.

Decisions baked in (from M2.1 audit + CE/EP planning):
  - Plain VIEW dim_counterparty as foundation
  - Tax-id-missing entities included with badge
  - 24-month default window
  - List endpoint: lean field set
  - Smart search: tax id prefix + name substring, relevance ordering
  - Standalone sidebar nav item
  - name_variants_count > 1 shows a "drift" badge

Usage:
    python scripts/install_counterparty_explorer.py
"""
from pathlib import Path
import sys

ROOT = Path(".")
SERVER_PY = ROOT / "dashboard" / "server.py"
INDEX_HTML = ROOT / "dashboard" / "static" / "index.html"
APP_JS = ROOT / "dashboard" / "static" / "app.v5.js"
STYLE_CSS = ROOT / "dashboard" / "static" / "style.v5.css"

MARKER_SERVER = "# === COUNTERPARTY EXPLORER (M2.1) ==="
MARKER_HTML = "<!-- === COUNTERPARTY EXPLORER (M2.1) === -->"
MARKER_JS = "// === COUNTERPARTY EXPLORER (M2.1) ==="
MARKER_CSS = "/* === COUNTERPARTY EXPLORER (M2.1) === */"
SIDEBAR_MARKER = "data-section=\"counterparty\""


# ─────────────────────────────────────────────────────────────────────────
# Backend endpoints (FastAPI)
# ─────────────────────────────────────────────────────────────────────────


SERVER_PATCH = '''

# === COUNTERPARTY EXPLORER (M2.1) ===
# Two endpoints backed by the dim_counterparty view (Migration 012).
# - List endpoint: smart search + lean field set, drives the search-typeahead UI.
# - Detail endpoint: full panel data for a selected counterparty.

@app.get("/api/internal/counterparties")
def list_counterparties(
    side: str = "purchase",
    q: str = "",
    type: str | None = None,
    limit: int = 50,
):
    """
    Smart-search list of counterparties.

    Search behavior:
      - If `q` looks like digits/tax id: prefix match on vergi_numarasi
      - Otherwise: case-insensitive substring on display_name
      - Order: exact-tax-match > tax-prefix > name-substring > total_tl_24m DESC
    """
    if side not in ("purchase", "sales"):
        return {"error": "side must be purchase or sales"}, 400

    limit = max(1, min(200, int(limit)))
    q = (q or "").strip()
    q_clean = q.replace(".0", "")  # tolerate '1234567890.0' style

    # Build the query
    sql_parts = ["""
        SELECT
            canonical_key,
            display_name,
            vergi_numarasi,
            is_verified,
            counterparty_type,
            total_tl_24m,
            row_count_24m,
            last_seen,
            name_variants_count
        FROM dim_counterparty
        WHERE side = %s
    """]
    params = [side]

    if type:
        sql_parts.append("AND counterparty_type = %s")
        params.append(type)

    is_numeric_query = q_clean.isdigit() and len(q_clean) >= 3

    if q:
        if is_numeric_query:
            # Tax id prefix match OR name substring (broader for short numeric queries)
            sql_parts.append(
                "AND (vergi_numarasi LIKE %s OR display_name ILIKE %s)"
            )
            params.append(q_clean + "%")
            params.append("%" + q + "%")
        else:
            # Pure name search
            sql_parts.append("AND display_name ILIKE %s")
            params.append("%" + q + "%")

    # Relevance-aware ordering
    if q and is_numeric_query:
        sql_parts.append("""
            ORDER BY
              CASE
                WHEN vergi_numarasi = %s THEN 0
                WHEN vergi_numarasi LIKE %s THEN 1
                WHEN display_name ILIKE %s THEN 2
                ELSE 3
              END,
              total_tl_24m DESC NULLS LAST
        """)
        params.extend([q_clean, q_clean + "%", "%" + q + "%"])
    elif q:
        # For text search, exact match first, then position of substring
        sql_parts.append("""
            ORDER BY
              CASE WHEN display_name ILIKE %s THEN 0 ELSE 1 END,
              total_tl_24m DESC NULLS LAST
        """)
        params.append(q + "%")  # starts-with bonus
    else:
        sql_parts.append("ORDER BY total_tl_24m DESC NULLS LAST")

    sql_parts.append("LIMIT %s")
    params.append(limit)

    sql = "\\n".join(sql_parts)

    rows = _query(sql, params)

    return {
        "side": side,
        "q": q,
        "count": len(rows),
        "results": [
            {
                "canonical_key": r["canonical_key"],
                "display_name": r["display_name"],
                "vergi_numarasi": r["vergi_numarasi"],
                "is_verified": r["is_verified"],
                "counterparty_type": r["counterparty_type"],
                "total_tl_24m": float(r["total_tl_24m"]) if r["total_tl_24m"] else 0,
                "row_count_24m": r["row_count_24m"] or 0,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "name_variants_count": r["name_variants_count"] or 1,
            }
            for r in rows
        ],
    }


@app.get("/api/internal/counterparty/detail")
def counterparty_detail(
    side: str = "purchase",
    canonical_key: str = "",
    months: int = 24,
):
    """
    Detail panel for a single counterparty.
    Returns: summary, monthly_trend, bucket_split, subtype_split,
             currency_split, top_accounts, classification_quality, recent_rows.
    """
    if side not in ("purchase", "sales"):
        return {"error": "side must be purchase or sales"}, 400
    if not canonical_key:
        return {"error": "canonical_key is required"}, 400

    months = max(1, min(120, int(months)))
    fact_table = f"fact_{'purchase' if side == 'purchase' else 'sales'}_lines_clean"

    # Header row from dim_counterparty
    header = _query(
        """
        SELECT * FROM dim_counterparty
        WHERE side = %s AND canonical_key = %s
        """,
        [side, canonical_key],
    )
    if not header:
        return {"error": "counterparty not found"}, 404
    h = header[0]

    # Reconstruct the WHERE clause used by the view to filter rows for this counterparty
    if h["is_verified"]:
        cp_filter = "vergi_numarasi IS NOT NULL AND TRIM(vergi_numarasi) NOT IN ('', '0', '0.0') AND TRIM(vergi_numarasi) = %s"
        cp_param = h["vergi_numarasi"]
    else:
        cp_filter = """(vergi_numarasi IS NULL OR TRIM(vergi_numarasi) IN ('', '0', '0.0'))
                       AND TRIM(cari_hesap_aciklamasi) = %s"""
        # display_name is the latest spelling; for unverified we use it directly
        cp_param = h["display_name"]

    # Data horizon (anchor for "trailing N months")
    horizon_row = _query(f"SELECT MAX(fatura_tarihi) AS m FROM {fact_table}", [])
    horizon = horizon_row[0]["m"] if horizon_row else None

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = _query(
        f"""
        SELECT
            SUM(net_tutar_y) FILTER (
                WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_tl,
            SUM(net_tutar_d) FILTER (
                WHERE para_birimi_d = 'USD'
                  AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_usd,
            SUM(net_tutar_d) FILTER (
                WHERE para_birimi_d = 'EUR'
                  AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_eur,
            COUNT(*) FILTER (
                WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::int AS row_count,
            MIN(fatura_tarihi) AS first_invoice,
            MAX(fatura_tarihi) AS last_invoice
        FROM {fact_table}
        WHERE {cp_filter}
        """,
        [horizon, horizon, horizon, horizon, cp_param],
    )[0]

    # Total side amount in window for share calc
    side_total_row = _query(
        f"""
        SELECT SUM(net_tutar_y)::float AS t
        FROM {fact_table}
        WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        """,
        [horizon],
    )
    side_total = side_total_row[0]["t"] or 0
    share_pct = (
        100.0 * (summary["total_tl"] or 0) / side_total
        if side_total else 0
    )

    # ── Monthly trend ───────────────────────────────────────────────────────
    monthly = _query(
        f"""
        SELECT DATE_TRUNC('month', fatura_tarihi)::date AS month,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY 1
        """,
        [cp_param, horizon],
    )

    # ── Bucket split ────────────────────────────────────────────────────────
    buckets = _query(
        f"""
        SELECT business_bucket AS bucket,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        """,
        [cp_param, horizon],
    )
    cp_total = sum((b["amount_tl"] or 0) for b in buckets) or 1
    bucket_split = [
        {
            "bucket": b["bucket"],
            "amount_tl": b["amount_tl"] or 0,
            "share_pct": round(100.0 * (b["amount_tl"] or 0) / cp_total, 1),
            "rows": b["rows"],
        }
        for b in buckets
    ]

    # ── Subtype split ───────────────────────────────────────────────────────
    subtypes = _query(
        f"""
        SELECT subtype, SUM(net_tutar_y)::float AS amount_tl, COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
          AND subtype IS NOT NULL AND subtype <> ''
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        LIMIT 15
        """,
        [cp_param, horizon],
    )

    # ── Currency split ──────────────────────────────────────────────────────
    currencies = _query(
        f"""
        SELECT COALESCE(para_birimi_d, '<unknown>') AS ccy,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        """,
        [cp_param, horizon],
    )

    # ── Top accounts ────────────────────────────────────────────────────────
    accounts = _query(
        f"""
        SELECT hesap_kodu, hesap_aciklamasi,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
          AND hesap_kodu IS NOT NULL
        GROUP BY 1, 2 ORDER BY amount_tl DESC NULLS LAST
        LIMIT 10
        """,
        [cp_param, horizon],
    )

    # ── Classification quality ──────────────────────────────────────────────
    quality = _query(
        f"""
        SELECT
            100.0 * SUM(CASE WHEN confidence_level = 'high' THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0) AS confidence_high_pct,
            100.0 * SUM(CASE WHEN review_flag THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0) AS review_flagged_pct
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        """,
        [cp_param, horizon],
    )[0]

    # ── Recent rows ─────────────────────────────────────────────────────────
    recent = _query(
        f"""
        SELECT fatura_tarihi, hesap_kodu, business_bucket AS bucket,
               net_tutar_y::float AS amount_tl,
               para_birimi_d AS ccy
        FROM {fact_table}
        WHERE {cp_filter}
        ORDER BY fatura_tarihi DESC NULLS LAST
        LIMIT 20
        """,
        [cp_param],
    )

    return {
        "side": side,
        "canonical_key": canonical_key,
        "vergi_numarasi": h["vergi_numarasi"],
        "display_name": h["display_name"],
        "is_verified": h["is_verified"],
        "counterparty_type": h["counterparty_type"],
        "name_variants_count": h["name_variants_count"] or 1,
        "months": months,
        "data_horizon": horizon.isoformat() if horizon else None,
        "summary": {
            "total_tl": summary["total_tl"] or 0,
            "total_usd": summary["total_usd"] or 0,
            "total_eur": summary["total_eur"] or 0,
            "row_count": summary["row_count"] or 0,
            "first_invoice": summary["first_invoice"].isoformat() if summary["first_invoice"] else None,
            "last_invoice": summary["last_invoice"].isoformat() if summary["last_invoice"] else None,
            "share_of_total_pct": round(share_pct, 2),
        },
        "monthly_trend": [
            {"month": r["month"].isoformat(), "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in monthly
        ],
        "bucket_split": bucket_split,
        "subtype_split": [
            {"subtype": r["subtype"], "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in subtypes
        ],
        "currency_split": [
            {"ccy": r["ccy"], "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in currencies
        ],
        "top_accounts": [
            {
                "hesap_kodu": r["hesap_kodu"],
                "hesap_aciklamasi": r["hesap_aciklamasi"],
                "amount_tl": r["amount_tl"] or 0,
                "rows": r["rows"],
            }
            for r in accounts
        ],
        "classification_quality": {
            "confidence_high_pct": round(float(quality["confidence_high_pct"] or 0), 1),
            "review_flagged_pct": round(float(quality["review_flagged_pct"] or 0), 1),
        },
        "recent_rows": [
            {
                "fatura_tarihi": r["fatura_tarihi"].isoformat() if r["fatura_tarihi"] else None,
                "hesap_kodu": r["hesap_kodu"],
                "bucket": r["bucket"],
                "amount_tl": r["amount_tl"] or 0,
                "ccy": r["ccy"],
            }
            for r in recent
        ],
    }

# === END COUNTERPARTY EXPLORER (M2.1) ===
'''


# ─────────────────────────────────────────────────────────────────────────
# HTML section
# ─────────────────────────────────────────────────────────────────────────


HTML_SECTION = '''
<!-- === COUNTERPARTY EXPLORER (M2.1) === -->
<section id="section-counterparty" class="section" style="display:none;">
  <header class="section-header">
    <h2>Counterparty Explorer</h2>
    <p class="section-sub">Suppliers &amp; Customers · canonical view by tax id, with name-grouping fallback</p>
  </header>

  <div class="ce-toolbar">
    <div class="ce-mode-toggle">
      <button class="ce-mode-btn ce-mode-active" data-ce-mode="purchase">ALIŞ (Suppliers)</button>
      <button class="ce-mode-btn" data-ce-mode="sales">SATIŞ (Customers)</button>
    </div>
    <div class="ce-search-wrap">
      <input id="ce-search" type="text" placeholder="Search name or tax id…" autocomplete="off" />
      <span id="ce-search-status"></span>
    </div>
  </div>

  <div class="ce-layout">
    <aside class="ce-list-pane">
      <div class="ce-list-header">
        <span id="ce-list-count">—</span>
        <span class="ce-list-hint">sorted by 24-month TL</span>
      </div>
      <ul id="ce-list" class="ce-list"></ul>
    </aside>

    <main class="ce-detail-pane">
      <div id="ce-detail-empty" class="ce-empty">
        <p>Select a counterparty from the list to see details.</p>
      </div>
      <div id="ce-detail" style="display:none;">
        <header class="ce-detail-header">
          <div class="ce-detail-name-block">
            <h3 id="ce-detail-name">—</h3>
            <div id="ce-detail-badges" class="ce-badges"></div>
          </div>
          <div class="ce-detail-meta" id="ce-detail-meta"></div>
        </header>

        <section class="ce-summary-grid">
          <div class="ce-stat"><div class="ce-stat-label">24m TL</div><div class="ce-stat-value" id="ce-stat-tl">—</div></div>
          <div class="ce-stat"><div class="ce-stat-label">24m USD</div><div class="ce-stat-value" id="ce-stat-usd">—</div></div>
          <div class="ce-stat"><div class="ce-stat-label">24m EUR</div><div class="ce-stat-value" id="ce-stat-eur">—</div></div>
          <div class="ce-stat"><div class="ce-stat-label">Rows</div><div class="ce-stat-value" id="ce-stat-rows">—</div></div>
          <div class="ce-stat"><div class="ce-stat-label">Share of side</div><div class="ce-stat-value" id="ce-stat-share">—</div></div>
          <div class="ce-stat"><div class="ce-stat-label">Last invoice</div><div class="ce-stat-value" id="ce-stat-last">—</div></div>
        </section>

        <section class="ce-block">
          <h4>Monthly trend (TL)</h4>
          <div id="ce-monthly-chart" class="ce-chart"></div>
        </section>

        <div class="ce-row-2col">
          <section class="ce-block">
            <h4>Bucket split</h4>
            <table class="ce-table" id="ce-bucket-table"><thead><tr><th>Bucket</th><th class="num">TL</th><th class="num">%</th><th class="num">Rows</th></tr></thead><tbody></tbody></table>
          </section>
          <section class="ce-block">
            <h4>Currency split</h4>
            <table class="ce-table" id="ce-ccy-table"><thead><tr><th>Currency</th><th class="num">TL</th><th class="num">Rows</th></tr></thead><tbody></tbody></table>
          </section>
        </div>

        <div class="ce-row-2col">
          <section class="ce-block">
            <h4>Top accounts</h4>
            <table class="ce-table" id="ce-accounts-table"><thead><tr><th>Code</th><th>Description</th><th class="num">TL</th><th class="num">Rows</th></tr></thead><tbody></tbody></table>
          </section>
          <section class="ce-block">
            <h4>Subtype split</h4>
            <table class="ce-table" id="ce-subtype-table"><thead><tr><th>Subtype</th><th class="num">TL</th><th class="num">Rows</th></tr></thead><tbody></tbody></table>
          </section>
        </div>

        <section class="ce-block">
          <h4>Classification quality</h4>
          <div class="ce-quality-strip" id="ce-quality"></div>
        </section>

        <section class="ce-block">
          <h4>Recent rows (last 20)</h4>
          <table class="ce-table" id="ce-recent-table"><thead><tr><th>Date</th><th>Account</th><th>Bucket</th><th class="num">TL</th><th>Ccy</th></tr></thead><tbody></tbody></table>
        </section>
      </div>
    </main>
  </div>
</section>
<!-- === END COUNTERPARTY EXPLORER (M2.1) === -->
'''


# ─────────────────────────────────────────────────────────────────────────
# JavaScript (loader + render)
# ─────────────────────────────────────────────────────────────────────────


JS_BLOCK = '''

// === COUNTERPARTY EXPLORER (M2.1) ===
const CE = {
  mode: 'purchase',
  query: '',
  selected: null,
  searchTimer: null,
  list: [],
};

function ceInit() {
  // Mode toggle
  document.querySelectorAll('[data-ce-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-ce-mode]').forEach(b => b.classList.remove('ce-mode-active'));
      btn.classList.add('ce-mode-active');
      CE.mode = btn.dataset.ceMode;
      CE.selected = null;
      document.getElementById('ce-detail').style.display = 'none';
      document.getElementById('ce-detail-empty').style.display = 'block';
      ceFetchList();
    });
  });

  const inp = document.getElementById('ce-search');
  if (inp) {
    inp.addEventListener('input', () => {
      CE.query = inp.value.trim();
      clearTimeout(CE.searchTimer);
      CE.searchTimer = setTimeout(ceFetchList, 250);
    });
  }
}

async function ceFetchList() {
  const status = document.getElementById('ce-search-status');
  if (status) status.textContent = '…';
  try {
    const url = `/api/internal/counterparties?side=${CE.mode}&q=${encodeURIComponent(CE.query)}&limit=50`;
    const data = await api(url);
    CE.list = data.results || [];
    ceRenderList();
    if (status) status.textContent = `${data.count} result${data.count === 1 ? '' : 's'}`;
  } catch (e) {
    console.error('ceFetchList error', e);
    if (status) status.textContent = 'error';
  }
}

function ceRenderList() {
  const ul = document.getElementById('ce-list');
  const countEl = document.getElementById('ce-list-count');
  if (!ul) return;
  ul.innerHTML = '';
  if (countEl) countEl.textContent = `${CE.list.length} entit${CE.list.length === 1 ? 'y' : 'ies'}`;

  CE.list.forEach(item => {
    const li = document.createElement('li');
    li.className = 'ce-list-item';
    if (CE.selected && CE.selected.canonical_key === item.canonical_key) {
      li.classList.add('ce-list-item-active');
    }

    const badges = [];
    if (!item.is_verified) badges.push('<span class="ce-badge ce-badge-warn" title="Tax id missing — name-grouped (collision risk)">no-tax</span>');
    if (item.name_variants_count > 1) badges.push(`<span class="ce-badge ce-badge-info" title="${item.name_variants_count} name spellings detected">${item.name_variants_count}var</span>`);

    li.innerHTML = `
      <div class="ce-li-name">${escapeHtml(item.display_name || '<unknown>')}</div>
      <div class="ce-li-meta">
        <span class="ce-li-amount">${ceFmtTL(item.total_tl_24m)}</span>
        <span class="ce-li-rows">${item.row_count_24m} rows</span>
        ${badges.length ? '<span class="ce-li-badges">' + badges.join('') + '</span>' : ''}
      </div>
      ${item.vergi_numarasi ? `<div class="ce-li-tax">vn: ${item.vergi_numarasi}</div>` : ''}
    `;
    li.addEventListener('click', () => {
      CE.selected = item;
      ceRenderList();  // refresh active highlighting
      ceFetchDetail(item);
    });
    ul.appendChild(li);
  });

  if (CE.list.length === 0) {
    ul.innerHTML = '<li class="ce-list-empty">No counterparties found.</li>';
  }
}

async function ceFetchDetail(item) {
  document.getElementById('ce-detail-empty').style.display = 'none';
  const detail = document.getElementById('ce-detail');
  detail.style.display = 'block';
  document.getElementById('ce-detail-name').textContent = 'Loading…';

  try {
    const url = `/api/internal/counterparty/detail?side=${CE.mode}&canonical_key=${encodeURIComponent(item.canonical_key)}&months=24`;
    const d = await api(url);
    ceRenderDetail(d);
  } catch (e) {
    console.error('ceFetchDetail error', e);
    document.getElementById('ce-detail-name').textContent = 'Error loading detail';
  }
}

function ceRenderDetail(d) {
  document.getElementById('ce-detail-name').textContent = d.display_name || '<unknown>';

  // Badges
  const badgesEl = document.getElementById('ce-detail-badges');
  const bd = [];
  if (!d.is_verified) bd.push('<span class="ce-badge ce-badge-warn">tax id missing · name-grouped</span>');
  if (d.name_variants_count > 1) bd.push(`<span class="ce-badge ce-badge-info">${d.name_variants_count} name variants</span>`);
  if (d.counterparty_type) bd.push(`<span class="ce-badge ce-badge-neutral">${d.counterparty_type}</span>`);
  badgesEl.innerHTML = bd.join(' ');

  // Meta line
  const metaEl = document.getElementById('ce-detail-meta');
  metaEl.innerHTML = `
    <div class="ce-meta-row"><span>Tax id:</span> <strong>${d.vergi_numarasi || '—'}</strong></div>
    <div class="ce-meta-row"><span>Window:</span> <strong>${d.months}m</strong> ending ${d.data_horizon || '—'}</div>
    <div class="ce-meta-row"><span>First invoice:</span> <strong>${d.summary.first_invoice || '—'}</strong></div>
  `;

  // Summary
  document.getElementById('ce-stat-tl').textContent = ceFmtTL(d.summary.total_tl);
  document.getElementById('ce-stat-usd').textContent = d.summary.total_usd ? '$' + ceFmtNum(d.summary.total_usd) : '—';
  document.getElementById('ce-stat-eur').textContent = d.summary.total_eur ? '€' + ceFmtNum(d.summary.total_eur) : '—';
  document.getElementById('ce-stat-rows').textContent = d.summary.row_count.toLocaleString();
  document.getElementById('ce-stat-share').textContent = d.summary.share_of_total_pct.toFixed(2) + '%';
  document.getElementById('ce-stat-last').textContent = d.summary.last_invoice || '—';

  // Monthly trend (lightweight inline SVG sparkline)
  ceRenderMonthlyChart(d.monthly_trend);

  // Bucket table
  const bbody = document.querySelector('#ce-bucket-table tbody');
  bbody.innerHTML = '';
  d.bucket_split.forEach(b => {
    bbody.innerHTML += `<tr><td>${escapeHtml(b.bucket || '<null>')}</td><td class="num">${ceFmtTL(b.amount_tl)}</td><td class="num">${b.share_pct}%</td><td class="num">${b.rows}</td></tr>`;
  });

  // Currency table
  const cbody = document.querySelector('#ce-ccy-table tbody');
  cbody.innerHTML = '';
  d.currency_split.forEach(c => {
    cbody.innerHTML += `<tr><td>${escapeHtml(c.ccy)}</td><td class="num">${ceFmtTL(c.amount_tl)}</td><td class="num">${c.rows}</td></tr>`;
  });

  // Accounts table
  const abody = document.querySelector('#ce-accounts-table tbody');
  abody.innerHTML = '';
  d.top_accounts.forEach(a => {
    abody.innerHTML += `<tr><td><code>${escapeHtml(a.hesap_kodu || '')}</code></td><td>${escapeHtml((a.hesap_aciklamasi || '').slice(0, 40))}</td><td class="num">${ceFmtTL(a.amount_tl)}</td><td class="num">${a.rows}</td></tr>`;
  });

  // Subtype table
  const sbody = document.querySelector('#ce-subtype-table tbody');
  sbody.innerHTML = '';
  if (d.subtype_split.length === 0) {
    sbody.innerHTML = '<tr><td colspan="3" class="ce-empty-cell">No subtype data</td></tr>';
  } else {
    d.subtype_split.forEach(s => {
      sbody.innerHTML += `<tr><td>${escapeHtml(s.subtype || '')}</td><td class="num">${ceFmtTL(s.amount_tl)}</td><td class="num">${s.rows}</td></tr>`;
    });
  }

  // Quality strip
  const q = d.classification_quality;
  document.getElementById('ce-quality').innerHTML = `
    <div class="ce-quality-cell"><span class="ce-q-label">High confidence:</span> <strong>${q.confidence_high_pct}%</strong></div>
    <div class="ce-quality-cell"><span class="ce-q-label">Review-flagged:</span> <strong>${q.review_flagged_pct}%</strong></div>
  `;

  // Recent rows
  const rbody = document.querySelector('#ce-recent-table tbody');
  rbody.innerHTML = '';
  d.recent_rows.forEach(r => {
    rbody.innerHTML += `<tr><td>${r.fatura_tarihi || '—'}</td><td><code>${escapeHtml(r.hesap_kodu || '')}</code></td><td>${escapeHtml(r.bucket || '')}</td><td class="num">${ceFmtTL(r.amount_tl)}</td><td>${escapeHtml(r.ccy || '')}</td></tr>`;
  });
}

function ceRenderMonthlyChart(trend) {
  const container = document.getElementById('ce-monthly-chart');
  if (!container) return;
  if (!trend || trend.length === 0) {
    container.innerHTML = '<div class="ce-empty-cell">No monthly data</div>';
    return;
  }
  const w = container.clientWidth || 600;
  const h = 140;
  const pad = { l: 50, r: 10, t: 10, b: 30 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;

  const maxV = Math.max(...trend.map(p => p.amount_tl), 1);
  const barW = innerW / trend.length * 0.8;
  const step = innerW / trend.length;

  let svg = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" class="ce-svg">`;
  // Y-axis labels (3 ticks)
  for (let i = 0; i <= 3; i++) {
    const y = pad.t + innerH - (innerH * i / 3);
    const v = (maxV * i / 3);
    svg += `<line x1="${pad.l}" y1="${y}" x2="${w - pad.r}" y2="${y}" class="ce-grid"/>`;
    svg += `<text x="${pad.l - 6}" y="${y + 3}" text-anchor="end" class="ce-axis-label">${ceFmtTLShort(v)}</text>`;
  }
  // Bars
  trend.forEach((p, i) => {
    const x = pad.l + i * step + (step - barW) / 2;
    const barH = innerH * (p.amount_tl / maxV);
    const y = pad.t + innerH - barH;
    svg += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" class="ce-bar">
              <title>${p.month}: ${ceFmtTL(p.amount_tl)} (${p.rows} rows)</title>
            </rect>`;
  });
  // X-axis labels (every Nth month)
  const labelEvery = Math.max(1, Math.floor(trend.length / 8));
  trend.forEach((p, i) => {
    if (i % labelEvery !== 0 && i !== trend.length - 1) return;
    const x = pad.l + i * step + step / 2;
    const y = h - 10;
    const label = p.month.slice(2, 7);  // "26-04"
    svg += `<text x="${x}" y="${y}" text-anchor="middle" class="ce-axis-label">${label}</text>`;
  });
  svg += '</svg>';
  container.innerHTML = svg;
}

function ceFmtTL(v) {
  if (!v && v !== 0) return '—';
  return '₺' + ceFmtNum(v);
}
function ceFmtNum(v) {
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return v.toFixed(0);
}
function ceFmtTLShort(v) {
  return ceFmtNum(v);
}
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Wire up section activation
const _ceOriginalShowSection = window.showSection || null;
window.showSection = function(name) {
  if (_ceOriginalShowSection) _ceOriginalShowSection(name);
  if (name === 'counterparty') {
    if (!CE._initialized) {
      ceInit();
      CE._initialized = true;
      ceFetchList();
    }
  }
};

// Try to also initialize via the existing nav-click pathway
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-section="counterparty"]').forEach(el => {
    el.addEventListener('click', () => {
      if (!CE._initialized) {
        ceInit();
        CE._initialized = true;
        ceFetchList();
      }
    });
  });
});

// === END COUNTERPARTY EXPLORER (M2.1) ===
'''


# ─────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────


CSS_BLOCK = '''

/* === COUNTERPARTY EXPLORER (M2.1) === */
#section-counterparty .ce-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin: 12px 0 16px;
  flex-wrap: wrap;
}
.ce-mode-toggle {
  display: inline-flex;
  border: 1px solid var(--border, #d0d7de);
  border-radius: 6px;
  overflow: hidden;
}
.ce-mode-btn {
  padding: 6px 14px;
  background: #f6f8fa;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: #57606a;
}
.ce-mode-btn.ce-mode-active {
  background: #0969da;
  color: white;
}
.ce-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 480px;
}
#ce-search {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  font-size: 13px;
}
#ce-search-status {
  font-size: 12px;
  color: #57606a;
  min-width: 80px;
}

.ce-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  min-height: 600px;
}
.ce-list-pane {
  border: 1px solid #d0d7de;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.ce-list-header {
  padding: 8px 12px;
  border-bottom: 1px solid #d0d7de;
  background: #f6f8fa;
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  color: #57606a;
}
.ce-list-hint { font-style: italic; }
.ce-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  max-height: 700px;
}
.ce-list-item {
  padding: 10px 12px;
  border-bottom: 1px solid #eaeef2;
  cursor: pointer;
  font-size: 12px;
}
.ce-list-item:hover { background: #f6f8fa; }
.ce-list-item-active { background: #ddf4ff !important; }
.ce-li-name {
  font-weight: 600;
  color: #1f2328;
  margin-bottom: 4px;
  line-height: 1.3;
}
.ce-li-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 11px;
  color: #57606a;
}
.ce-li-amount { font-weight: 600; color: #0969da; }
.ce-li-rows { color: #57606a; }
.ce-li-tax { font-size: 10px; color: #6e7781; margin-top: 2px; font-family: monospace; }
.ce-list-empty { padding: 20px; text-align: center; color: #57606a; }

.ce-detail-pane {
  background: #fff;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  padding: 18px;
  overflow-y: auto;
}
.ce-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: #57606a;
}

.ce-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  border-bottom: 1px solid #eaeef2;
  padding-bottom: 12px;
  margin-bottom: 16px;
}
.ce-detail-name-block h3 {
  margin: 0 0 6px 0;
  font-size: 18px;
  color: #1f2328;
}
.ce-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.ce-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}
.ce-badge-warn { background: #fff8c5; color: #7d4e00; border: 1px solid #f1e05a; }
.ce-badge-info { background: #ddf4ff; color: #0969da; border: 1px solid #80ccff; }
.ce-badge-neutral { background: #f6f8fa; color: #57606a; border: 1px solid #d0d7de; }

.ce-detail-meta {
  font-size: 11px;
  color: #57606a;
  text-align: right;
  line-height: 1.6;
}
.ce-meta-row span { color: #6e7781; }

.ce-summary-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
  margin-bottom: 18px;
}
.ce-stat {
  background: #f6f8fa;
  border: 1px solid #eaeef2;
  border-radius: 4px;
  padding: 8px 10px;
}
.ce-stat-label {
  font-size: 10px;
  color: #6e7781;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.ce-stat-value {
  font-size: 16px;
  font-weight: 600;
  color: #1f2328;
  margin-top: 2px;
}

.ce-block {
  margin-bottom: 16px;
}
.ce-block h4 {
  font-size: 13px;
  margin: 0 0 8px 0;
  color: #1f2328;
  font-weight: 600;
}
.ce-row-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1200px) {
  .ce-row-2col { grid-template-columns: 1fr; }
  .ce-summary-grid { grid-template-columns: repeat(3, 1fr); }
  .ce-layout { grid-template-columns: 280px 1fr; }
}
@media (max-width: 900px) {
  .ce-layout { grid-template-columns: 1fr; }
  .ce-summary-grid { grid-template-columns: repeat(2, 1fr); }
}

.ce-table {
  width: 100%;
  font-size: 11px;
  border-collapse: collapse;
  background: #fff;
}
.ce-table th, .ce-table td {
  padding: 5px 8px;
  border-bottom: 1px solid #eaeef2;
  text-align: left;
}
.ce-table th { color: #57606a; font-weight: 600; background: #f6f8fa; }
.ce-table td.num, .ce-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
.ce-empty-cell { color: #6e7781; font-style: italic; }

.ce-quality-strip {
  display: flex;
  gap: 24px;
  font-size: 12px;
  background: #f6f8fa;
  padding: 8px 12px;
  border-radius: 4px;
}
.ce-q-label { color: #6e7781; }

.ce-chart {
  background: #fafbfc;
  border: 1px solid #eaeef2;
  border-radius: 4px;
  min-height: 140px;
}
.ce-svg { width: 100%; height: 140px; }
.ce-bar { fill: #0969da; opacity: 0.8; }
.ce-bar:hover { opacity: 1; }
.ce-grid { stroke: #eaeef2; stroke-width: 1; }
.ce-axis-label { font-size: 9px; fill: #6e7781; font-family: -apple-system, sans-serif; }

/* === END COUNTERPARTY EXPLORER (M2.1) === */
'''


# ─────────────────────────────────────────────────────────────────────────
# Sidebar nav item
# ─────────────────────────────────────────────────────────────────────────


SIDEBAR_HTML = '''      <li class="nav-item" data-section="counterparty"><span class="nav-icon">👥</span> Counterparty Explorer</li>
'''


# ─────────────────────────────────────────────────────────────────────────
# Patch logic
# ─────────────────────────────────────────────────────────────────────────


def patch_file(path: Path, marker: str, content: str, anchor: str | None = None,
               anchor_position: str = "before", description: str = ""):
    """Generic patcher. If `anchor` is provided, inserts content before/after it.
    Otherwise appends to end of file. Idempotent via `marker`."""
    if not path.exists():
        print(f"  ❌ {path} not found")
        return False

    text = path.read_text(encoding="utf-8")

    if marker in text:
        print(f"  ⏭  {path.name} already patched ({description}); skipping.")
        return False

    bak = path.with_suffix(path.suffix + ".bak_m21")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")
        print(f"  💾 backup: {bak}")

    if anchor and anchor in text:
        if anchor_position == "before":
            new_text = text.replace(anchor, content + anchor, 1)
        else:
            new_text = text.replace(anchor, anchor + content, 1)
    else:
        new_text = text + content

    path.write_text(new_text, encoding="utf-8")
    print(f"  ✓ patched {path.name} ({description})")
    return True


def patch_sidebar():
    """Insert sidebar nav item near other internal-data nav items."""
    if not INDEX_HTML.exists():
        print(f"  ❌ {INDEX_HTML} not found")
        return False

    text = INDEX_HTML.read_text(encoding="utf-8")

    if SIDEBAR_MARKER in text:
        print(f"  ⏭  sidebar nav item already present; skipping.")
        return False

    bak = INDEX_HTML.with_suffix(".html.bak_m21")
    if not bak.exists():
        bak.write_text(text, encoding="utf-8")

    # Try to find the "internal" nav item and insert after it
    import re
    pattern = r'(<li class="nav-item" data-section="internal"[^>]*>[^<]*(?:<[^>]+>[^<]*)*</li>\s*\n?)'
    match = re.search(pattern, text)
    if match:
        new_text = text[:match.end()] + SIDEBAR_HTML + text[match.end():]
        INDEX_HTML.write_text(new_text, encoding="utf-8")
        print(f"  ✓ added sidebar nav item")
        return True

    # Fallback: try a more permissive pattern
    if 'data-section="internal"' in text:
        idx = text.find("</li>", text.find('data-section="internal"'))
        if idx >= 0:
            insertion_point = idx + len("</li>") + 1
            new_text = text[:insertion_point] + "\n" + SIDEBAR_HTML + text[insertion_point:]
            INDEX_HTML.write_text(new_text, encoding="utf-8")
            print(f"  ✓ added sidebar nav item (fallback)")
            return True

    print(f"  ⚠️  could not find anchor for sidebar; you'll need to add manually:")
    print(f"      {SIDEBAR_HTML.strip()}")
    return False


def main():
    print("Installing Counterparty Explorer v1 (M2.1)...")
    print()

    print("[1/5] Backend endpoints (server.py)...")
    patch_file(SERVER_PY, MARKER_SERVER, SERVER_PATCH,
               description="2 endpoints")

    print("\n[2/5] HTML section (index.html)...")
    # Try to insert before </main> or before footer
    text = INDEX_HTML.read_text(encoding="utf-8") if INDEX_HTML.exists() else ""
    anchor = "</main>" if "</main>" in text else None
    patch_file(INDEX_HTML, MARKER_HTML, HTML_SECTION,
               anchor=anchor, anchor_position="before",
               description="<section> block")

    print("\n[3/5] Sidebar nav item (index.html)...")
    patch_sidebar()

    print("\n[4/5] Frontend JS (app.v5.js)...")
    patch_file(APP_JS, MARKER_JS, JS_BLOCK,
               description="loader + render")

    print("\n[5/5] CSS (style.v5.css)...")
    patch_file(STYLE_CSS, MARKER_CSS, CSS_BLOCK,
               description="explorer styles")

    print()
    print("=" * 60)
    print("Counterparty Explorer v1 installed.")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Restart the dashboard server:")
    print("       Ctrl+C in the uvicorn terminal, then:")
    print("       python -m uvicorn dashboard.server:app --reload --port 8000")
    print("  2. Hard refresh the browser (Ctrl+Shift+R)")
    print("  3. Click 'Counterparty Explorer' in the sidebar")
    print("  4. Mode toggle: ALIŞ (Suppliers) ↔ SATIŞ (Customers)")
    print("  5. Search by name (e.g. 'ekin') or tax id (e.g. '5480')")
    print()
    print("If anything looks wrong, restore from .bak_m21 backups.")


if __name__ == "__main__":
    main()
