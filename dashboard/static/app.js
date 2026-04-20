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
  polyester_staple_fiber: 'PSF (Polyester Elyaf)',
  polyester_fdy:          'Polyester FDY',
  polyester_poy:          'Polyester POY',
  polyester_dty:          'Polyester DTY',
  polyester_yarn:         'Polyester İplik',
  pta:                    'PTA',
  cotton_lint:            'Pamuk (Ham)',
  cotton_yarn:            'Pamuk İpliği',
  polyamide_fdy:          'Naylon FDY (PA6)',
  pa6_chip:               'PA6 Chip',
  pa66_chip:              'PA66 Chip',
  rayon_yarn:             'Rayon İpliği',
  adipic_acid:            'Adipik Asit',
};

// Polyester family chart definition
const POLY_MATS = [
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
];

// All materials for summary table (ordered by family)
const ALL_PRICE_MATS = [
  { key: 'polyester_staple_fiber', fam: 'polyester' },
  { key: 'polyester_fdy',          fam: 'polyester' },
  { key: 'polyester_poy',          fam: 'polyester' },
  { key: 'polyester_dty',          fam: 'polyester' },
  { key: 'polyester_yarn',         fam: 'polyester' },
  { key: 'pta',                    fam: 'polyester' },
  { key: 'cotton_lint',            fam: 'cotton'    },
  { key: 'cotton_yarn',            fam: 'cotton'    },
  { key: 'polyamide_fdy',          fam: 'nylon'     },
  { key: 'pa6_chip',               fam: 'nylon'     },
  { key: 'pa66_chip',              fam: 'nylon'     },
  { key: 'adipic_acid',            fam: 'nylon'     },
  { key: 'rayon_yarn',             fam: 'rayon'     },
];

/* ── State ─────────────────────────────────────────────────────────────────── */
let _internalData = null;
let _exportData   = {};
let _priceData    = null;
let _polyMode     = 'price';
let _currency     = 'usd';   // 'rmb' | 'usd'

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
  if (section === 'prices')   loadPriceDashboard();
  if (section === 'exports')  loadExports();
  if (section === 'internal') loadInternal();
}

/* ── Header KPIs ────────────────────────────────────────────────────────────── */
async function loadStats() {
  try {
    const d = await api('/api/stats');
    setText('kpi-signals',    d.signal_count_30d ?? '—');
    setText('kpi-competitors', d.competitor_count ?? '—');
    const polyUsd = d.polyester_price_usd ?? (d.polyester_price_rmb != null && d.rmb_usd_rate
      ? d.polyester_price_rmb * d.rmb_usd_rate : null);
    setText('kpi-polyester', polyUsd != null
      ? `$${polyUsd.toLocaleString('en', {maximumFractionDigits:0})}` : '—');
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

    // Attach click handlers after DOM is ready — avoids inline onclick quoting issues
    list.querySelectorAll('.signal-card[data-url]').forEach(card => {
      const url = card.dataset.url;
      card.style.cursor = 'pointer';
      card.title = 'Haberi aç';
      card.addEventListener('click', function () {
        if (url && url.startsWith('http')) window.open(url, '_blank');
      });
    });
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Error loading signals: ${e.message}</div>`;
  }
}

function renderSignalCard(r) {
  const typeBadge = `<span class="badge badge-type-${r.signal_type || 'other'}">${(r.signal_type || 'other').replace(/_/g,' ')}</span>`;
  const sevBadge  = `<span class="badge badge-sev-${r.severity || 'info'}">${r.severity || 'info'}</span>`;
  const company   = r.company_name
    ? `<div class="signal-company">⬡ ${esc(r.company_name)}</div>` : '';
  const src     = (r.source_table || '').replace(/_/g,' ');
  const hasUrl  = r.source_url && r.source_url.startsWith('http');
  const urlAttr = hasUrl ? ` data-url="${esc(r.source_url)}"` : '';
  const linkIcon = hasUrl ? `<span class="signal-link-icon">↗</span>` : '';
  return `
    <div class="signal-card type-${r.signal_type || 'other'}"${urlAttr}>
      <div class="signal-meta">
        ${typeBadge}${sevBadge}
        <span class="signal-source">${esc(src)}</span>
        <span class="signal-dt">${esc(r.detected_at || '')}</span>
        ${linkIcon}
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

const PRICE_CHART_LAYOUT = {
  paper_bgcolor: '#161b22',
  plot_bgcolor:  '#161b22',
  font: { color: '#8b949e', family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', size: 11 },
  margin: { l: 40, r: 20, t: 10, b: 40 },
  xaxis: { gridcolor: '#30363d', linecolor: '#30363d', tickfont: { color: '#8b949e' }, zerolinecolor: '#30363d' },
  yaxis: { gridcolor: '#30363d', linecolor: '#30363d', tickfont: { color: '#8b949e' }, zerolinecolor: '#30363d' },
};

async function loadPriceDashboard() {
  // Fire signals bar immediately (independent request)
  _loadPriceSignalsBar();

  if (_priceData) {
    _renderPriceDashboard(_priceData);
    return;
  }
  // Show skeleton while loading
  document.getElementById('chart-polyester').innerHTML =
    '<div class="loading">Fiyat verisi yükleniyor…</div>';
  document.getElementById('poly-metric-cards').innerHTML = '';

  try {
    _priceData = await api('/api/prices');
    _renderPriceDashboard(_priceData);
  } catch (e) {
    document.getElementById('chart-polyester').innerHTML =
      `<div class="empty-state">Hata: ${esc(e.message)}</div>`;
  }
}

async function _loadPriceSignalsBar() {
  const bar = document.getElementById('price-signals-bar');
  try {
    const signals = await api('/api/price_signals');
    _renderPriceSignalsBar(bar, signals);
  } catch (_) {
    bar.innerHTML = '<span class="price-signal-badge badge-neutral">Sinyaller yüklenemedi</span>';
  }
}

function _renderPriceSignalsBar(bar, response) {
  // Accept both old array format and new {signals, suppressed} format
  const signals    = Array.isArray(response) ? response : (response.signals || []);
  const suppressed = Array.isArray(response) ? 0        : (response.suppressed || 0);

  if (!signals.length && !suppressed) {
    bar.innerHTML = '<span class="price-signal-badge badge-neutral">Sinyal yok — piyasalar sakin</span>';
    return;
  }

  let html = signals.map(s => {
    const cls = s.severity === 'warning' ? 'badge-warning'
              : s.severity === 'alert'   ? 'badge-alert'
              :                            'badge-info';
    return `<span class="price-signal-badge ${cls}">${esc(s.text)}</span>`;
  }).join('');

  if (suppressed) {
    html += `<span class="signals-suppressed-note">${suppressed} materyal susturuldu — yetersiz veri</span>`;
  }
  bar.innerHTML = html || '<span class="price-signal-badge badge-neutral">Sinyal yok — piyasalar sakin</span>';
}

function _renderPriceDashboard(data) {
  _updateRateNote(data);
  _renderPolyesterFamily(data, _polyMode);
  _renderPolyMetricCards(data);
  _renderSecondaryCharts(data);
  _renderPriceSummaryTable(data);
}

function _priceVal(point) {
  // Pick price_usd or price (RMB) depending on current currency selection.
  // Spread mode always uses raw values (both legs same currency).
  if (_currency === 'usd') return point.price_usd ?? point.price;
  return point.price;
}

function _latestPrice(latest) {
  if (_currency === 'usd') return latest?.price_usd ?? latest?.price;
  return latest?.price;
}

function _priceFmt(v) {
  if (v == null) return '—';
  if (_currency === 'usd') return `$${v.toLocaleString('en', {maximumFractionDigits: 2})}`;
  return v.toLocaleString('en', {maximumFractionDigits: 0});
}

function _updateRateNote(data) {
  const el = document.getElementById('currency-rate-note');
  if (!el) return;
  const meta = data?.meta;
  if (meta?.rmb_usd_rate && meta?.rate_date) {
    el.textContent = `1 CNY = ${meta.rmb_usd_rate.toFixed(4)} USD (${meta.rate_date})`;
  } else if (meta?.rmb_usd_rate) {
    el.textContent = `1 CNY = ${meta.rmb_usd_rate.toFixed(4)} USD`;
  } else {
    el.textContent = '';
  }
}

// ── Polyester family chart ────────────────────────────────────────────────────

function _renderPolyesterFamily(data, mode) {
  const traces = [];

  const hoverFmt = _currency === 'usd' ? '$.2f' : ',.0f';

  if (mode === 'price') {
    POLY_MATS.forEach(m => {
      const d = data[m.key];
      if (!d || !d.series.length) return;
      const conf = d.latest?.confidence_level || 'minimal';
      const x = d.series.map(p => p.date);
      const y = d.series.map(p => _priceVal(p));

      if (conf === 'minimal') {
        traces.push({
          x, y, name: `${m.label} (yetersiz veri)`,
          type: 'scatter', mode: 'lines',
          line: { color: m.color, width: 1.5, dash: 'dot' },
          opacity: 0.3,
          hovertemplate: `${m.label}: %{y:${hoverFmt}} (yetersiz veri)<extra></extra>`,
        });
        return;
      }

      traces.push({
        x, y, name: m.label, type: 'scatter', mode: 'lines',
        line: { color: m.color, width: 2.5 },
        hovertemplate: `${m.label}: %{y:${hoverFmt}}<extra></extra>`,
      });
      // MA7: scale MA7 (RMB) by same rate if in USD mode
      const rate = data.meta?.rmb_usd_rate ?? 1;
      const yMa7 = d.series.map(p => {
        if (p.ma7 == null) return null;
        return _currency === 'usd' ? p.ma7 * rate : p.ma7;
      });
      if (yMa7.some(v => v != null)) {
        traces.push({
          x, y: yMa7, name: `${m.label} MA7`,
          type: 'scatter', mode: 'lines',
          line: { color: m.color, width: 1.5, dash: 'dash' },
          opacity: 0.5, showlegend: false, hoverinfo: 'skip',
        });
      }
    });

  } else if (mode === 'normalize') {
    POLY_MATS.forEach(m => {
      const d = data[m.key];
      if (!d || !d.series.length) return;
      const conf = d.latest?.confidence_level || 'minimal';
      if (conf === 'minimal') return;
      const first = _priceVal(d.series[0]);
      if (!first) return;
      traces.push({
        x: d.series.map(p => p.date),
        y: d.series.map(p => { const v = _priceVal(p); return v != null ? (v / first) * 100 : null; }),
        name: m.label, type: 'scatter', mode: 'lines',
        line: { color: m.color, width: 2.5 },
        hovertemplate: `${m.label}: %{y:.1f}<extra></extra>`,
      });
    });

  } else if (mode === 'spread') {
    // Always use RMB prices for spreads (consistent basis; USD just scales both legs equally)
    const pairs = [
      { matA: 'polyester_staple_fiber', matB: 'polyester_fdy',  label: 'FDY − PSF', color: C.orange },
      { matA: 'polyester_poy',          matB: 'polyester_dty',  label: 'DTY − POY', color: '#a371f7' },
    ];
    pairs.forEach(({ matA, matB, label, color }) => {
      const dA = data[matA], dB = data[matB];
      if (!dA || !dB) return;
      const mapA = Object.fromEntries(dA.series.map(p => [p.date, _priceVal(p)]));
      const pts = dB.series
        .filter(p => _priceVal(p) != null && mapA[p.date] != null)
        .map(p => ({ date: p.date, val: _priceVal(p) - mapA[p.date] }));
      if (!pts.length) return;
      traces.push({
        x: pts.map(p => p.date),
        y: pts.map(p => p.val),
        name: label, type: 'scatter', mode: 'lines',
        fill: 'tozeroy', fillcolor: hexAlpha(color, 0.15),
        line: { color, width: 2 },
        hovertemplate: `${label}: %{y:${hoverFmt}}<extra></extra>`,
      });
    });
  }

  const yUnit = _currency === 'usd' ? 'USD/t' : 'RMB/t';
  const layout = {
    ...PRICE_CHART_LAYOUT,
    height: 360,
    xaxis: {
      ...PRICE_CHART_LAYOUT.xaxis,
      rangeslider: { bgcolor: '#0d1117', thickness: 0.08 },
    },
    yaxis: {
      ...PRICE_CHART_LAYOUT.yaxis,
      tickformat: mode === 'normalize' ? '.0f' : (_currency === 'usd' ? '$.2f' : ',d'),
      title: { text: yUnit, font: { color: C.muted, size: 11 } },
    },
    legend: { bgcolor: 'rgba(0,0,0,0)', font: { color: C.muted, size: 11 } },
    showlegend: true,
  };

  if (!traces.length) {
    document.getElementById('chart-polyester').innerHTML =
      '<div class="empty-state" style="padding:40px">Veri yok</div>';
    return;
  }
  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);
}

// ── Polyester metric cards ────────────────────────────────────────────────────

function _renderPolyMetricCards(data) {
  const container = document.getElementById('poly-metric-cards');
  container.innerHTML = POLY_MATS.map(m => {
    const d    = data[m.key];
    const l    = d?.latest;
    const conf = l?.confidence_level || (d ? 'minimal' : null);
    const isMinimal = conf === 'minimal' || !d;

    const pv    = _latestPrice(l);
    const price = _priceFmt(pv);

    // Minimal confidence: show price only, no other metrics
    if (isMinimal) {
      return `
        <div class="poly-metric-card" style="border-top: 3px solid ${m.color}; opacity: 0.5"
             title="Yetersiz veri — 7'den az veri noktası">
          <div class="card-label">${m.label}</div>
          <div class="card-price">${price}</div>
          <div class="card-meta"><span class="pct-badge pct-flat">—</span></div>
        </div>`;
    }

    const c7 = l?.change_7d;
    const c7Html = c7 != null
      ? `<span class="pct-badge ${c7 > 0 ? 'pct-up' : c7 < 0 ? 'pct-down' : 'pct-flat'}">${c7 > 0 ? '+' : ''}${c7.toFixed(1)}%</span>`
      : '';

    const trend = l?.trend_direction;
    const trendHtml = trend === 'up'   ? '<span class="trend-arrow trend-up">↑</span>'
                    : trend === 'down' ? '<span class="trend-arrow trend-down">↓</span>'
                    : trend === 'flat' ? '<span class="trend-arrow trend-flat">→</span>'
                    : '';

    const vol = l?.volatility_7d != null
      ? `<span class="card-vol">σ ${l.volatility_7d.toFixed(1)}</span>` : '';

    return `
      <div class="poly-metric-card" style="border-top: 3px solid ${m.color}">
        <div class="card-label">${m.label}</div>
        <div class="card-price">${price}</div>
        <div class="card-meta">${c7Html}${trendHtml}${vol}</div>
      </div>`;
  }).join('');
}

// ── Secondary charts ──────────────────────────────────────────────────────────

function _renderSecondaryCharts(data) {
  // Cotton & Raw
  _renderMultiLine('chart-cotton-raw', [
    { key: 'cotton_lint', color: C.orange, label: 'Pamuk Ham' },
    { key: 'pta',         color: C.blue,   label: 'PTA' },
  ], data);

  // Nylon
  _renderMultiLine('chart-nylon', [
    { key: 'pa6_chip',     color: C.blue,   label: 'PA6 Chip' },
    { key: 'pa66_chip',    color: C.orange, label: 'PA66 Chip' },
    { key: 'polyamide_fdy', color: C.purple, label: 'Naylon FDY' },
  ], data);
}

function _renderMultiLine(elId, mats, data) {
  const hoverFmt = _currency === 'usd' ? '$.2f' : ',.0f';
  const traces = mats.map(m => {
    const d = data[m.key];
    if (!d || !d.series.length) return null;
    return {
      x: d.series.map(p => p.date),
      y: d.series.map(p => _priceVal(p)),
      name: m.label, type: 'scatter', mode: 'lines',
      line: { color: m.color, width: 2 },
      hovertemplate: `${m.label}: %{y:${hoverFmt}}<extra></extra>`,
    };
  }).filter(Boolean);

  if (!traces.length) {
    document.getElementById(elId).innerHTML =
      '<div class="empty-state" style="padding:40px">Veri yok</div>';
    return;
  }
  Plotly.newPlot(elId, traces, {
    ...PRICE_CHART_LAYOUT,
    height: 320,
    yaxis: {
      ...PRICE_CHART_LAYOUT.yaxis,
      tickformat: _currency === 'usd' ? '$.2f' : ',d',
    },
    legend: { bgcolor: 'rgba(0,0,0,0)', font: { color: C.muted, size: 10 } },
    showlegend: true,
  }, PLOTLY_CONFIG);
}

// ── Summary table ─────────────────────────────────────────────────────────────

function _renderPriceSummaryTable(data) {
  const fmtPct = v => {
    if (v == null) return '<span class="muted">—</span>';
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };
  const trendArrow = t => {
    if (!t) return '<span class="muted">—</span>';
    if (t === 'up')   return '<span class="stat-up">↑</span>';
    if (t === 'down') return '<span class="stat-down">↓</span>';
    return '<span class="stat-neutral">→</span>';
  };
  const confBadge = conf => {
    if (!conf) return '';
    const cls = { high: 'conf-high', medium: 'conf-medium', low: 'conf-low', minimal: 'conf-minimal' }[conf] || '';
    return `<span class="conf-badge ${cls}">${conf}</span>`;
  };
  const INS = '<span class="muted">—</span>';

  const rows = ALL_PRICE_MATS.map(m => {
    const d    = data[m.key];
    const pts  = d?.series.length || 0;
    const l    = d?.latest;
    const conf = l?.confidence_level || (pts >= 30 ? 'high' : pts >= 14 ? 'medium' : pts >= 7 ? 'low' : 'minimal');
    const isMinimal = conf === 'minimal';

    const famCls  = m.fam === 'polyester' ? 'fam-polyester'
                  : m.fam === 'nylon'     ? 'fam-nylon' : '';
    const minCls  = isMinimal ? 'row-minimal' : '';
    const tooltip = isMinimal ? ` title="7'den az veri noktası — metrikler devre dışı"` : "";

    return `<tr class="${famCls} ${minCls}"${tooltip}>
      <td>${esc(MATERIAL_LABELS[m.key] || m.key)}</td>
      <td class="num">${_priceFmt(_latestPrice(l))}</td>
      <td class="num">${fmtPct(l?.change_1d)}</td>
      <td class="num">${fmtPct(l?.change_7d)}</td>
      <td class="num">${fmtPct(l?.change_30d)}</td>
      <td class="num">${trendArrow(l?.trend_direction)}</td>
      <td class="num">${l?.volatility_7d != null ? l.volatility_7d.toFixed(1) : INS}</td>
      <td class="num">${confBadge(conf)}</td>
      <td class="num" style="color:var(--muted);font-size:11px">${pts}</td>
    </tr>`;
  }).join('');

  document.getElementById('price-summary-table').innerHTML = `
    <table class="data-table">
      <thead><tr>
        <th>Materyal</th>
        <th class="num">Fiyat (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})</th>
        <th class="num">1G%</th>
        <th class="num">7G%</th>
        <th class="num">30G%</th>
        <th class="num">Trend</th>
        <th class="num">Volatilite</th>
        <th class="num">Güven</th>
        <th class="num">Veri</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Price section init ────────────────────────────────────────────────────────

function initPriceSection() {
  // Currency toggle buttons
  document.querySelectorAll('#currency-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#currency-toggle .toggle-btn')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _currency = btn.dataset.currency;
      if (_priceData) _renderPriceDashboard(_priceData);
    });
  });

  // Polyester chart-mode toggle buttons
  document.querySelectorAll('#poly-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#poly-toggle .toggle-btn')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _polyMode = btn.dataset.mode;
      if (_priceData) _renderPolyesterFamily(_priceData, _polyMode);
    });
  });

  // Collapsible summary table
  const header  = document.getElementById('price-table-toggle');
  const table   = document.getElementById('price-summary-table');
  const arrow   = document.getElementById('price-table-arrow');
  let collapsed = false;
  header.addEventListener('click', () => {
    collapsed = !collapsed;
    table.style.display    = collapsed ? 'none' : '';
    arrow.textContent      = collapsed ? '▶' : '▼';
  });
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
    _priceData    = null;
    Object.keys(_exportData).forEach(k => delete _exportData[k]);
    _loaded.clear();
    loadStats();
    loadSignals();
    // Re-render whichever section is active
    const active = document.querySelector('.nav-item.active');
    if (active) {
      const sec = active.dataset.section;
      if (sec === 'prices')   loadPriceDashboard();
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
  initPriceSection();
  initRefresh();
  loadStats();
  loadSignals();         // signals is the default active section
});
