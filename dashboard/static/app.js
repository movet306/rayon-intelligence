/* ── Rayon Intelligence — app.js ─────────────────────────────────────────── */

const C = {
  bg:     '#0d1117',
  card:   '#161b22',
  border: '#30363d',
  text:   '#e6edf3',
  muted:  '#8b949e',
  blue:   '#58a6ff',
  green:  '#3fb950',
  orange: '#f0883e',
  red:    '#f85149',
  purple: '#bc8cff',
};

const PLOTLY_BASE = {
  paper_bgcolor: C.card,
  plot_bgcolor:  C.card,
  font: { color: C.muted, family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', size: 11 },
  margin: { l: 10, r: 16, t: 10, b: 10 },
  xaxis: { gridcolor: C.border, linecolor: C.border, tickfont: { color: C.muted }, zerolinecolor: C.border },
  yaxis: { gridcolor: C.border, linecolor: C.border, tickfont: { color: C.muted }, zerolinecolor: C.border },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

const COUNTRY_NAMES = {
  US:'USA', DE:'Germany', NL:'Netherlands', GB:'UK', FR:'France', IT:'Italy',
  ES:'Spain', PL:'Poland', RU:'Russia', UA:'Ukraine', BY:'Belarus',
  KZ:'Kazakhstan', RO:'Romania', BG:'Bulgaria', IQ:'Iraq', SA:'Saudi Arabia',
  AE:'UAE', EG:'Egypt', MA:'Morocco', GE:'Georgia', AZ:'Azerbaijan',
  AM:'Armenia', UZ:'Uzbekistan', TM:'Turkmenistan', IR:'Iran', IL:'Israel',
  GR:'Greece', CZ:'Czech Rep.', SK:'Slovakia', HU:'Hungary', HR:'Croatia',
  RS:'Serbia', PT:'Portugal', BE:'Belgium', SE:'Sweden', DK:'Denmark',
  AT:'Austria', CH:'Switzerland', CN:'China', TW:'Taiwan', PK:'Pakistan',
  BD:'Bangladesh', IN:'India', VN:'Vietnam', MX:'Mexico', BR:'Brazil',
  TR:'Turkey (re-export)', NG:'Nigeria', ZA:'S. Africa', TN:'Tunisia', DZ:'Algeria',
};

const MATERIAL_LABELS = {
  polyester_staple_fiber: 'Polyester Staple Fibre',
  polyester_fdy:  'Polyester FDY',
  polyester_poy:  'Polyester POY',
  polyamide_fdy:  'Nylon FDY (PA6)',
  cotton_lint:    'Cotton Lint',
  pa6_chip:       'PA6 Chip',
  pa66_chip:      'PA66 Chip',
};

// Price chart order and grouping (pa6/pa66 share one panel)
const PRICE_PANELS = [
  { key: 'polyester_staple_fiber', color: C.blue },
  { key: 'polyester_fdy',          color: C.orange },
  { key: 'polyester_poy',          color: C.green },
  { key: 'polyamide_fdy',          color: C.purple },
  { key: 'cotton_lint',            color: C.orange },
  { key: '__pa_chips__',           keys: ['pa6_chip','pa66_chip'],
    colors: [C.blue, C.orange],    label: 'PA6 Chip vs PA66 Chip' },
];

/* ── State ─────────────────────────────────────────────────────────────────── */
let _internalData = null;
let _exportData   = {};

/* ── API helpers ───────────────────────────────────────────────────────────── */
async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/* ── Navigation ─────────────────────────────────────────────────────────────── */
function initNav() {
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      el.classList.add('active');
      const sec = document.getElementById('section-' + el.dataset.section);
      if (sec) sec.classList.add('active');
      // Lazy-load section on first visit
      lazyLoad(el.dataset.section);
    });
  });

  document.querySelectorAll('.sub-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sub-nav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.sub-section').forEach(s => s.classList.remove('active'));
      btn.classList.add('active');
      const sub = document.getElementById('sub-' + btn.dataset.sub);
      if (sub) sub.classList.add('active');
    });
  });
}

const _loaded = new Set();
function lazyLoad(section) {
  if (_loaded.has(section)) return;
  _loaded.add(section);
  if (section === 'prices')   loadPrices();
  if (section === 'exports')  loadExports();
  if (section === 'internal') loadInternal();
}

/* ── Header KPIs ────────────────────────────────────────────────────────────── */
async function loadStats() {
  try {
    const d = await api('/api/stats');
    setText('kpi-signals',    d.signal_count_30d ?? '—');
    setText('kpi-competitors', d.competitor_count ?? '—');
    setText('kpi-polyester',  d.polyester_price_rmb != null
      ? d.polyester_price_rmb.toLocaleString('en', {maximumFractionDigits:0})
      : '—');
    setText('kpi-hs5407',     d.hs5407_export_mn != null
      ? `$${d.hs5407_export_mn.toFixed(1)}M`
      : '—');
    setText('kpi-hs5407-period', d.hs5407_period ?? '');
    setText('last-refresh', `Refreshed ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    console.error('stats error', e);
  }
}

/* ── Market Signals ──────────────────────────────────────────────────────────── */
async function loadSignals() {
  const days = document.getElementById('filter-days').value;
  const type = document.getElementById('filter-type').value;
  const sev  = document.getElementById('filter-severity').value;
  const list = document.getElementById('signals-list');
  list.innerHTML = '<div class="loading">Loading signals…</div>';

  try {
    const data = await api(`/api/signals?days=${days}&type=${type}&severity=${sev}&limit=200`);
    setText('signal-count', `${data.length} signal${data.length !== 1 ? 's' : ''}`);

    if (!data.length) {
      list.innerHTML = '<div class="empty-state">No signals found for this filter combination.</div>';
      return;
    }
    list.innerHTML = data.map(renderSignalCard).join('');
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Error loading signals: ${e.message}</div>`;
  }
}

function renderSignalCard(r) {
  const typeBadge = `<span class="badge badge-type-${r.signal_type || 'other'}">${(r.signal_type || 'other').replace(/_/g,' ')}</span>`;
  const sevBadge  = `<span class="badge badge-sev-${r.severity || 'info'}">${r.severity || 'info'}</span>`;
  const company   = r.company_name
    ? `<div class="signal-company">⬡ ${esc(r.company_name)}</div>` : '';
  const src = (r.source_table || '').replace(/_/g,' ');
  return `
    <div class="signal-card type-${r.signal_type || 'other'}">
      <div class="signal-meta">
        ${typeBadge}${sevBadge}
        <span class="signal-source">${esc(src)}</span>
        <span class="signal-dt">${esc(r.detected_at || '')}</span>
      </div>
      <div class="signal-title">${esc(r.title || '')}</div>
      <div class="signal-body">${esc(r.summary || '')}</div>
      ${company}
    </div>`;
}

function initSignalFilters() {
  ['filter-days','filter-type','filter-severity'].forEach(id => {
    document.getElementById(id).addEventListener('change', loadSignals);
  });
}

/* ── Price Intelligence ──────────────────────────────────────────────────────── */
async function loadPrices() {
  const grid = document.getElementById('price-grid');
  grid.innerHTML = '<div class="loading">Loading price data…</div>';

  try {
    const data = await api('/api/prices');
    grid.innerHTML = '';

    PRICE_PANELS.forEach((panel, i) => {
      const div = document.createElement('div');
      div.className = 'price-panel';
      grid.appendChild(div);

      if (panel.key === '__pa_chips__') {
        renderMultiPricePanel(div, panel, data, i);
      } else {
        renderSinglePricePanel(div, panel, data[panel.key], i);
      }
    });
  } catch (e) {
    grid.innerHTML = `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

function renderSinglePricePanel(container, panel, d, idx) {
  const label = MATERIAL_LABELS[panel.key] || panel.key;
  if (!d || !d.prices || !d.prices.length) {
    container.innerHTML = `<div class="price-panel-header"><span class="price-panel-title">${label}</span></div><div class="empty-state" style="padding:20px">No data</div>`;
    return;
  }

  const cur = d.prices[d.prices.length - 1];
  const pct = d.pct_change;
  const pctHtml = pct != null
    ? `<span class="pct-badge ${pct > 0 ? 'pct-up' : pct < 0 ? 'pct-down' : 'pct-flat'}">${pct > 0 ? '+' : ''}${pct}%</span>`
    : '';

  container.innerHTML = `
    <div class="price-panel-header">
      <span class="price-panel-title">${label}</span>
      <span class="price-current">${cur.toLocaleString('en',{maximumFractionDigits:0})}</span>
      ${pctHtml}
    </div>
    <div class="price-chart-wrap" id="pchart-${idx}"></div>`;

  const trace = {
    x: d.periods, y: d.prices,
    type: 'scatter', mode: 'lines',
    line: { color: panel.color, width: 2 },
    fill: 'tozeroy',
    fillcolor: hexAlpha(panel.color, 0.08),
    hovertemplate: '%{x}<br><b>%{y:,.0f}</b><extra></extra>',
  };
  const layout = {
    ...PLOTLY_BASE,
    height: 180,
    margin: { l: 48, r: 12, t: 8, b: 28 },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -30, nticks: 6 },
    yaxis: { ...PLOTLY_BASE.yaxis, tickformat: ',d' },
    showlegend: false,
  };
  Plotly.newPlot(`pchart-${idx}`, [trace], layout, PLOTLY_CONFIG);
}

function renderMultiPricePanel(container, panel, data, idx) {
  container.innerHTML = `
    <div class="price-panel-header">
      <span class="price-panel-title">${panel.label}</span>
    </div>
    <div class="price-chart-wrap" id="pchart-${idx}"></div>`;

  const traces = panel.keys.map((k, i) => {
    const d = data[k];
    if (!d) return null;
    return {
      x: d.periods, y: d.prices,
      name: MATERIAL_LABELS[k] || k,
      type: 'scatter', mode: 'lines',
      line: { color: panel.colors[i], width: 2 },
      hovertemplate: `${MATERIAL_LABELS[k]}: %{y:,.0f}<extra></extra>`,
    };
  }).filter(Boolean);

  if (!traces.length) {
    container.querySelector('.price-chart-wrap').innerHTML = '<div class="empty-state" style="padding:20px">No data</div>';
    return;
  }

  const layout = {
    ...PLOTLY_BASE,
    height: 180,
    margin: { l: 48, r: 12, t: 8, b: 28 },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -30, nticks: 6 },
    yaxis: { ...PLOTLY_BASE.yaxis, tickformat: ',d' },
    legend: { font: { color: C.muted, size: 10 }, bgcolor: 'rgba(0,0,0,0)', x: 0, y: 1 },
    showlegend: true,
  };
  Plotly.newPlot(`pchart-${idx}`, traces, layout, PLOTLY_CONFIG);
}

/* ── Export Intelligence ─────────────────────────────────────────────────────── */
async function loadExports(hsCode) {
  const hs = hsCode || document.getElementById('hs-select').value || '5407';
  if (_exportData[hs]) {
    renderExports(_exportData[hs], hs);
    return;
  }
  try {
    const data = await api(`/api/exports?hs_code=${hs}&months=18`);
    _exportData[hs] = data;
    renderExports(data, hs);
  } catch (e) {
    document.getElementById('export-kpis').innerHTML =
      `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

function renderExports(data, hs) {
  const kpi = data.kpi || {};
  const mom = kpi.mom_pct;
  const momHtml = mom != null
    ? `<span class="${mom >= 0 ? 'stat-up' : 'stat-down'}">${mom >= 0 ? '+' : ''}${mom}% MoM</span>`
    : '<span class="stat-neutral">—</span>';

  document.getElementById('export-kpis').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">HS ${hs} Export (${kpi.latest_period || '—'})</div>
      <div class="stat-value">$${kpi.latest_value_mn != null ? kpi.latest_value_mn.toFixed(1) : '—'}M</div>
      <div class="stat-sub">${momHtml}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Month-on-Month</div>
      <div class="stat-value">${mom != null ? (mom >= 0 ? '+' : '') + mom + '%' : '—'}</div>
      <div class="stat-sub stat-neutral">${kpi.latest_period || ''}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Top Destination</div>
      <div class="stat-value" style="font-size:18px">${esc(COUNTRY_NAMES[kpi.top_dest] || kpi.top_dest || '—')}</div>
      <div class="stat-sub stat-neutral">${kpi.top_dest_mn != null ? '$' + kpi.top_dest_mn.toFixed(1) + 'M' : ''}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">HS 6006 Export</div>
      <div class="stat-value">${(data.trend?.['6006']?.values?.slice(-1)[0] ?? null) != null
        ? '$' + data.trend['6006'].values.slice(-1)[0].toFixed(1) + 'M' : '—'}</div>
      <div class="stat-sub stat-neutral">latest month</div>
    </div>`;

  // Top destinations bar chart
  const dest = data.top_destinations || [];
  document.getElementById('dest-chart-title').textContent =
    `Top ${dest.length} Destinations — HS ${hs}`;

  if (dest.length) {
    const countries = dest.map(r => COUNTRY_NAMES[r.country] || r.country).reverse();
    const vals      = dest.map(r => r.value_mn).reverse();
    Plotly.newPlot('chart-destinations', [{
      x: vals, y: countries,
      type: 'bar', orientation: 'h',
      marker: { color: C.blue, opacity: 0.85 },
      text: vals.map(v => `$${v.toFixed(1)}M`),
      textposition: 'outside',
      textfont: { color: C.muted, size: 10 },
      hovertemplate: '%{y}: $%{x:.1f}M<extra></extra>',
    }], {
      ...PLOTLY_BASE,
      height: 320,
      margin: { l: 100, r: 60, t: 12, b: 28 },
      xaxis: { ...PLOTLY_BASE.xaxis, tickprefix: '$', ticksuffix: 'M' },
      yaxis: { ...PLOTLY_BASE.yaxis, tickfont: { color: C.muted, size: 11 } },
    }, PLOTLY_CONFIG);
  }

  // Monthly trend
  const trend = data.trend || {};
  const trendTraces = [
    { hs: '5407', color: C.blue,   name: 'HS 5407 — Woven synthetic filament' },
    { hs: '6006', color: C.orange, name: 'HS 6006 — Technical knit' },
  ].map(({ hs: h, color, name }) => {
    const d = trend[h];
    if (!d) return null;
    return {
      x: d.periods, y: d.values,
      name, type: 'scatter', mode: 'lines+markers',
      line: { color, width: 2 },
      marker: { size: 4, color },
      hovertemplate: `${name}: $%{y:.1f}M<extra></extra>`,
    };
  }).filter(Boolean);

  if (trendTraces.length) {
    Plotly.newPlot('chart-trend', trendTraces, {
      ...PLOTLY_BASE,
      height: 320,
      margin: { l: 48, r: 12, t: 12, b: 36 },
      xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -30 },
      yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '$', ticksuffix: 'M', title: { text: 'USD million', font: { color: C.muted, size: 10 } } },
      legend: { bgcolor: 'rgba(0,0,0,0)', font: { color: C.muted, size: 11 } },
    }, PLOTLY_CONFIG);
  }
}

function initExportSelector() {
  document.getElementById('hs-select').addEventListener('change', e => {
    loadExports(e.target.value);
  });
}

/* ── Internal Data ───────────────────────────────────────────────────────────── */
async function loadInternal() {
  if (_internalData) return;
  try {
    _internalData = await api('/api/lescon');
    renderLescon(_internalData);
    renderYarn(_internalData);
    renderOrders(_internalData);
  } catch (e) {
    document.getElementById('lescon-metrics').innerHTML =
      `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

function renderLescon(data) {
  const s = data.summary || {};
  document.getElementById('lescon-metrics').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Total Revenue</div>
      <div class="stat-value">$${(s.total_revenue_usd||0).toLocaleString('en',{maximumFractionDigits:0})}</div>
      <div class="stat-sub stat-neutral">excl. returns</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Transactions</div>
      <div class="stat-value">${(s.total_transactions||0).toLocaleString()}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Transaction</div>
      <div class="stat-value">$${(s.avg_tx_value||0).toLocaleString('en',{maximumFractionDigits:0})}</div>
    </div>`;

  // Revenue by fabric
  const fab = data.by_fabric || [];
  if (fab.length) {
    const labels = fab.map(r => r.fabric_type).reverse();
    const revs   = fab.map(r => r.revenue_usd || 0).reverse();
    Plotly.newPlot('chart-lescon-fabric', [{
      x: revs, y: labels,
      type: 'bar', orientation: 'h',
      marker: { color: C.blue, opacity: 0.85 },
      text: revs.map(v => `$${(v/1000).toFixed(0)}K`),
      textposition: 'outside',
      textfont: { color: C.muted, size: 10 },
      hovertemplate: '%{y}: $%{x:,.0f}<extra></extra>',
    }], {
      ...PLOTLY_BASE,
      height: 320,
      margin: { l: 120, r: 60, t: 12, b: 28 },
      xaxis: { ...PLOTLY_BASE.xaxis, tickprefix: '$' },
      yaxis: { ...PLOTLY_BASE.yaxis },
    }, PLOTLY_CONFIG);
  }

  // Monthly trend area
  const mon = data.monthly || [];
  if (mon.length) {
    Plotly.newPlot('chart-lescon-monthly', [{
      x: mon.map(r => r.month),
      y: mon.map(r => r.revenue_usd || 0),
      type: 'scatter', mode: 'lines',
      fill: 'tozeroy',
      line: { color: C.green, width: 2.5 },
      fillcolor: hexAlpha(C.green, 0.1),
      hovertemplate: '%{x}: $%{y:,.0f}<extra></extra>',
    }], {
      ...PLOTLY_BASE,
      height: 320,
      margin: { l: 52, r: 12, t: 12, b: 36 },
      xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -30 },
      yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '$', tickformat: '~s' },
    }, PLOTLY_CONFIG);
  }

  // Top products table
  const prods = data.top_products || [];
  const rows = prods.map(r => `
    <tr>
      <td>${esc(r.product)}</td>
      <td class="num">${(r.tx_count||0).toLocaleString()}</td>
      <td class="num">$${(r.revenue_usd||0).toLocaleString('en',{maximumFractionDigits:0})}</td>
    </tr>`).join('');
  document.getElementById('lescon-products-table').innerHTML = `
    <table class="data-table">
      <thead><tr><th>Product</th><th class="num">Transactions</th><th class="num">Revenue (USD)</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderYarn(data) {
  const rows = data.yarn_trend || [];
  if (!rows.length) return;

  Plotly.newPlot('chart-yarn', [{
    x: rows.map(r => String(r.year)),
    y: rows.map(r => r.avg_cost || 0),
    type: 'bar',
    marker: { color: C.orange, opacity: 0.85 },
    text: rows.map(r => `$${(r.avg_cost||0).toFixed(2)}`),
    textposition: 'outside',
    textfont: { color: C.muted, size: 11 },
    customdata: rows.map(r => r.records),
    hovertemplate: 'Year %{x}<br><b>$%{y:.4f}/MT</b><br>Records: %{customdata}<extra></extra>',
  }], {
    ...PLOTLY_BASE,
    height: 320,
    margin: { l: 52, r: 12, t: 12, b: 36 },
    xaxis: { ...PLOTLY_BASE.xaxis, title: { text: 'Year', font: { color: C.muted, size: 11 } } },
    yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '$', title: { text: 'USD/MT', font: { color: C.muted, size: 11 } } },
  }, PLOTLY_CONFIG);
}

function renderOrders(data) {
  const sups = data.suppliers || [];
  if (!sups.length) return;

  // Horizontal bar — top 12
  const top12  = sups.slice(0, 12);
  const labels = top12.map(r => r.supplier).reverse();
  const counts = top12.map(r => r.order_count || 0).reverse();
  Plotly.newPlot('chart-suppliers', [{
    x: counts, y: labels,
    type: 'bar', orientation: 'h',
    marker: { color: C.purple, opacity: 0.85 },
    text: counts.map(String),
    textposition: 'outside',
    textfont: { color: C.muted, size: 10 },
    hovertemplate: '%{y}: %{x} orders<extra></extra>',
  }], {
    ...PLOTLY_BASE,
    height: 420,
    margin: { l: 120, r: 50, t: 12, b: 28 },
    xaxis: { ...PLOTLY_BASE.xaxis },
    yaxis: { ...PLOTLY_BASE.yaxis, tickfont: { color: C.muted, size: 11 } },
  }, PLOTLY_CONFIG);

  // Supplier table
  const rows = sups.map(r => `
    <tr>
      <td>${esc(r.supplier)}</td>
      <td>${esc(r.currency)}</td>
      <td class="num">${(r.order_count||0).toLocaleString()}</td>
      <td class="num">${r.total_kg ? r.total_kg.toLocaleString('en',{maximumFractionDigits:0}) : '—'}</td>
      <td class="num">${r.avg_price != null ? r.avg_price.toFixed(4) : '—'}</td>
    </tr>`).join('');
  document.getElementById('suppliers-table').innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Supplier</th><th>Currency</th>
        <th class="num">Orders</th><th class="num">Total KG</th><th class="num">Avg Price</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ── Utilities ───────────────────────────────────────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function hexAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/* ── Refresh ─────────────────────────────────────────────────────────────────── */
function initRefresh() {
  document.getElementById('refresh-btn').addEventListener('click', () => {
    _internalData = null;
    Object.keys(_exportData).forEach(k => delete _exportData[k]);
    _loaded.clear();
    loadStats();
    loadSignals();
    // Re-render whichever section is active
    const active = document.querySelector('.nav-item.active');
    if (active) {
      const sec = active.dataset.section;
      if (sec === 'prices')   loadPrices();
      if (sec === 'exports')  loadExports();
      if (sec === 'internal') loadInternal();
    }
  });
}

/* ── Boot ────────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initSignalFilters();
  initExportSelector();
  initRefresh();
  loadStats();
  loadSignals();         // signals is the default active section
});
