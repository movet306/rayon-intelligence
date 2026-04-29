"""
M2.2.5 — Currency composition mix % chart.

Backend: new endpoint /api/internal/procurement-currency-trend
Frontend: stacked bar mix % chart (TRY/USD/EUR/OTHER segments)
Layout: stacked under Concentration trend chart (B layout sequence)

Backups: .bak_m22_5 suffix
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m22_5")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/3] Adding /api/internal/procurement-currency-trend endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/procurement-currency-trend")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    # Insert just before /api/internal/top-suppliers comment block (consistent with prior insertions)
    ANCHOR = "# ── /api/internal/top-suppliers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/procurement-currency-trend ───────────────────────────────
# M2.2.5 — Procurement Phase 1 Chart 4: TL-equivalent spend by invoice
# currency (TRY/USD/EUR/OTHER) over 24m. Source: v_monthly_procurement_by_currency.
# Note: amount_tl is the invoice-date TL equivalent stored by Nebim
# (net_tutar_y), NOT a re-conversion at today's FX rate.
@app.get("/api/internal/procurement-currency-trend")
def internal_procurement_currency_trend():
    rows = _rows("""
        SELECT
            month,
            currency,
            row_count,
            amount_tl::float AS amount_tl
        FROM v_monthly_procurement_by_currency
        ORDER BY month, currency
    """)
    return {
        "data":       rows,
        "currencies": ["TRY", "USD", "EUR", "OTHER"],
        "window":     "24 months rolling",
        "scope":      "cost_model_relevant only",
        "note":       "amount_tl is invoice-date TL equivalent (net_tutar_y), not re-converted at current FX rate",
    }


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — add chart container after Concentration chart panel
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/3] Inserting Currency mix chart container into index.html...")
html = INDEX.read_text(encoding="utf-8")

if 'id="chart-ops-procurement-currency"' in html:
    print("  ⏭  Currency chart container already present")
else:
    backup(INDEX)

    # Anchor: closing of the Concentration chart panel
    OLD = '<div class="chart-panel-title">Supplier Concentration trend (top 1 / top 3 / top 10)</div>\n        <div class="chart-wrap" id="chart-ops-procurement-concentration"></div>\n      </div>'
    NEW = '<div class="chart-panel-title">Supplier Concentration trend (top 1 / top 3 / top 10)</div>\n        <div class="chart-wrap" id="chart-ops-procurement-concentration"></div>\n      </div>\n      <div class="chart-panel" style="margin-bottom:16px">\n        <div class="chart-panel-title">Currency composition mix % (invoice-date TL equivalent)</div>\n        <div class="chart-wrap" id="chart-ops-procurement-currency"></div>\n      </div>'

    if OLD not in html:
        print("  ❌ Concentration chart anchor not found")
        idx = html.find('chart-ops-procurement-concentration')
        if idx > 0:
            print("  Context: " + repr(html[idx-50:idx+250]))
        raise SystemExit(1)

    html = html.replace(OLD, NEW, 1)
    INDEX.write_text(html, encoding="utf-8")
    print("  ✓ Currency chart container inserted after Concentration chart")


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/3] Adding Currency mix chart fetch+render to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

if "renderOpsProcurementCurrencyChart" in js:
    print("  ⏭  Currency renderer already present")
else:
    backup(APP_JS)

    NEW_FN = '''

/* ── Procurement currency composition mix % chart (M2.2.5) ─────────────── */
async function loadProcurementCurrencyChart() {
  try {
    const data = await api('/api/internal/procurement-currency-trend');
    if (!data || !data.data || !data.data.length) return;
    renderOpsProcurementCurrencyChart(data);
  } catch (e) {
    console.error('procurement-currency-trend fetch failed', e);
  }
}

function renderOpsProcurementCurrencyChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = [...new Set(data.map(d => d.month))].sort();
  const currencies = payload.currencies || ['TRY', 'USD', 'EUR', 'OTHER'];

  const colorMap = {
    TRY:   C.blue,
    USD:   C.green,
    EUR:   C.orange,
    OTHER: C.muted,
  };
  const labelMap = {
    TRY:   'TRY (₺)',
    USD:   'USD ($)',
    EUR:   'EUR (€)',
    OTHER: 'Other',
  };

  // Per-month totals (TL equivalent across all currencies)
  const monthTotals = {};
  months.forEach(m => { monthTotals[m] = 0; });
  data.forEach(d => {
    if (currencies.includes(d.currency)) {
      monthTotals[d.month] = (monthTotals[d.month] || 0) + (d.amount_tl || 0);
    }
  });

  const traces = currencies.map(curr => {
    const byMonth = Object.fromEntries(
      data.filter(d => d.currency === curr)
          .map(d => [d.month, d.amount_tl || 0])
    );
    return {
      x: months,
      y: months.map(m => {
        const total = monthTotals[m] || 0;
        if (total === 0) return 0;
        return ((byMonth[m] || 0) / total) * 100;
      }),
      name: labelMap[curr] || curr,
      type: 'bar',
      marker: { color: colorMap[curr] || C.muted, opacity: 0.85 },
      hovertemplate: `${labelMap[curr] || curr}: %{y:.1f}%<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-procurement-currency', traces, {
    ...PLOTLY_BASE,
    height: 360,
    barmode: 'stack',
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: {
      ...PLOTLY_BASE.yaxis,
      ticksuffix: '%',
      range: [0, 100],
      tickvals: [0, 25, 50, 75, 100],
    },
  }, PLOTLY_CONFIG);
}
'''

    # Insert after renderOpsProcurementConcentrationChart's closing brace
    fn_start = js.find("function renderOpsProcurementConcentrationChart(payload) {")
    if fn_start < 0:
        print("  ❌ renderOpsProcurementConcentrationChart not found — patch aborted")
        raise SystemExit(1)

    brace_open = js.find("{", fn_start)
    depth = 1
    i = brace_open + 1
    while i < len(js) and depth > 0:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    fn_end = i

    js = js[:fn_end] + NEW_FN + js[fn_end:]
    print("  ✓ renderOpsProcurementCurrencyChart inserted")


# Wire the call. Same pattern as concentration: load on Procurement sub-tab activation.
WIRE_MARKER = "loadProcurementCurrencyChart hook"
if WIRE_MARKER in js:
    print("  ⏭  currency chart wiring already present")
else:
    OLD_WIRE = '''      // loadProcurementConcentrationChart hook (M2.2.4)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementConcentrationChart === 'function') {
        if (!window._procConcentrationLoaded) {
          loadProcurementConcentrationChart();
          window._procConcentrationLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadProcurementConcentrationChart hook (M2.2.4)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementConcentrationChart === 'function') {
        if (!window._procConcentrationLoaded) {
          loadProcurementConcentrationChart();
          window._procConcentrationLoaded = true;
        }
      }
      // loadProcurementCurrencyChart hook (M2.2.5)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementCurrencyChart === 'function') {
        if (!window._procCurrencyLoaded) {
          loadProcurementCurrencyChart();
          window._procCurrencyLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadProcurementCurrencyChart")
    else:
        print("  ⚠️  sub-tab anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


print()
print("=" * 60)
print("M2.2.5 — Currency composition mix chart complete.")
print("=" * 60)
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Procurement.")
print("Order: KPIs > Absolute > Mix % > Concentration > Currency mix > Top 10 table")
