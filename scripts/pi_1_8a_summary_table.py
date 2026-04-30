"""
pi_1_8a_summary_table.py - Materials Summary table: family grouping,
sortable columns, 30D tooltip, language cleanup.

Behavior:
  Default (no sort): rows grouped by family (POLYESTER / COTTON / NYLON
                     / VISCOSE) with collapsible chevron headers.
  Sort active:       flat list with family badges on each row.
  Sort cleared:      back to grouped mode (3rd click on same column).

Sortable columns: Material, Price, 1D%, 7D%, 30D%, Quality, TR Lag.
Trend and Momentum stay categorical.

Idempotent.
"""
from pathlib import Path
import re
import io
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS   = REPO / "dashboard" / "static" / "style.v5.css"

src = APPJS.read_text(encoding="utf-8")

START_MARKER = "function _renderPriceSummaryTable(data) {"
END_MARKER   = "\n}\n\nfunction initPriceSection() {"

start_idx = src.find(START_MARKER)
if start_idx == -1:
    print("[X] could not locate _renderPriceSummaryTable in app.v5.js")
    raise SystemExit(1)

end_idx = src.find(END_MARKER, start_idx)
if end_idx == -1:
    print("[X] could not locate end of _renderPriceSummaryTable (boundary missing)")
    raise SystemExit(1)
end_idx += 2  # include the function's "}\n"

if "// PI-1.8a:" in src:
    print("[skip] PI-1.8a summary table already applied")
    raise SystemExit(0)

NEW_FN = '''function _renderPriceSummaryTable(data) {
  // PI-1.8a: family grouping + sortable columns + flat-list-when-sorted hybrid.
  const fn = _renderPriceSummaryTable;
  if (!fn._sortState)  fn._sortState  = null;
  if (!fn._collapsed)  fn._collapsed  = new Set();

  const FAMILY_LABEL = {
    polyester: 'POLYESTER',
    cotton:    'COTTON',
    nylon:     'NYLON',
    viscose:   'VISCOSE',
  };
  const FAMILY_ORDER = ['polyester', 'cotton', 'nylon', 'viscose'];

  const fmtPct = v => {
    if (v == null) return '<span class="muted">\\u2014</span>';
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };
  const fmt30 = v => {
    if (v == null) {
      return '<span class="muted" title="Insufficient history \\u2014 30D requires at least 30 days of data">\\u2014</span>';
    }
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };
  const trendArrow = t => {
    if (!t) return '<span class="muted">\\u2014</span>';
    if (t === 'up')   return '<span class="stat-up">\\u2191</span>';
    if (t === 'down') return '<span class="stat-down">\\u2193</span>';
    return '<span class="stat-neutral">\\u2192</span>';
  };
  const INS = '<span class="muted">\\u2014</span>';

  const records = ALL_PRICE_MATS.map(m => {
    const d    = data[m.key];
    const pts  = d?.series.length || 0;
    const l    = d?.latest;
    const dm   = d?.meta;
    const tier = l?.confidence_tier;
    const conf = l?.confidence_level || (pts >= 30 ? 'high' : pts >= 14 ? 'medium' : pts >= 7 ? 'low' : 'minimal');
    const isTierE   = tier === 'E' || conf === 'minimal';
    const isMinimal = conf === 'minimal';
    const lagMin = dm?.lag_min_weeks;
    const lagMax = dm?.lag_max_weeks;
    const lagMid = (lagMin && lagMax) ? (lagMin + lagMax) / 2 : null;

    return {
      key: m.key, fam: m.fam,
      label: MATERIAL_LABELS[m.key] || m.key,
      price: _latestPrice(l),
      change_1d: l?.change_1d, change_7d: l?.change_7d, change_30d: l?.change_30d,
      trend: l?.trend_direction, momentum: l?.momentum_score,
      tier, lagMin, lagMax, lagMid,
      isTierE, isMinimal,
    };
  });

  const rowHtml = (r, opts = {}) => {
    const showFamBadge = !!opts.showFamBadge;
    const famCls   = r.fam === 'polyester' ? 'fam-polyester'
                   : r.fam === 'nylon'     ? 'fam-nylon'
                   : r.fam === 'cotton'    ? 'fam-cotton'
                   : r.fam === 'viscose'   ? 'fam-viscose'
                   : '';
    const tierECls = r.isTierE   ? 'row-tier-e' : '';
    const minCls   = r.isMinimal ? 'row-minimal' : '';
    const tooltip  = r.isTierE ? ' title="Collecting data \\u2014 metrics disabled"' : '';

    const tierHtml = r.tier ? `<span class="tier-badge tier-${r.tier}">${r.tier}</span>` : INS;
    const mom      = _momentumArrow(r.momentum);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;
    const lagHtml  = (r.lagMin && r.lagMax)
      ? `<span class="turkey-lag-badge">${r.lagMin}\\u2013${r.lagMax} wk</span>`
      : INS;

    const matBadge = showFamBadge
      ? `<span class="fam-badge fam-badge-${r.fam}" title="${FAMILY_LABEL[r.fam] || r.fam}">${(FAMILY_LABEL[r.fam] || r.fam).slice(0, 3)}</span> `
      : '';

    return `<tr class="${famCls} ${tierECls} ${minCls}"${tooltip}>
      <td>${matBadge}${esc(r.label)}</td>
      <td class="num">${_priceFmt(r.price)}</td>
      <td class="num">${fmtPct(r.change_1d)}</td>
      <td class="num">${fmtPct(r.change_7d)}</td>
      <td class="num">${fmt30(r.change_30d)}</td>
      <td class="num">${trendArrow(r.trend)}</td>
      <td class="num">${momHtml}</td>
      <td class="num">${tierHtml}</td>
      <td class="num">${lagHtml}</td>
    </tr>`;
  };

  const sortIndicator = col => {
    const s = fn._sortState;
    if (!s || s.col !== col) return '';
    return s.dir === 'desc' ? ' <span class="sort-ind">\\u25BC</span>' : ' <span class="sort-ind">\\u25B2</span>';
  };
  const sortableTh = (col, label, extraCls = '') => {
    const cls = `sortable ${extraCls}`.trim();
    return `<th class="${cls}" data-sort-col="${col}">${label}${sortIndicator(col)}</th>`;
  };

  const headerHtml = `
    <thead><tr>
      ${sortableTh('label', 'Material')}
      ${sortableTh('price', `Price (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})`, 'num')}
      ${sortableTh('change_1d', '1D%', 'num')}
      ${sortableTh('change_7d', '7D%', 'num')}
      ${sortableTh('change_30d', '30D%', 'num')}
      <th class="num">Trend</th>
      <th class="num">Momentum</th>
      ${sortableTh('tier', 'Quality', 'num')}
      ${sortableTh('lagMid', 'TR Lag', 'num')}
    </tr></thead>
  `;

  let bodyHtml;
  if (fn._sortState) {
    const { col, dir } = fn._sortState;
    const sorted = records.slice().sort((a, b) => {
      const va = a[col], vb = b[col];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'string') {
        return dir === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb);
      }
      return dir === 'desc' ? vb - va : va - vb;
    });
    bodyHtml = `<tbody>${sorted.map(r => rowHtml(r, { showFamBadge: true })).join('')}</tbody>`;
  } else {
    const groups = {};
    FAMILY_ORDER.forEach(f => groups[f] = []);
    records.forEach(r => {
      if (!groups[r.fam]) groups[r.fam] = [];
      groups[r.fam].push(r);
    });
    let rowsHtml = '';
    FAMILY_ORDER.forEach(fam => {
      const items = groups[fam];
      if (!items || !items.length) return;
      const collapsed = fn._collapsed.has(fam);
      const chevron = collapsed ? '\\u25B6' : '\\u25BC';
      rowsHtml += `<tr class="fam-header" data-fam="${fam}">
        <td colspan="9"><span class="fam-chevron">${chevron}</span> <span class="fam-name">${FAMILY_LABEL[fam] || fam}</span> <span class="fam-count">(${items.length})</span></td>
      </tr>`;
      if (!collapsed) {
        rowsHtml += items.map(r => rowHtml(r, { showFamBadge: false })).join('');
      }
    });
    // Defensive: any record whose family isn't in FAMILY_ORDER ends up here.
    const leftover = records.filter(r => !FAMILY_ORDER.includes(r.fam));
    if (leftover.length) {
      const byFam = {};
      leftover.forEach(r => { (byFam[r.fam] ||= []).push(r); });
      Object.keys(byFam).forEach(fam => {
        const items = byFam[fam];
        const collapsed = fn._collapsed.has(fam);
        const chevron = collapsed ? '\\u25B6' : '\\u25BC';
        rowsHtml += `<tr class="fam-header" data-fam="${fam}">
          <td colspan="9"><span class="fam-chevron">${chevron}</span> <span class="fam-name">${(fam || 'OTHER').toUpperCase()}</span> <span class="fam-count">(${items.length})</span></td>
        </tr>`;
        if (!collapsed) {
          rowsHtml += items.map(r => rowHtml(r, { showFamBadge: false })).join('');
        }
      });
    }
    bodyHtml = `<tbody>${rowsHtml}</tbody>`;
  }

  document.getElementById('price-summary-table').innerHTML = `
    <table class="data-table summary-table">${headerHtml}${bodyHtml}</table>`;

  document.querySelectorAll('#price-summary-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sortCol;
      const s = fn._sortState;
      if (!s || s.col !== col) {
        fn._sortState = { col, dir: 'desc' };
      } else if (s.dir === 'desc') {
        fn._sortState = { col, dir: 'asc' };
      } else {
        fn._sortState = null;
      }
      _renderPriceSummaryTable(data);
    });
  });

  document.querySelectorAll('#price-summary-table tr.fam-header').forEach(tr => {
    tr.addEventListener('click', () => {
      const fam = tr.dataset.fam;
      if (fn._collapsed.has(fam)) fn._collapsed.delete(fam);
      else                         fn._collapsed.add(fam);
      _renderPriceSummaryTable(data);
    });
  });
}'''

src = src[:start_idx] + NEW_FN + src[end_idx:]
APPJS.write_text(src, encoding="utf-8")
print("[OK] _renderPriceSummaryTable rewritten")

# CSS additions
css_src = CSS.read_text(encoding="utf-8")
CSS_HEADER = "/* ── PI-1.8a: family grouping + sortable summary table"
CSS_BLOCK = """

/* ── PI-1.8a: family grouping + sortable summary table ────────────────────── */
.summary-table th.sortable {
  cursor: pointer;
  user-select: none;
}
.summary-table th.sortable:hover {
  color: var(--accent, #6cb6ff);
}
.summary-table .sort-ind {
  font-size: 10px;
  opacity: 0.85;
  color: var(--accent, #6cb6ff);
}
.summary-table tr.fam-header {
  cursor: pointer;
  user-select: none;
  background: rgba(255, 255, 255, 0.03);
}
.summary-table tr.fam-header:hover {
  background: rgba(255, 255, 255, 0.05);
}
.summary-table tr.fam-header td {
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--text, #e6e9ef);
}
.summary-table .fam-chevron {
  display: inline-block;
  width: 14px;
  font-size: 10px;
  color: var(--muted, #8a92a3);
  margin-right: 4px;
}
.summary-table .fam-count {
  color: var(--muted, #8a92a3);
  font-weight: 400;
  margin-left: 4px;
}

.fam-badge {
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.4px;
  padding: 2px 5px;
  border-radius: 3px;
  margin-right: 6px;
  vertical-align: middle;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted, #8a92a3);
}
.fam-badge-polyester { color: #8ad7ff; background: rgba(76, 154, 255, 0.12); }
.fam-badge-cotton    { color: #ffb86c; background: rgba(241, 161, 105, 0.12); }
.fam-badge-nylon     { color: #c7a3ff; background: rgba(163, 113, 247, 0.14); }
.fam-badge-viscose   { color: #7ee787; background: rgba(86, 211, 100, 0.12); }
"""

if CSS_HEADER in css_src:
    print("[skip] PI-1.8a CSS already present")
else:
    CSS.write_text(css_src.rstrip() + CSS_BLOCK, encoding="utf-8")
    print("[OK] PI-1.8a CSS appended")

# Cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
html = re.sub(r'app\.v5\.js\?v=\d+', f'app.v5.js?v={ts}', html)
html = re.sub(r'style\.v5\.css\?v=\d+', f'style.v5.css?v={ts}', html)
with io.open(INDEX, "w", encoding="utf-8", newline="") as f:
    f.write(html)
print(f"[OK] cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print("Expected:")
print("  - 4 family headers with chevrons")
print("  - Click a column header -> sort + flat list")
print("  - Click family header -> collapse/expand")
print("  - Hover '-' in 30D% -> tooltip")
