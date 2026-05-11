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
  polyester_yarn:         'Polyester Yarn',
  pta:                    'PTA',
  cotton_lint:            'Cotton (SunSirs China)',
  cotton_lint_futures:    'Cotton (ICE Futures)',
  cotton_yarn:            'Cotton Yarn',
  polyamide_fdy:          'Nylon FDY (PA6)',
  pa6_chip:               'PA6 Chip',
  pa66_chip:              'PA66 Chip',
  rayon_yarn:             'Viscose Yarn',
  adipic_acid:            'Adipic Acid',
};

const POLY_MATS = [
  // PI-1.5: PTA added (upstream trigger of polyester chain).
  // PI-1.5b: order now reflects branch structure, not the false linear chain.
  //   PTA -> PSF (staple) -> POY -> DTY (filament main) -> FDY (parallel)
  { key: 'pta',                    color: '#22c1c3',  label: 'PTA' },
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
];

// PI-2a: MATERIAL_TYPE — role of each tracked material in Rayon's procurement.
//   Direct    = bought and used directly
//   Benchmark = tracked for market awareness only
//   Proxy     = upstream / leading driver of an input we use
//   Estimate  = driver-based estimated price
// Override rule: if item-level Nebim data later shows direct purchase,
// flip Benchmark/Proxy to Direct.
const MATERIAL_TYPE = {
  // Polyester
  polyester_staple_fiber: 'Benchmark',
  polyester_fdy:          'Direct',
  polyester_poy:          'Proxy',
  polyester_dty:          'Direct',
  polyester_yarn:         'Estimate',
  pta:                    'Proxy',
  // Cotton
  cotton_lint:            'Benchmark',
  cotton_lint_futures:    'Benchmark',
  cotton_yarn:            'Direct',
  // Nylon
  polyamide_fdy:          'Direct',
  pa6_chip:                'Proxy',
  pa66_chip:               'Proxy',
  adipic_acid:             'Proxy',
  // Viscose
  rayon_yarn:              'Direct',
};
const MATERIAL_TYPE_ORDER = { Direct: 0, Benchmark: 1, Proxy: 2, Estimate: 3 };
const MATERIAL_TYPE_TOOLTIP = {
  Direct:    'Direct: bought and used in production',
  Benchmark: 'Benchmark: tracked for market awareness, not purchased',
  Proxy:     'Proxy: upstream / leading driver of an input we use',
  Estimate:  'Estimate: driver-based price, not a real quote',
};

const ALL_PRICE_MATS = [
  { key: 'polyester_staple_fiber', fam: 'polyester' },
  { key: 'polyester_fdy',          fam: 'polyester' },
  { key: 'polyester_poy',          fam: 'polyester' },
  { key: 'polyester_dty',          fam: 'polyester' },
  { key: 'polyester_yarn',         fam: 'polyester' },
  { key: 'pta',                    fam: 'polyester' },
  { key: 'cotton_lint',            fam: 'cotton'    },
  { key: 'cotton_lint_futures',    fam: 'cotton'    },
  { key: 'cotton_yarn',            fam: 'cotton'    },
  { key: 'polyamide_fdy',          fam: 'nylon'     },
  { key: 'pa6_chip',               fam: 'nylon'     },
  { key: 'pa66_chip',              fam: 'nylon'     },
  { key: 'adipic_acid',            fam: 'nylon'     },
  { key: 'rayon_yarn',             fam: 'viscose'   },
];

// PI-1.5b: linear POLY_CHAIN replaced with branched POLY_TOPOLOGY.
// Correct industrial structure: PTA splits into staple (PSF) and filament
// (POY -> DTY) branches; FDY is a parallel filament product, not a step
// downstream of POY. POLY_CHAIN kept as a derived flat list because lag-row
// rendering and a few helpers still iterate over the chain in display order.
const POLY_TOPOLOGY = {
  root: { key: 'pta', label: 'PTA', color: '#22c1c3' },
  branches: {
    staple: {
      label: 'Staple branch',
      nodes: [
        { key: 'polyester_staple_fiber', label: 'PSF', color: C.blue },
      ],
    },
    filament: {
      label: 'Filament branch',
      main: [
        { key: 'polyester_poy', label: 'POY', color: C.green },
        { key: 'polyester_dty', label: 'DTY', color: '#a371f7' },
      ],
      parallel: {
        label: 'Parallel filament',
        nodes: [
          { key: 'polyester_fdy', label: 'FDY', color: C.orange },
        ],
      },
    },
  },
};
const POLY_CHAIN = [
  POLY_TOPOLOGY.root,
  ...POLY_TOPOLOGY.branches.staple.nodes,
  ...POLY_TOPOLOGY.branches.filament.main,
  ...POLY_TOPOLOGY.branches.filament.parallel.nodes,
];

const CHAIN_UPSTREAM = {
  polyester_staple_fiber: 'pta',
  polyester_fdy:          'pta',
  polyester_poy:          'pta',
  polyester_dty:          'polyester_poy',
};

let _internalData = null;
let _exportData   = {};
let _priceData    = null;
let _polyMode     = 'price';
let _currency     = 'usd';

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function initNav() {
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      el.classList.add('active');
      const sec = document.getElementById('section-' + el.dataset.section);
      if (sec) sec.classList.add('active');
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
      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }
      // loadRevenueKpis hook (M2.3.2)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadRevenueKpis === 'function') {
        if (!window._revenueKpisLoaded) {
          loadRevenueKpis();
          window._revenueKpisLoaded = true;
        }
      }
      // loadCustomerConcentrationChart hook (M2.3.3)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadCustomerConcentrationChart === 'function') {
        if (!window._custConcentrationLoaded) {
          loadCustomerConcentrationChart();
          window._custConcentrationLoaded = true;
        }
      }
      // loadCostSuppliersTable hook (M2.4.1)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostSuppliersTable === 'function') {
        if (!window._costSuppliersLoaded) {
          loadCostSuppliersTable();
          window._costSuppliersLoaded = true;
        }
      }
      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }
      // loadCostMovers hook (M2.4.4)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostMovers === 'function') {
        if (!window._costMoversLoaded) {
          loadCostMovers();
          window._costMoversLoaded = true;
        }
      }
      // renderOpsCostMixChart hook (M2.4.3) — uses _opsData.cost already fetched
      if (btn.dataset.sub === 'ops-cost' && typeof renderOpsCostMixChart === 'function') {
        if (!window._costMixLoaded && _opsData && _opsData.cost) {
          renderOpsCostMixChart(_opsData.cost);
          window._costMixLoaded = true;
        }
      }
      // loadProcurementConcentrationChart hook (M2.2.4)
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
      }
      // Counterparty Explorer hook (M2.1)
      if (btn.dataset.sub === 'ops-counterparty' && typeof ceInit === 'function') {
        if (!window.CE || !window.CE._initialized) {
          ceInit();
          if (window.CE) window.CE._initialized = true;
        }
        if (typeof ceFetchList === 'function') ceFetchList();
      }
    });
  });
}

const _loaded = new Set();
function lazyLoad(section) {
  if (_loaded.has(section)) return;
  _loaded.add(section);
  if (section === 'prices')   loadPriceDashboard();
  if (section === 'yarn')     loadYarnIntelligence();
  if (section === 'exports')  loadExports();
  if (section === 'internal') loadInternal();
}

async function loadStats() {
  try {
    const [d, sigStats] = await Promise.all([
      api('/api/stats'),
      api('/api/signal_stats'),
    ]);
    setText('kpi-high-impact',   sigStats.high_impact_7d   ?? '—');
    setText('kpi-cost-pressure', sigStats.cost_pressure_count ?? '—');
    setText('kpi-risk',          sigStats.risk_count        ?? '—');
    const polyUsd = d.polyester_price_usd ?? (d.polyester_price_rmb != null && d.rmb_usd_rate
      ? d.polyester_price_rmb * d.rmb_usd_rate : null);
    setText('kpi-polyester', polyUsd != null
      ? `$${Math.round(polyUsd).toLocaleString('en')}` : '—');
    const chg7 = d.polyester_change_7d;
    const chgEl = document.getElementById('kpi-polyester-change');
    if (chgEl) {
      if (chg7 != null) {
        const sign = chg7 >= 0 ? '+' : '';
        chgEl.textContent = `${sign}${chg7.toFixed(1)}% 7d`;
        chgEl.style.color = chg7 >= 0 ? '#3fb950' : '#f85149';
      } else {
        chgEl.textContent = '';
      }
    }
    setText('last-refresh', `Refreshed ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    console.error('stats error', e);
  }
}

const CAT_COLORS = {
  COST_IMPACT:     '#f0883e',
  DEMAND_SHIFT:    '#58a6ff',
  SUPPLY_RISK:     '#f85149',
  COMPETITOR_MOVE: '#a371f7',
  REGULATORY:      '#3fb950',
};

let _feedRawData    = null;
let _feedMinImpact  = 50;
let _feedViewAll    = false;
let _feedThemeFilter = null;

function loadSignalsPanels() {
  _loadCriticalSignals();
  _loadSignalStats();
  _loadFeedSignals();
}

async function _loadCriticalSignals() {
  const el = document.getElementById('critical-list');
  el.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const data = await api('/api/signals?min_impact=80&days=7&limit=5');
    const real = data.filter(r => r.impact_score != null && r.impact_score >= 80);
    if (!real.length) {
      el.innerHTML = '<div class="empty-state-sm">No critical signals in the last 7 days.</div>';
      return;
    }
    el.innerHTML = real.map(renderCriticalCard).join('');
    _attachUrlHandlers(el);
  } catch (e) {
    el.innerHTML = `<div class="empty-state-sm">Error: ${esc(e.message)}</div>`;
  }
}

async function _loadSignalStats() {
  try {
    const stats = await api('/api/signal_stats');
    _renderThemeChips(stats.top_themes || []);
  } catch (_) {}
}

async function _loadFeedSignals() {
  const list = document.getElementById('signals-list');
  list.innerHTML = '<div class="loading">Loading signals…</div>';
  const viewAllParam = _feedViewAll ? '&view_all=true' : '';
  const url = `/api/signals?days=30&limit=200&exclude_critical=true${viewAllParam}`;
  try {
    _feedRawData = await api(url);
    _renderFeed();
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Error loading signals: ${esc(e.message)}</div>`;
  }
}

function _renderFeed() {
  const list = document.getElementById('signals-list');
  const data = _feedThemeFilter
    ? (_feedRawData || []).filter(r => r.theme === _feedThemeFilter)
    : (_feedRawData || []);

  setText('signal-count', `${data.length} signal${data.length !== 1 ? 's' : ''}`);

  if (!data.length) {
    list.innerHTML = '<div class="empty-state">No signals found.</div>';
  } else {
    list.innerHTML = data.map(renderSignalCard).join('');
    _attachUrlHandlers(list);
  }

  const archiveRow    = document.getElementById('feed-archive-row');
  const archiveToggle = document.getElementById('archive-toggle');
  if (_feedMinImpact > 0) {
    archiveRow.style.display = '';
    archiveToggle.textContent = `Showing signals with impact ≥ ${_feedMinImpact} · View all →`;
  } else {
    archiveRow.style.display = 'none';
  }
}

function _renderThemeChips(themes) {
  const panel = document.getElementById('panel-themes');
  const container = document.getElementById('theme-chips');
  if (!themes.length) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  container.innerHTML = themes.map(t =>
    `<span class="theme-chip" data-theme="${esc(t.theme)}">${esc(t.theme)} <span class="theme-chip-count">${t.count}</span></span>`
  ).join('');
  container.querySelectorAll('.theme-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const theme = chip.dataset.theme;
      const active = chip.classList.contains('active');
      container.querySelectorAll('.theme-chip').forEach(c => c.classList.remove('active'));
      _feedThemeFilter = active ? null : theme;
      if (!active) chip.classList.add('active');
      const clearEl = document.getElementById('theme-clear');
      if (clearEl) clearEl.style.display = _feedThemeFilter ? '' : 'none';
      _renderFeed();
    });
  });
}

function renderCriticalCard(r) {
  const borderColor = CAT_COLORS[r.signal_category] || '#f85149';
  const hasUrl  = r.source_url && r.source_url.startsWith('http');
  const urlAttr = hasUrl ? ` data-url="${esc(r.source_url)}"` : '';
  const impact  = r.impact_score != null ? r.impact_score : '—';
  const catHtml = r.signal_category
    ? `<span class="cat-badge cat-${r.signal_category}">${r.signal_category.replace(/_/g,' ')}</span>` : '';
  const actionHtml = r.action_tag
    ? `<span class="action-badge action-${r.action_tag.toLowerCase()}">${r.action_tag}</span>` : '';
  const horizonHtml = r.time_horizon
    ? `<span class="horizon-tag">${r.time_horizon.toUpperCase()}</span>` : '';
  const company = r.company_name ? `<span class="signal-company-inline">⬡ ${esc(r.company_name)}</span>` : '';
  const matHtml = r.material_form ? `<span class="signal-mat-sm">${esc(r.material_form)}</span>` : '';
  const linkIcon = hasUrl ? `<span class="signal-link-icon">↗</span>` : '';
  return `
    <div class="critical-card"${urlAttr} style="border-left: 4px solid ${borderColor}">
      <div class="critical-card-head">
        <div class="critical-card-badges">${catHtml}${actionHtml}</div>
        <div class="impact-score-badge">${impact}</div>
      </div>
      <div class="critical-card-title">${esc(r.title || '')}</div>
      <div class="critical-card-body">${esc(r.summary || '')}</div>
      <div class="critical-card-footer">
        ${company}${matHtml}${horizonHtml}
        <span class="signal-dt" style="margin-left:auto">${esc(r.detected_at || '')}${linkIcon}</span>
      </div>
    </div>`;
}

function renderSignalCard(r) {
  const borderColor = CAT_COLORS[r.signal_category] || C.border;
  const hasUrl  = r.source_url && r.source_url.startsWith('http');
  const urlAttr = hasUrl ? ` data-url="${esc(r.source_url)}"` : '';
  const linkIcon = hasUrl ? `<span class="signal-link-icon">↗</span>` : '';
  const impact  = r.impact_score != null
    ? `<span class="impact-score-sm">${r.impact_score}</span>` : '';
  const catHtml = r.signal_category
    ? `<span class="cat-badge cat-${r.signal_category}">${r.signal_category.replace(/_/g,' ')}</span>` : '';
  const actionHtml = r.action_tag
    ? `<span class="action-badge action-${r.action_tag.toLowerCase()}">${r.action_tag}</span>` : '';
  const horizonHtml = r.time_horizon
    ? `<span class="horizon-tag">${r.time_horizon.toUpperCase()}</span>` : '';
  const matHtml = r.material_form
    ? `<span class="signal-mat-sm">· ${esc(r.material_form)}</span>` : '';
  const company = r.company_name
    ? `<div class="signal-company">⬡ ${esc(r.company_name)}</div>` : '';
  return `
    <div class="signal-card"${urlAttr} style="border-left-color: ${borderColor}">
      <div class="signal-meta">
        ${catHtml}${actionHtml}${horizonHtml}${matHtml}
        <div class="signal-meta-right">
          <span class="signal-dt">${esc(r.detected_at || '')}</span>
          ${linkIcon}${impact}
        </div>
      </div>
      <div class="signal-title">${esc(r.title || '')}</div>
      <div class="signal-body">${esc(r.summary || '')}</div>
      ${company}
    </div>`;
}

function _attachUrlHandlers(container) {
  container.querySelectorAll('[data-url]').forEach(el => {
    const url = el.dataset.url;
    el.style.cursor = 'pointer';
    el.title = 'Haberi aç';
    el.addEventListener('click', () => {
      if (url && url.startsWith('http')) window.open(url, '_blank');
    });
  });
}

function initSignalsSection() {
  const archiveToggle = document.getElementById('archive-toggle');
  if (archiveToggle) {
    archiveToggle.addEventListener('click', () => {
      _feedViewAll = !_feedViewAll;
      _feedMinImpact = _feedViewAll ? 0 : 50;
      _loadFeedSignals();
    });
  }
  const clearEl = document.getElementById('theme-clear');
  if (clearEl) {
    clearEl.addEventListener('click', () => {
      _feedThemeFilter = null;
      clearEl.style.display = 'none';
      document.querySelectorAll('.theme-chip').forEach(c => c.classList.remove('active'));
      _renderFeed();
    });
  }
}

const PRICE_CHART_LAYOUT = {
  paper_bgcolor: '#161b22',
  plot_bgcolor:  '#161b22',
  font: { color: '#8b949e', family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', size: 11 },
  margin: { l: 40, r: 20, t: 10, b: 40 },
  xaxis: { gridcolor: '#30363d', linecolor: '#30363d', tickfont: { color: '#8b949e' }, zerolinecolor: '#30363d' },
  yaxis: { gridcolor: '#30363d', linecolor: '#30363d', tickfont: { color: '#8b949e' }, zerolinecolor: '#30363d' },
};

async function loadPriceDashboard() {
  _loadEarlyWarningBar();

  if (_priceData) {
    _renderPriceDashboard(_priceData);
    return;
  }
  document.getElementById('chart-polyester').innerHTML =
    '<div class="loading">Loading price data…</div>';
  document.getElementById('poly-metric-cards').innerHTML = '';

  try {
    _priceData = await api('/api/prices');
    _renderPriceDashboard(_priceData);
  } catch (e) {
    document.getElementById('chart-polyester').innerHTML =
      `<div class="empty-state">Hata: ${esc(e.message)}</div>`;
  }
}

async function _loadEarlyWarningBar() {
  const bar = document.getElementById('early-warning-bar');
  try {
    const signals = await api('/api/price_intelligence_signals');
    _renderEarlyWarningBar(bar, signals);
  } catch (_) {
    bar.innerHTML = '<div class="ew-loading">Erken uyarı sinyalleri yüklenemedi.</div>';
  }
}

function _renderEarlyWarningBar(bar, signals) {
  // PI-1.3: tiered presentation (Action / Watch / All) with hard caps.
  if (!signals || !signals.length) {
    bar.innerHTML = '<div class="no-signals-muted">No active price signals — markets calm</div>';
    return;
  }

  const SEV_LABEL  = { critical: 'CRITICAL', high: 'HIGH', medium: 'MEDIUM', low: 'LOW' };
  const TYPE_LABEL = {
    COST_PRESSURE_UP:        'Cost Pressure Up',
    COST_PRESSURE_DOWN:      'Cost Pressure Down',
    UPSTREAM_DOWNSTREAM_DIVG:'Chain Divergence',
    SPREAD_WIDENING:         'Spread Widening',
    SPREAD_TIGHTENING:       'Spread Tightening',
    VOLATILITY_SPIKE:        'Volatility',
    DELAYED_PASS_THROUGH_RISK:'Delayed Pass-Through',
    DATA_QUALITY_WARNING:    'Data Quality',
  };

  // Render a single signal card (unchanged from the previous flat version).
  const renderCard = (s) => {
    const sev      = s.severity || 'low';
    const typeText = TYPE_LABEL[s.signal_type] || s.signal_type;
    const valChip  = s.value_pct != null
      ? `<div class="ew-value-chip">${s.value_pct > 0 ? '+' : ''}${s.value_pct.toFixed(1)}%</div>` : '';
    const lagHtml  = (s.turkey_lag_min && s.turkey_lag_max)
      ? `<div class="ew-lag">&#8594; Turkey lag est.: ${s.turkey_lag_min}–${s.turkey_lag_max} weeks</div>` : '';
    const impl     = s.business_implication
      ? `<div class="ew-implication">${esc(s.business_implication)}</div>` : '';
    return `
      <div class="early-warning-card ew-card-${sev}">
        <div class="ew-left">
          <span class="ew-type-badge ew-badge-${sev}">${typeText}</span>
          <span class="ew-sev-text">${SEV_LABEL[sev] || sev}</span>
        </div>
        <div class="ew-content">
          <div class="ew-explanation">${esc(s.explanation)}</div>
          ${impl}${lagHtml}
        </div>
        ${valChip}
      </div>`;
  };

  // Tier the signals. Server already returns them sorted by severity then
  // signal_date DESC (via v_active_signals), so we just walk the array and
  // partition with hard caps.
  const ACTION_CAP = 3;
  const WATCH_CAP  = 5;

  const action = [];
  const watch  = [];
  const all    = [];

  signals.forEach(s => {
    const sev = s.severity || 'low';
    if ((sev === 'critical' || sev === 'high') && action.length < ACTION_CAP) {
      action.push(s);
    } else if (sev === 'medium' && watch.length < WATCH_CAP) {
      watch.push(s);
    } else {
      all.push(s);
    }
  });

  // Render a section. Action and Watch are open by default and always shown
  // (with a muted note when empty so the user can read "calm" at a glance).
  // All Signals is collapsed by default and hidden if empty.
  const renderSection = (label, items, opts) => {
    const { defaultOpen, idSuffix, emptyMsg, hideWhenEmpty } = opts;
    if (!items.length && hideWhenEmpty) return '';
    const openCls = defaultOpen ? 'open' : '';
    const chevron = defaultOpen ? '▼' : '▶';
    const body = items.length
      ? items.map(renderCard).join('')
      : `<div class="ew-section-empty">${emptyMsg}</div>`;
    return `
      <div class="ew-section ${openCls}" data-section="${idSuffix}">
        <div class="ew-section-header" onclick="this.parentElement.classList.toggle('open');
                                                 const c=this.querySelector('.ew-chevron');
                                                 if(c)c.textContent=this.parentElement.classList.contains('open')?'▼':'▶';">
          <span class="ew-chevron">${chevron}</span>
          <span class="ew-section-label">${label}</span>
          <span class="ew-section-count">(${items.length})</span>
        </div>
        <div class="ew-section-content">${body}</div>
      </div>`;
  };

  bar.innerHTML =
    renderSection('Action Now', action, {
      defaultOpen: true,
      idSuffix: 'action',
      emptyMsg: 'No critical / high-severity signals require action right now.',
      hideWhenEmpty: false,
    }) +
    renderSection('Watch', watch, {
      defaultOpen: true,
      idSuffix: 'watch',
      emptyMsg: 'No medium-severity signals to watch right now.',
      hideWhenEmpty: false,
    }) +
    renderSection('All Signals', all, {
      defaultOpen: false,
      idSuffix: 'all',
      emptyMsg: '',
      hideWhenEmpty: true,
    });
}

function _renderPriceDashboard(data) {
  _updateRateNote(data);
  _renderChainFlow(data);
  _renderPolyesterFamily(data, _polyMode);
  _renderPolyMetricCards(data);
  _renderPolyLagRow(data);
  _renderSecondaryCharts(data);
  _renderPriceSummaryTable(data);
}

function _momentumArrow(score) {
  if (score == null) return { icon: '→', cls: 'momentum-flat' };
  if (score >  0.3) return { icon: '↑↑', cls: 'momentum-strong-up'   };
  if (score >  0.1) return { icon: '↑',  cls: 'momentum-up'          };
  if (score > -0.1) return { icon: '→',  cls: 'momentum-flat'         };
  if (score > -0.3) return { icon: '↓',  cls: 'momentum-down'         };
  return                   { icon: '↓↓', cls: 'momentum-strong-down'  };
}

function _tierBadge(tier) {
  if (!tier) return '';
  return `<span class="tier-badge tier-${tier}">${tier}</span>`;
}

function _renderChainFlow(data) {
  // PI-1.5b v2: grouped-card layout (replaces the v1 connector-heavy layout
  // which was sparse and fragmented). PTA on top spanning full width, then
  // three group cards side by side: Staple (PSF), Filament (POY -> DTY),
  // FDY reference. No floating spread badges.
  const el = document.getElementById('chain-flow-polyester');
  if (!el) return;

  const renderNode = (node) => {
    const d        = data[node.key];
    const latest   = d?.latest;
    const price    = latest?.price_usd != null
      ? `$${Math.round(latest.price_usd).toLocaleString('en')}`
      : '—';
    const c7       = latest?.change_7d;
    const c7Html   = c7 != null
      ? `<div class="chain-node-change ${c7 > 0 ? 'stat-up' : c7 < 0 ? 'stat-down' : ''}">${c7 > 0 ? '+' : ''}${c7.toFixed(1)}%</div>`
      : '<div class="chain-node-change" style="color:var(--muted)">—</div>';
    const tier     = latest?.confidence_tier;
    const mom      = _momentumArrow(latest?.momentum_score);
    const tierHtml = _tierBadge(tier);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;
    const vol      = latest?.volatility_7d;
    const volHtml  = vol != null
      ? `<span class="chain-vol" style="font-size:11px; color:var(--muted); margin-left:6px">σ ${vol.toFixed(1)}</span>`
      : '';
    return `
      <div class="chain-node" style="border-top: 2px solid ${node.color}">
        <div class="chain-node-name">${node.label}</div>
        <div class="chain-node-price">${price}</div>
        ${c7Html}
        <div class="chain-node-footer">${tierHtml}${momHtml}${volHtml}</div>
      </div>`;
  };

  const T = POLY_TOPOLOGY;

  el.innerHTML = `
    <div class="chain-grouped">

      <div class="chain-grouped-root">
        ${renderNode(T.root)}
      </div>

      <div class="chain-grouped-arrow">&#8595;</div>

      <div class="chain-grouped-branches">

        <div class="chain-group chain-group-staple">
          <div class="chain-group-label">Staple</div>
          <div class="chain-group-flow">
            ${T.branches.staple.nodes.map(renderNode).join('')}
          </div>
        </div>

        <div class="chain-group chain-group-filament">
          <div class="chain-group-label">Filament</div>
          <div class="chain-group-flow">
            ${renderNode(T.branches.filament.main[0])}
            <span class="chain-group-arrow">&#8594;</span>
            ${renderNode(T.branches.filament.main[1])}
          </div>
        </div>

        <div class="chain-group chain-group-parallel">
          <div class="chain-group-label">FDY reference</div>
          <div class="chain-group-flow">
            ${T.branches.filament.parallel.nodes.map(renderNode).join('')}
          </div>
        </div>

      </div>
    </div>`;
}

function _renderPolyLagRow(data) {
  const el = document.getElementById('poly-lag-row');
  if (!el) return;

  const items = POLY_CHAIN.map(node => {
    const dm      = data[node.key]?.meta;
    const lagMin  = dm?.lag_min_weeks;
    const lagMax  = dm?.lag_max_weeks;
    if (!lagMin || !lagMax) return '';
    return `<div class="lag-item">
      <span class="lag-item-name">${node.label}</span>
      <span class="turkey-lag-badge">${lagMin}–${lagMax} wk</span>
    </div>`;
  }).filter(Boolean);

  if (!items.length) { el.style.display = 'none'; return; }
  el.innerHTML = `<span class="lag-row-label">&#127481;&#127479; Turkey lag:</span> ${items.join('')}`;
}

function _priceVal(point) {
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
          x, y, name: `${m.label} (insufficient data)`,
          type: 'scatter', mode: 'lines',
          line: { color: m.color, width: 1.5, dash: 'dot' },
          opacity: 0.3,
          hovertemplate: `${m.label}: %{y:${hoverFmt}} (insufficient data)<extra></extra>`,
        });
        return;
      }

      traces.push({
        x, y, name: m.label, type: 'scatter', mode: 'lines',
        line: { color: m.color, width: 2.5 },
        hovertemplate: `${m.label}: %{y:${hoverFmt}}<extra></extra>`,
      });
      // PI-1.5: MA7 dashed ghost traces removed (visual noise, no UX value).
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
  // PI-1.5: align x-axis to latest first-date across visible series.
  // Prevents the misleading "spike" effect when one series starts later.
  const _firstDates = traces
    .filter(t => Array.isArray(t.x) && t.x.length)
    .map(t => t.x[0]);
  if (_firstDates.length) {
    const _commonStart = _firstDates.sort().reverse()[0];
    const _commonEnd = traces
      .filter(t => Array.isArray(t.x) && t.x.length)
      .map(t => t.x[t.x.length - 1])
      .sort()
      .reverse()[0];
    layout.xaxis = {
      ...(layout.xaxis || {}),
      range: [_commonStart, _commonEnd],
      // PI-1.5 closeout: hide rangeslider strip (low value at this density).
      rangeslider: { visible: false },
    };
  }
  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);
}

function _renderPolyMetricCards(data) {
  // PI-1.5: detail cards are now redundant (sigma moved to chain-flow footer).
  // HTML container preserved for easy rollback; rendered as hidden no-op.
  const container = document.getElementById('poly-metric-cards');
  if (container) {
    container.innerHTML = '';
    container.style.display = 'none';
  }
  return;
  // eslint-disable-next-line no-unreachable
  /* original implementation kept below for reference, never executed:
  container.innerHTML = POLY_MATS.map(m => {
    const d    = data[m.key];
    const l    = d?.latest;
    const conf = l?.confidence_level || (d ? 'minimal' : null);
    const isMinimal = conf === 'minimal' || !d;

    const pv    = _latestPrice(l);
    const price = _priceFmt(pv);

    if (isMinimal) {
      return `
        <div class="poly-metric-card" style="border-top: 3px solid ${m.color}; opacity: 0.5"
             title="Insufficient data — fewer than 7 data points">
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

    const tier = l?.confidence_tier;
    const tierHtml = tier ? _tierBadge(tier) : '';

    const mom = _momentumArrow(l?.momentum_score);
    const momHtml = `<span class="chain-momentum ${mom.cls}" style="font-size:12px">${mom.icon}</span>`;

    return `
      <div class="poly-metric-card" style="border-top: 3px solid ${m.color}">
        <div class="card-label">${m.label}</div>
        <div class="card-price">${price}</div>
        <div class="card-meta">${c7Html}${trendHtml}${momHtml}${vol}</div>
        <div class="card-meta" style="margin-top:4px">${tierHtml}</div>
      </div>`;
  }).join('');
  */
}

function _renderSecondaryCharts(data) {
  _renderCottonPanel(data);

  _renderMultiLine('chart-nylon', [
    { key: 'pa6_chip',      color: C.blue,   label: 'PA6 Chip' },
    { key: 'pa66_chip',     color: C.orange, label: 'PA66 Chip' },
    { key: 'polyamide_fdy', color: C.purple, label: 'Nylon FDY' },
    { key: 'adipic_acid',   color: '#56d364',label: 'Adipic Acid (leading)' },
  ], data);
}

function _renderCottonPanel(data) {
  const infoEl = document.getElementById('cotton-series-info');
  if (infoEl) {
    const sunsirs  = data['cotton_lint']?.latest;
    const iceFut   = data['cotton_lint_futures']?.latest;
    const fmtP = v => v?.price_usd != null ? `$${Math.round(v.price_usd).toLocaleString('en')}/t` : '—';
    infoEl.innerHTML = `
      <div class="cotton-series-card">
        <div class="cotton-series-label">SunSirs China Spot</div>
        <div class="cotton-series-price" style="color:${C.orange}">${fmtP(sunsirs)}</div>
      </div>
      <div class="cotton-series-card">
        <div class="cotton-series-label">ICE Futures (Global)</div>
        <div class="cotton-series-price" style="color:${C.blue}">${fmtP(iceFut)}</div>
      </div>`;
  }

  const discEl = document.getElementById('cotton-disclaimer');
  if (discEl) {
    discEl.textContent = 'Different markets — not directly comparable.';
  }

  // PI-1.6: render SunSirs and ICE on separate sub-charts so they no longer
  // share a y-axis. Different markets, different price scales.
  // PI-1.7 followup: ensure both sub-charts use the same x-axis window so
  // the user reads them as one comparison, not two unrelated time series.
  // We pick the latest first-date and the latest last-date across the two
  // series so neither sub-chart shows extrapolated empty space and short
  // series aren't squeezed into a tiny corner.
  const _spotSer  = data['cotton_lint']?.series          || [];
  const _futSer   = data['cotton_lint_futures']?.series  || [];
  let _xRange = null;
  if (_spotSer.length && _futSer.length) {
    const _firsts = [_spotSer[0].date, _futSer[0].date].sort().reverse();
    const _lasts  = [
      _spotSer[_spotSer.length - 1].date,
      _futSer[_futSer.length - 1].date,
    ].sort().reverse();
    _xRange = [_firsts[0], _lasts[0]];
  }
  _renderMultiLine('chart-cotton-spot', [
    { key: 'cotton_lint', color: C.orange, label: 'SunSirs China Spot (USD/t)' },
  ], data, _xRange);
  _renderMultiLine('chart-cotton-futures', [
    { key: 'cotton_lint_futures', color: C.blue, label: 'ICE Futures (USD/t)' },
  ], data, _xRange);
}

function _renderMultiLine(elId, mats, data, xRangeOverride) {
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
      // PI-1.7: align x-axis. Caller can pass xRangeOverride [start, end]
      // (used by _renderCottonPanel to keep both sub-charts on the same
      // window). Otherwise, fall back to common-start across visible series
      // (good for multi-trace charts like the nylon family).
      ...(function _multiLineRange() {
        if (Array.isArray(xRangeOverride) && xRangeOverride.length === 2) {
          return { xaxis: { range: xRangeOverride, autorange: false } };
        }
        const fd = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[0]);
        const ld = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[t.x.length - 1]);
        if (!fd.length) return {};
        const start = fd.sort().reverse()[0];
        const end   = ld.sort().reverse()[0];
        return { xaxis: { range: [start, end], autorange: false } };
      })(),
      // PI-1.6: pin legend top-right so it sits in the upper corner of the plot.
      legend: { x: 1, xanchor: 'right', y: 1, yanchor: 'top' },
    ...PRICE_CHART_LAYOUT,
    height: 320,
    yaxis: {
      ...PRICE_CHART_LAYOUT.yaxis,
      tickformat: _currency === 'usd' ? '$.2f' : ',d',
    },
    legend: { bgcolor: 'rgba(0,0,0,0)', font: { color: C.muted, size: 10 } },
    showlegend: true,
  }, PLOTLY_CONFIG);
  // PI-1.7c: resize after paint — flex container height isn't
  // final at newPlot time on initial load. Plotly's responsive
  // observer fires later, but only on subsequent resizes. Force
  // an explicit resize on the next frame so the chart fills the
  // container immediately.
  requestAnimationFrame(() => {
    try { Plotly.Plots.resize(elId); } catch (e) { /* element may have unmounted */ }
  });
}

function _renderPriceSummaryTable(data) {
  // PI-1.8b: tooltips applied
  // PI-1.8a: family grouping + sortable columns + flat-list-when-sorted hybrid.
  const fn = _renderPriceSummaryTable;
  if (!fn._sortState)  fn._sortState  = null;
  if (!fn._collapsed)  fn._collapsed  = new Set();
  // PI-2b: filter chips — null means All. Otherwise one of the type names.
  if (fn._typeFilter === undefined) fn._typeFilter = null;

  const FAMILY_LABEL = {
    polyester: 'POLYESTER',
    cotton:    'COTTON',
    nylon:     'NYLON',
    viscose:   'VISCOSE',
  };
  const FAMILY_ORDER = ['polyester', 'cotton', 'nylon', 'viscose'];

  const fmtPct = v => {
    if (v == null) return '<span class="muted">\u2014</span>';
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };
  const fmt30 = v => {
    if (v == null) {
      // PI-1.8a tweak: explicit "<30 days history" instead of dash so the
      // missing-data reason is visible without hovering.
      return '<span class="muted muted-tag" title="30D requires at least 30 days of data">&lt;30 days history</span>';
    }
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };
  const trendArrow = t => {
    if (!t) return '<span class="muted">\u2014</span>';
    if (t === 'up')   return '<span class="stat-up">\u2191</span>';
    if (t === 'down') return '<span class="stat-down">\u2193</span>';
    return '<span class="stat-neutral">\u2192</span>';
  };
  const INS = '<span class="muted">\u2014</span>';

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
      type: MATERIAL_TYPE[m.key] || null,
      typeOrder: MATERIAL_TYPE_ORDER[MATERIAL_TYPE[m.key]] ?? 99,
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
    const tooltip  = r.isTierE ? ' title="Collecting data \u2014 metrics disabled"' : '';

    const TIER_DESC = {
      A: '60+ days of history — high confidence',
      B: '30+ days of history — usable directional',
      C: '14+ days of history — directional, weaker',
      D: '7+ days of history — short series',
      E: '<7 days of history — collecting data',
    };
    const tierHtml = r.tier
      ? `<span class="tier-badge tier-${r.tier}" title="${TIER_DESC[r.tier] || ''}">${r.tier}</span>`
      : INS;
    const mom      = _momentumArrow(r.momentum);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;
    const lagHtml  = (r.lagMin && r.lagMax)
      ? `<span class="turkey-lag-badge" title="Turkey supplier pass-through estimate: ${r.lagMin} to ${r.lagMax} weeks">${r.lagMin}\u2013${r.lagMax} wk</span>`
      : INS;

    const matBadge = showFamBadge
      ? `<span class="fam-badge fam-badge-${r.fam}" title="${FAMILY_LABEL[r.fam] || r.fam}">${(FAMILY_LABEL[r.fam] || r.fam).slice(0, 3)}</span> `
      : '';

    const typeBadge = r.type
      ? `<span class="type-badge type-${r.type.toLowerCase()}" title="${MATERIAL_TYPE_TOOLTIP[r.type] || ''}">${r.type}</span>`
      : INS;

    return `<tr class="${famCls} ${tierECls} ${minCls}"${tooltip}>
      <td>${matBadge}${esc(r.label)}</td>
      <td>${typeBadge}</td>
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
    return s.dir === 'desc' ? ' <span class="sort-ind">\u25BC</span>' : ' <span class="sort-ind">\u25B2</span>';
  };
  const sortableTh = (col, label, extraCls = '', tooltip = '') => {
    const cls = `sortable ${extraCls}`.trim();
    const t   = tooltip ? ` title="${tooltip}"` : '';
    return `<th class="${cls}"${t} data-sort-col="${col}">${label}${sortIndicator(col)}</th>`;
  };

  const headerHtml = `
    <thead><tr>
      ${sortableTh('label', 'Material')}
      ${sortableTh('typeOrder', 'Type', '', 'Material role: Direct (bought) / Benchmark (tracked only) / Proxy (upstream driver) / Estimate (driver-based)')}
      ${sortableTh('price', `Price (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})`, 'num')}
      ${sortableTh('change_1d', '1D%', 'num')}
      ${sortableTh('change_7d', '7D%', 'num')}
      ${sortableTh('change_30d', '30D%', 'num')}
      <th class="num" title="Direction over the last window (up / flat / down)">Trend</th>
      <th class="num" title="Speed and acceleration of recent price movement">Momentum</th>
      ${sortableTh('tier', 'Quality', 'num', 'Data quality: A=60+ days, B=30+, C=14+, D=7+, E=<7 days of usable history')}
      ${sortableTh('lagMid', 'TR Lag', 'num', 'Estimated Turkey supplier pass-through lag (weeks)')}
    </tr></thead>
  `;

  // PI-2b: build the chip row counts BEFORE filtering, so chip counts
  // always reflect the full universe, not the filtered subset.
  const typeCounts = { Direct: 0, Benchmark: 0, Proxy: 0, Estimate: 0 };
  records.forEach(r => { if (r.type && typeCounts[r.type] !== undefined) typeCounts[r.type]++; });
  const totalCount = records.length;

  // Apply filter to the records used for body rendering.
  const visibleRecords = fn._typeFilter
    ? records.filter(r => r.type === fn._typeFilter)
    : records;

  let bodyHtml;
  if (fn._sortState) {
    const { col, dir } = fn._sortState;
    const sorted = visibleRecords.slice().sort((a, b) => {
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
    visibleRecords.forEach(r => {
      if (!groups[r.fam]) groups[r.fam] = [];
      groups[r.fam].push(r);
    });
    let rowsHtml = '';
    FAMILY_ORDER.forEach(fam => {
      const items = groups[fam];
      if (!items || !items.length) return;
      const collapsed = fn._collapsed.has(fam);
      const chevron = collapsed ? '\u25B6' : '\u25BC';
      rowsHtml += `<tr class="fam-header" data-fam="${fam}">
        <td colspan="10"><span class="fam-chevron">${chevron}</span> <span class="fam-name">${FAMILY_LABEL[fam] || fam}</span> <span class="fam-count">(${items.length})</span></td>
      </tr>`;
      if (!collapsed) {
        rowsHtml += items.map(r => rowHtml(r, { showFamBadge: false })).join('');
      }
    });
    // Defensive: any record whose family isn't in FAMILY_ORDER ends up here.
    const leftover = visibleRecords.filter(r => !FAMILY_ORDER.includes(r.fam));
    if (leftover.length) {
      const byFam = {};
      leftover.forEach(r => { (byFam[r.fam] ||= []).push(r); });
      Object.keys(byFam).forEach(fam => {
        const items = byFam[fam];
        const collapsed = fn._collapsed.has(fam);
        const chevron = collapsed ? '\u25B6' : '\u25BC';
        rowsHtml += `<tr class="fam-header" data-fam="${fam}">
          <td colspan="10"><span class="fam-chevron">${chevron}</span> <span class="fam-name">${(fam || 'OTHER').toUpperCase()}</span> <span class="fam-count">(${items.length})</span></td>
        </tr>`;
        if (!collapsed) {
          rowsHtml += items.map(r => rowHtml(r, { showFamBadge: false })).join('');
        }
      });
    }
    bodyHtml = `<tbody>${rowsHtml}</tbody>`;
  }

  // PI-2b: build chip bar
  const mkChip = (label, count, value) => {
    const isActive = (fn._typeFilter === value) || (value === null && fn._typeFilter === null);
    const cls = `type-chip ${isActive ? 'type-chip-active' : ''} ${value ? `type-chip-${value.toLowerCase()}` : 'type-chip-all'}`.trim();
    return `<button class="${cls}" data-type-filter="${value === null ? 'all' : value}">${label} <span class="type-chip-count">${count}</span></button>`;
  };
  const chipBar = `
    <div class="type-chip-bar">
      ${mkChip('All', totalCount, null)}
      ${mkChip('Direct', typeCounts.Direct, 'Direct')}
      ${mkChip('Benchmark', typeCounts.Benchmark, 'Benchmark')}
      ${mkChip('Proxy', typeCounts.Proxy, 'Proxy')}
      ${mkChip('Estimate', typeCounts.Estimate, 'Estimate')}
    </div>
  `;

  document.getElementById('price-summary-table').innerHTML = `
    ${chipBar}
    <table class="data-table summary-table">${headerHtml}${bodyHtml}</table>`;

  // Wire chip clicks
  document.querySelectorAll('#price-summary-table .type-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const v = btn.dataset.typeFilter;
      fn._typeFilter = (v === 'all') ? null : v;
      _renderPriceSummaryTable(data);
    });
  });

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
}

function initPriceSection() {
  document.querySelectorAll('#currency-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#currency-toggle .toggle-btn')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _currency = btn.dataset.currency;
      if (_priceData) _renderPriceDashboard(_priceData);
    });
  });

  document.querySelectorAll('#poly-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#poly-toggle .toggle-btn')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _polyMode = btn.dataset.mode;
      if (_priceData) _renderPolyesterFamily(_priceData, _polyMode);
    });
  });

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

/* ── Yarn Intelligence — Phase A 1.5 ─────────────────────────────────────────── */
async function loadYarnIntelligence() {
  const tbody    = document.getElementById('yarn-pressure-tbody');
  const summary  = document.getElementById('yarn-pressure-summary');
  const covStrip = document.getElementById('yarn-coverage-strip');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="9" class="loading">Yukleniyor...</td></tr>';

  try {
    const data  = await api('/api/yarn_pressure');
    const yarns = data.flat || [];
    const cov   = data.coverage_summary || {};

    /* ── Family summary cards ─────────────────────────────────────────────── */
    const families = {};
    yarns.forEach(y => {
      families[y.fiber_family] = families[y.fiber_family] || [];
      families[y.fiber_family].push(y);
    });

    summary.innerHTML = Object.entries(families).map(([fam, items]) => {
      const rising   = items.filter(y => ['rising', 'firming'].includes(y.pressure_signal)).length;
      const falling  = items.filter(y => ['falling', 'easing'].includes(y.pressure_signal)).length;
      const dominant = rising > falling ? 'rising' : falling > rising ? 'falling' : 'stable';
      const cls      = dominant === 'rising'  ? 'pressure-rising'  :
                       dominant === 'falling' ? 'pressure-falling' : 'pressure-stable';
      const icon     = dominant === 'rising'  ? '\u2191' :
                       dominant === 'falling' ? '\u2193' : '\u2192';
      return `<div class="yarn-family-card ${cls}">
        <div class="yarn-family-name">${esc(fam)}</div>
        <div class="yarn-family-signal">${icon} ${dominant}</div>
        <div class="yarn-family-count">${items.length} specs</div>
      </div>`;
    }).join('');

    /* ── Coverage strip (reframed as Phase 1 scope) ──────────────────────── */
    if (covStrip) {
      covStrip.innerHTML = `
        <div class="cov-strip-label">Phase 1 scope coverage <span style="font-weight:400;opacity:0.7">(${cov.total ?? yarns.length} synthetic specs)</span>:</div>
        <div class="cov-chip cov-chip-quote-validated" title="Has validated supplier quote within 90 days">
          <span class="cov-chip-dot"></span>
          <span class="cov-chip-text">Quote-validated</span>
          <span class="cov-chip-count">${cov.quote_validated ?? 0}</span>
        </div>
        <div class="cov-chip cov-chip-driver-priced" title="Priced via commodity driver (indicative)">
          <span class="cov-chip-dot"></span>
          <span class="cov-chip-text">Driver-priced</span>
          <span class="cov-chip-count">${cov.driver_priced ?? 0}</span>
        </div>
        <div class="cov-chip cov-chip-placeholder" title="Placeholder entry, not yet priced">
          <span class="cov-chip-dot"></span>
          <span class="cov-chip-text">Placeholder</span>
          <span class="cov-chip-count">${cov.placeholder ?? 0}</span>
        </div>
        <div class="cov-chip cov-chip-not-covered" title="Eligible but no driver / price data in this subset">
          <span class="cov-chip-dot"></span>
          <span class="cov-chip-text">Not covered</span>
          <span class="cov-chip-count">${cov.not_covered ?? 0}</span>
        </div>
        <div class="cov-strip-total">Cotton / viscose / blend = Phase 2</div>
      `;
    }

    /* ── Top insight strip (dynamic) ──────────────────────────────────────── */
    _renderYarnInsights(yarns);

    /* ── Pressure labels ──────────────────────────────────────────────────── */
    const PLABEL = {
      rising:   'Rising',
      firming:  'Firming',
      stable:   'Stable',
      easing:   'Easing',
      falling:  'Falling',
      watch:    'Watch',
    };

    const covLabel = {
      'quote-validated': 'Quote',
      'driver-priced':   'Driver',
      'placeholder':     'Placeholder',
      'not-covered':     'Not cov.',
    };

    const renderCoverageChip = (status) => {
      const label = covLabel[status] || status;
      return `<span class="cov-chip-small cov-chip-${status}">${label}</span>`;
    };

    const fmtPrice = (v) => v != null
      ? `$${Math.round(v).toLocaleString('en')}`
      : '\u2014';

    const fmtChange = (v) => v != null
      ? `<span class="${v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : ''}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`
      : '\u2014';

    const fmtMomentum = (v) => v != null
      ? `<span class="${v > 0.1 ? 'stat-up' : v < -0.1 ? 'stat-down' : ''}">` +
        (v > 0.3 ? '\u21911' : v > 0.1 ? '\u2191' :
         v < -0.3 ? '\u21932' : v < -0.1 ? '\u2193' : '\u2192') +
        '</span>'
      : '\u2014';

    const fmtLag = (a, b) => (a && b)
      ? `<span class="turkey-lag-badge">${a}\u2013${b} wk</span>`
      : '\u2014';

    const fmtTier = (t) => t
      ? `<span class="tier-badge tier-${t}">${t}</span>`
      : '\u2014';

    const fmtPressure = (signal) => {
      const label = PLABEL[signal] || signal;
      return `<span class="pressure-pill pressure-${signal}">${label}</span>`;
    };

    /* ── Group by driver ──────────────────────────────────────────────────── */
    const groups = {};
    yarns.forEach(y => {
      const key = y.primary_driver_slug || '__no_driver__';
      groups[key] = groups[key] || [];
      groups[key].push(y);
    });

    const rankDriver = (group) => {
      const sample = group[0];
      const c = sample.driver_change_7d;
      if (c == null) return 6;
      if (c > 5)  return 1;
      if (c > 2)  return 2;
      if (c < -5) return 5;
      if (c < -2) return 4;
      return 3;
    };

    const sortedGroupEntries = Object.entries(groups).sort((a, b) => {
      if (a[0] === '__no_driver__') return 1;
      if (b[0] === '__no_driver__') return -1;
      return rankDriver(a[1]) - rankDriver(b[1]);
    });

    /* ── Render grouped rows (8 columns) ──────────────────────────────────── */
    let html = '';

    sortedGroupEntries.forEach((entry, groupIdx) => {
      const [driverSlug, items] = entry;
      const hasDriver = driverSlug !== '__no_driver__';
      const sample    = items[0];
      const groupId   = `yarn-group-${groupIdx}`;

      // DRIVER (parent) row — signal columns
      if (hasDriver) {
        html += `<tr class="yarn-driver-row" data-group="${groupId}">
          <td class="yarn-expand-cell">
            <span class="yarn-expand-caret">\u25B6</span>
          </td>
          <td>
            <span class="driver-badge">${esc(driverSlug)}</span>
            <span class="yarn-spec-count">${items.length} spec${items.length === 1 ? '' : 's'}</span>
          </td>
          <td class="num">${fmtPrice(sample.driver_price_usd)}</td>
          <td class="num">${fmtChange(sample.driver_change_7d)}</td>
          <td class="num">${fmtMomentum(sample.driver_momentum)}</td>
          <td class="num">${fmtPressure(sample.pressure_signal)}</td>
          <td class="num">${fmtLag(sample.lag_min_weeks, sample.lag_max_weeks)}</td>
          <td class="num">${fmtTier(sample.driver_data_quality)}</td>
          <td class="num"></td>
        </tr>`;
      } else {
        html += `<tr class="yarn-driver-row yarn-driver-row-nodriver" data-group="${groupId}">
          <td class="yarn-expand-cell">
            <span class="yarn-expand-caret">\u25B6</span>
          </td>
          <td colspan="8" class="muted">
            <em>No driver assigned</em> \u00B7 ${items.length} spec${items.length === 1 ? '' : 's'}
          </td>
        </tr>`;
      }

      // SPEC (child) rows — metadata only
      items.forEach(y => {
        const subspec = y.subspec_sensitive
          ? ' <span title="Sub-spec variants present \u2014 price may vary" style="color:#f0883e;font-size:10px">\u26a0</span>'
          : '';

        const chips = [];
        // Phase C+1: branch on count_type
        const _ct = y.yarn_count_type;
        if (_ct === 'Ne') {
          // Spun yarn branch
          if (y.yarn_ne_count != null) chips.push(`<span class="spec-meta-chip chip-ne">Ne ${Math.round(y.yarn_ne_count)}</span>`);
          if (y.yarn_ply != null && y.yarn_ply > 1) chips.push(`<span class="spec-meta-chip chip-ply">${y.yarn_ply}-ply</span>`);
          const _spinLabel = { 'staple_ring': 'Ring', 'staple_vortex': 'Vortex', 'staple_oe': 'OE' }[y.yarn_subfamily];
          if (_spinLabel) chips.push(`<span class="spec-meta-chip chip-spinning">${_spinLabel}</span>`);
        } else {
          // Filament branch (count_type='denier' or null)
          if (y.denier != null)         chips.push(`<span class="spec-meta-chip chip-denier">${y.denier}D</span>`);
          if (y.filament_count != null) chips.push(`<span class="spec-meta-chip chip-filament">${y.filament_count}F</span>`);
          if (y.luster)                 chips.push(`<span class="spec-meta-chip chip-luster">${esc(y.luster)}</span>`);
        }
        // Common chips for both branches
        if (y.yarn_color_state === 'BLACK')  chips.push(`<span class="spec-meta-chip chip-color-black">BLACK</span>`);
        // specialty_flags can be TEXT (string) or TEXT[] (array)
        const _sf = y.yarn_specialty_flags;
        if (Array.isArray(_sf) && _sf.length) {
          _sf.forEach(f => chips.push(`<span class="spec-meta-chip chip-specialty">${esc(String(f).toUpperCase())}</span>`));
        } else if (typeof _sf === 'string' && _sf) {
          chips.push(`<span class="spec-meta-chip chip-specialty">${esc(_sf.toUpperCase())}</span>`);
        }
        if (y.recycle_flag)           chips.push(`<span class="spec-meta-chip chip-recycle">GRS</span>`);
        if (y.alias_count)            chips.push(`<span class="spec-meta-chip chip-alias" title="${y.alias_count} label alias(es) mapped to this spec">${y.alias_count} alias${y.alias_count === 1 ? '' : 'es'}</span>`);
        if (y.is_placeholder)         chips.push(`<span class="spec-meta-chip chip-placeholder">placeholder</span>`);

        const coverageCell = renderCoverageChip(y.coverage_status || 'driver-priced');

        // Phase C+1: yarn-level 7d/30d pressure display
        const fmtTrend = (v) => {
          if (v == null) return '';
          const cls = v > 0.5 ? 'pct-up' : (v < -0.5 ? 'pct-down' : 'pct-flat');
          const sign = v > 0 ? '+' : '';
          return `<span class="${cls}">${sign}${v.toFixed(2)}%</span>`;
        };
        const trendRow = (y.yarn_pressure_7d != null || y.yarn_pressure_30d != null)
          ? `<div class="yarn-trend-row">${y.yarn_pressure_7d != null ? `${fmtTrend(y.yarn_pressure_7d)}<sub>7d</sub>` : ''}${y.yarn_pressure_30d != null ? `${fmtTrend(y.yarn_pressure_30d)}<sub>30d</sub>` : ''}</div>`
          : '';
        const yarnPriceCell = y.yarn_estimated_index_usd_per_kg != null
          ? `<div class="yarn-price-cell">
               <span class="yarn-price-value">$${y.yarn_estimated_index_usd_per_kg.toFixed(2)}</span>
               ${trendRow}
               <div class="yarn-price-badges">
                 <span class="pricing-method-badge pm-${(y.yarn_pricing_method || 'unknown').replace(/_/g, '-')}" title="${y.yarn_pricing_method || ''}">${y.yarn_pricing_method === 'tier_4_benchmark_proxy' ? 'Benchmark' : y.yarn_pricing_method === 'tier_4_proxy_fallback' ? 'Proxy' : '?'}</span>
                 <span class="confidence-badge conf-${y.yarn_confidence || 'unknown'}" title="Confidence: ${y.yarn_confidence || 'unknown'}">${y.yarn_confidence || '?'}</span>
               </div>
             </div>`
          : '<span class="muted">\u2014</span>';

        html += `<tr class="yarn-spec-row" data-group="${groupId}" style="display:none">
          <td></td>
          <td class="spec-primary">${esc(y.yarn_code)}${subspec}</td>
          <td colspan="5" class="spec-meta-cell">${chips.join(' ')}</td>
          <td class="num">${coverageCell}</td>
          <td class="num">${yarnPriceCell}</td>
        </tr>`;
      });
    });

    tbody.innerHTML = html;

    /* ── Expand/collapse handlers ─────────────────────────────────────────── */
    tbody.querySelectorAll('.yarn-driver-row').forEach(row => {
      row.addEventListener('click', () => {
        const groupId = row.dataset.group;
        const caret   = row.querySelector('.yarn-expand-caret');
        const isOpen  = row.classList.toggle('yarn-driver-open');
        if (caret) caret.textContent = isOpen ? '\u25BC' : '\u25B6';
        tbody.querySelectorAll(`.yarn-spec-row[data-group="${groupId}"]`)
          .forEach(r => { r.style.display = isOpen ? '' : 'none'; });
      });
    });

    /* ── Subspec warning footer ───────────────────────────────────────────── */
    const noteEl = document.getElementById('yarn-subspec-note');
    if (noteEl && data.subspec_warning) {
      noteEl.textContent = '\u26a0 ' + data.subspec_warning;
    }

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="error"h>Yuklenemedi: ${e.message}</td></tr>`;
  }
}

/* ── Dynamic insight strip ─────────────────────────────────────────────────── */
function _renderYarnInsights(yarns) {
  const el = document.getElementById('yarn-insights-strip');
  if (!el) return;

  const byDriver = {};
  yarns.forEach(y => {
    const k = y.primary_driver_slug || '__no_driver__';
    byDriver[k] = byDriver[k] || [];
    byDriver[k].push(y);
  });

  const driverStats = Object.entries(byDriver).map(([slug, items]) => {
    const s = items[0];
    return {
      slug,
      label: slug === '__no_driver__' ? 'Unassigned' : slug,
      count: items.length,
      change_7d: s.driver_change_7d,
      pressure: s.pressure_signal,
      family: s.fiber_family,
      hasPlaceholder: items.some(y => y.coverage_status === 'placeholder'),
      placeholderCount: items.filter(y => y.coverage_status === 'placeholder').length,
    };
  }).filter(d => d.slug !== '__no_driver__');

  driverStats.sort((a, b) => {
    if (a.change_7d == null) return 1;
    if (b.change_7d == null) return -1;
    return Math.abs(b.change_7d) - Math.abs(a.change_7d);
  });

  const insights = [];

  const top = driverStats[0];
  if (top && top.change_7d != null) {
    const verb = _insightVerb(top.pressure);
    insights.push({
      bullet: top.pressure,
      text: `<span class="yarn-insight-emph">${esc(top.label)}</span> ${verb}, ${top.count} spec${top.count === 1 ? '' : 's'} affected <span class="yarn-insight-muted">(${top.change_7d > 0 ? '+' : ''}${top.change_7d.toFixed(1)}% 7d)</span>`,
    });
  }

  if (driverStats.length >= 2) {
    const second = driverStats[1];
    if (top && second.family === top.family && second.change_7d != null && top.change_7d != null
        && Math.abs(second.change_7d - top.change_7d) > 0.8) {
      const comparison = second.change_7d < top.change_7d ? 'sharper move than' : 'milder move than';
      insights.push({
        bullet: second.pressure,
        text: `<span class="yarn-insight-emph">${esc(second.label)}</span> showing ${comparison} ${esc(top.label)} <span class="yarn-insight-muted">(${second.change_7d > 0 ? '+' : ''}${second.change_7d.toFixed(1)}% 7d, ${second.count} spec${second.count === 1 ? '' : 's'})</span>`,
      });
    } else if (second.change_7d != null) {
      const verb = _insightVerb(second.pressure);
      insights.push({
        bullet: second.pressure,
        text: `<span class="yarn-insight-emph">${esc(second.label)}</span> ${verb} <span class="yarn-insight-muted">(${second.change_7d > 0 ? '+' : ''}${second.change_7d.toFixed(1)}% 7d, ${second.count} spec${second.count === 1 ? '' : 's'})</span>`,
      });
    }
  }

  const placeholdersByFamily = {};
  yarns.forEach(y => {
    if (y.coverage_status === 'placeholder') {
      placeholdersByFamily[y.fiber_family] = (placeholdersByFamily[y.fiber_family] || 0) + 1;
    }
  });
  const phEntries = Object.entries(placeholdersByFamily);
  if (phEntries.length) {
    const phText = phEntries.map(([fam, n]) => `${n} in ${esc(fam)}`).join(', ');
    insights.push({
      bullet: 'watch',
      text: `<span class="yarn-insight-emph">Unresolved placeholders</span>: ${phText} <span class="yarn-insight-muted">(needs driver assignment or pricing)</span>`,
    });
  }

  const subspecCount = yarns.filter(y => y.subspec_sensitive).length;
  if (subspecCount > 0 && insights.length < 4) {
    insights.push({
      bullet: 'watch',
      text: `<span class="yarn-insight-emph">${subspecCount} spec${subspecCount === 1 ? '' : 's'}</span> flagged subspec-sensitive <span class="yarn-insight-muted">\u2014 driver price is an approximation</span>`,
    });
  }

  if (!insights.length) {
    el.innerHTML = `
      <div class="yarn-insights-strip-title">Today's read</div>
      <div class="yarn-insight-item yarn-insight-muted">No strong signals in current scope</div>
    `;
    return;
  }

  el.innerHTML = `
    <div class="yarn-insights-strip-title">Today's read</div>
    ${insights.map(i =>
      `<div class="yarn-insight-item"><span class="yarn-insight-bullet bullet-${i.bullet}"></span>${i.text}</div>`
    ).join('')}
  `;
}

function _insightVerb(pressure) {
  const map = {
    rising:  'rising strongly',
    firming: 'firming',
    stable:  'stable',
    easing:  'easing',
    falling: 'falling',
    watch:   'insufficient data',
  };
  return map[pressure] || pressure;
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
async function _loadInternal_legacy() {
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
    _internalData    = null;
    _priceData       = null;
    _feedRawData     = null;
    _feedMinImpact   = 50;
    _feedViewAll     = false;
    _feedThemeFilter = null;
    Object.keys(_exportData).forEach(k => delete _exportData[k]);
    _loaded.clear();
    loadStats();
    loadSignalsPanels();
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
  initSignalsSection();
  initExportSelector();
  initPriceSection();
  initRefresh();
  loadStats();
  loadSignalsPanels();
});


/* ── Operations Intelligence (M2) ───────────────────────────────────────────
 *
 * Replaces the old "Internal Data" loaders (Lescon / Yarn Costs / Orders)
 * with the M2 Operations Intelligence panel system:
 *   - Overview     (KPI grid + contra anomaly alert)
 *   - Procurement  (trend chart + top suppliers)
 *   - Cost         (trend chart)
 *   - Revenue      (gross/net trend + top customers)
 *
 * Existing renderLescon / renderYarn / renderOrders functions are retained
 * elsewhere in this file but are no longer invoked.
 *
 * Backend endpoints used:
 *   GET /api/internal/kpi-latest-month
 *   GET /api/internal/procurement-trend?months=24
 *   GET /api/internal/cost-structure-trend?months=24
 *   GET /api/internal/revenue-trend?months=24
 *   GET /api/internal/top-suppliers?limit=10
 *   GET /api/internal/top-customers?limit=10
 *   GET /api/internal/contra-anomaly
 */

let _opsData = null;

async function loadInternal() {
  if (_opsData) return;
  try {
    const [kpi, proc, cost, rev, suppliers, customers, contra] = await Promise.all([
      api('/api/internal/kpi-latest-month'),
      api('/api/internal/procurement-trend?months=24'),
      api('/api/internal/cost-structure-trend?months=24'),
      api('/api/internal/revenue-trend?months=24'),
      api('/api/internal/top-suppliers?limit=10'),
      api('/api/internal/top-customers?limit=10'),
      api('/api/internal/contra-anomaly'),
    ]);
    _opsData = { kpi, proc, cost, rev, suppliers, customers, contra };

    renderOpsPeriodHeader(kpi);
    renderOpsKpis(kpi);
    renderOpsContraAlert(contra);
    if (typeof loadOverviewSignals === 'function') loadOverviewSignals(); // loadOverviewSignals call inside loadInternal
    renderOpsProcurementChart(proc);
    renderOpsProcurementMixChart(proc);
    renderOpsCostChart(cost);
    if (typeof renderOpsCostMixChart === "function") renderOpsCostMixChart(cost);
    renderOpsRevenueChart(rev);
    renderOpsSuppliersTable(suppliers);
    renderOpsCustomersTable(customers);
  } catch (err) {
    console.error('[ops] load failed', err);
  }
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function fmtTL(v) {
  if (v == null || isNaN(v)) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e9)  return `₺${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `₺${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3)  return `₺${(n / 1e3).toFixed(0)}K`;
  return `₺${Math.round(n).toLocaleString('en')}`;
}

function fmtUSD(v) {
  if (v == null || isNaN(v) || Number(v) === 0) return null;
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${Math.round(n).toLocaleString('en')}`;
}

function fmtEUR(v) {
  if (v == null || isNaN(v) || Number(v) === 0) return null;
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `€${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `€${(n / 1e3).toFixed(0)}K`;
  return `€${Math.round(n).toLocaleString('en')}`;
}

function fmtYoy(pct) {
  if (pct == null || isNaN(pct)) return null;
  const n = Number(pct);
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(1)}%`;
}

function yoyClass(pct, invertGood = false) {
  // For procurement/cost: rising is bad → red. For revenue: rising is good → green.
  if (pct == null || isNaN(pct)) return 'stat-neutral';
  const n = Number(pct);
  if (Math.abs(n) < 1) return 'stat-neutral';
  const isUp = n > 0;
  const isGood = invertGood ? !isUp : isUp;
  return isGood ? 'stat-good' : 'stat-bad';
}

/* ── Period header ────────────────────────────────────────────────────────── */

function renderOpsPeriodHeader(kpi) {
  const ref = kpi.reference || {};
  const el = document.getElementById('ops-period-header');
  if (!el) return;
  el.classList.add('ops-status-strip');
  el.innerHTML = `
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Latest complete month</span>
      <span class="ops-status-cell-value">${ref.purchase_latest_month || '—'}</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Window</span>
      <span class="ops-status-cell-value">last 24 months</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Currency</span>
      <span class="ops-status-cell-value">TL primary · USD/EUR secondary</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Classification</span>
      <span class="ops-status-cell-value">v3 · current</span>
    </span>
    <span class="ops-status-cell ops-status-meta">YoY = vs same month prior year</span>
  `;
}

/* ── KPI cards ─────────────────────────────────────────────────────────────── */


/* ── Mini sparklines for Overview KPI wall (M2.5.2) ───────────────────── */
/* Each KPI card resolves its 12-month series from the _opsData payload    */
/* that loadInternal already fetched. No new endpoint.                     */

function _kpiSparklineSeries(metricKey, panel) {
  // Returns array of numbers (length up to 12) or [] if no data available.
  const opsData = (typeof _opsData !== 'undefined') ? _opsData : null;
  if (!opsData) return [];

  // ── Procurement KPIs ───────────────────────────────────────────────────
  if (panel === 'procurement') {
    const rows = opsData?.proc?.data || [];
    if (!rows.length) return [];

    // Group rows by month, summing per requested metric_key
    const byMonth = {};
    rows.forEach(r => {
      const m = r.month;
      if (!byMonth[m]) byMonth[m] = 0;
      const b = r.business_bucket;
      let include = false;
      if (metricKey === 'total_procurement') {
        include = b && b.indexOf('raw_material_') === 0;
      } else if (metricKey === 'yarn') {
        include = (b === 'raw_material_yarn');
      } else if (metricKey === 'chemical_dye') {
        include = (b === 'raw_material_chemical' || b === 'raw_material_dye');
      } else if (metricKey === 'greige') {
        include = (b === 'raw_material_greige_fabric');
      }
      if (include) byMonth[m] += (r.amount_tl || 0);
    });
    const months = Object.keys(byMonth).sort();
    const last12 = months.slice(-12);
    return last12.map(m => byMonth[m]);
  }

  // ── Cost Structure KPIs ────────────────────────────────────────────────
  if (panel === 'cost_structure') {
    const rows = opsData?.cost?.data || [];
    if (!rows.length) return [];
    const targetBucket =
      metricKey === 'utilities'        ? 'utilities' :
      metricKey === 'maintenance'      ? 'maintenance_factory' :
      metricKey === 'fason'            ? 'outsourced_processing' :
      metricKey === 'factory_overhead' ? 'factory_overhead' : null;
    if (!targetBucket) return [];

    const byMonth = {};
    rows.forEach(r => {
      if (r.business_bucket === targetBucket) {
        byMonth[r.month] = (byMonth[r.month] || 0) + (r.amount_tl || 0);
      }
    });
    const months = Object.keys(byMonth).sort();
    return months.slice(-12).map(m => byMonth[m]);
  }

  // ── Revenue KPIs ───────────────────────────────────────────────────────
  if (panel === 'revenue_reality') {
    const rows = opsData?.rev?.data || [];
    if (!rows.length) return [];
    const col =
      metricKey === 'core_sales'    ? 'core_sales_tl' :
      metricKey === 'fason_revenue' ? 'fason_revenue_tl' :
      metricKey === 'net_revenue'   ? 'net_revenue_tl' : null;
    if (!col) return [];

    const sorted = rows.slice().sort((a, b) => (a.month < b.month ? -1 : 1));
    return sorted.slice(-12).map(r => r[col] || 0);
  }

  return [];
}

function _renderSparklineSvg(series, opts = {}) {
  if (!series || series.length < 2) return '';
  const w = opts.width  || 110;
  const h = opts.height || 22;
  const pad = 1;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = (max - min) || 1;
  const stepX = (w - 2 * pad) / (series.length - 1);

  const points = series.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  // Trend color: compare last vs first half average
  const half = Math.floor(series.length / 2);
  const firstAvg = series.slice(0, half).reduce((s, v) => s + v, 0) / Math.max(half, 1);
  const lastAvg  = series.slice(-half).reduce((s, v) => s + v, 0) / Math.max(half, 1);
  const trend = lastAvg > firstAvg * 1.05 ? 'up'
              : lastAvg < firstAvg * 0.95 ? 'down'
              : 'flat';

  // Dot at the last point (current value emphasis)
  const lastX = pad + (series.length - 1) * stepX;
  const lastY = h - pad - ((series[series.length - 1] - min) / range) * (h - 2 * pad);

  return `
    <svg class="kpi-sparkline kpi-sparkline-${trend}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <polyline fill="none" stroke="currentColor" stroke-width="1.2" points="${points}" />
      <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="1.8" fill="currentColor" />
    </svg>
  `;
}

function buildKpiCard(metric, invertGoodForUp = false) {
  const tlMain = fmtTL(metric.amount_tl);
  const yoy    = fmtYoy(metric.yoy_pct_tl);
  const yoyCls = yoyClass(metric.yoy_pct_tl, invertGoodForUp);

  const usd = fmtUSD(metric.amount_usd);
  const eur = fmtEUR(metric.amount_eur);
  const usdYoy = fmtYoy(metric.yoy_pct_usd);

  const fxLine = [];
  if (usd) {
    fxLine.push(usdYoy ? `${usd} (${usdYoy})` : usd);
  }
  if (eur) fxLine.push(eur);
  const fxText = fxLine.length ? fxLine.join(' · ') : '';

  // Add a small context hint when the YoY swing is large (≥ ±60%) and the
  // absolute amount is small relative to a typical month — this keeps weakly-
  // signal items like a single Maintenance month from looking like alarms.
  let contextHint = '';
  if (metric.yoy_pct_tl != null && Math.abs(metric.yoy_pct_tl) >= 60) {
    contextHint = `<div class="stat-context-hint">Volatile line item — single-month YoY may overstate the underlying trend.</div>`;
  }

  // Sparkline (M2.5.2) — uses _opsData already fetched by loadInternal
  const _sparkSeries = (typeof _kpiSparklineSeries === 'function')
    ? _kpiSparklineSeries(metric.metric_key, metric.panel) : [];
  const _sparkSvg = (typeof _renderSparklineSvg === 'function' && _sparkSeries.length >= 2)
    ? _renderSparklineSvg(_sparkSeries) : '';
  const _sparkBlock = _sparkSvg
    ? `<div class="kpi-sparkline-wrap" title="last 12 months">${_sparkSvg}</div>`
    : '';

  return `
    <div class="stat-card">
      <div class="stat-label">${metric.metric_label}</div>
      <div class="stat-value">${tlMain}</div>
      <div class="stat-sub ${yoyCls}">${yoy ? `YoY ${yoy}` : '—'}</div>
      ${fxText ? `<div class="stat-fx">${fxText}</div>` : ''}
      ${_sparkBlock}
      ${contextHint}
    </div>
  `;
}

function renderOpsKpis(kpi) {
  const items = kpi.kpis || [];

  const proc = items.filter(k => k.panel === 'procurement');
  const cost = items.filter(k => k.panel === 'cost_structure');
  const rev  = items.filter(k => k.panel === 'revenue_reality')
                   .filter(k => k.metric_key !== 'contra_revenue'); // contra → alert card

  const fillRow = (id, list, invertGoodForUp) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = list.map(m => buildKpiCard(m, invertGoodForUp)).join('');
  };

  // For procurement & cost: increase = bad (red). For revenue: increase = good.
  fillRow('ops-kpi-procurement', proc, true);
  fillRow('ops-kpi-cost',        cost, true);
  fillRow('ops-kpi-revenue',     rev,  false);
}

/* ── Contra anomaly alert card ─────────────────────────────────────────────── */

function buildContraNarrative(a) {
  if (!a || a.total_contra_tl == null) return 'No contra data available for this period.';
  const sev = a.severity || 'normal';
  const top = a.top_counterparty_name;
  const topPct = a.top_counterparty_pct;
  const ratio = a.ratio_to_median;
  const sourceLabel = (a.top_counterparty_source || '').toLowerCase() === 'satiş'
    ? 'customer return' : 'supplier-side adjustment';
  const ratioText = (ratio != null && !isNaN(ratio))
    ? `${Number(ratio).toFixed(1)}× the 24-month median`
    : 'elevated';
  if (sev === 'high' || sev === 'elevated') {
    if (top && topPct != null && topPct >= 30) {
      return `Driven primarily by a single ${sourceLabel}: <strong>${top}</strong> accounts for ${Number(topPct).toFixed(0)}% of total contra. Overall contra is ${ratioText}.`;
    }
    return `Contra is ${ratioText}. Top contributor: <strong>${top || '—'}</strong> (${topPct != null ? Number(topPct).toFixed(0) : '—'}% of total).`;
  }
  return `Contra is within normal range (${ratioText}).`;
}

function renderOpsContraAlert(payload) {
  const a = payload?.anomaly || {};
  const el = document.getElementById('ops-contra-alert');
  if (!el) return;

  const sev = a.severity || 'normal';
  const sevLabel = {
    high:     'HIGH ANOMALY',
    elevated: 'ELEVATED',
    normal:   'WITHIN NORMAL RANGE',
  }[sev] || 'NORMAL';

  const ratio = a.ratio_to_median != null ? `${Number(a.ratio_to_median).toFixed(1)}×` : '—';
  const pct   = a.contra_pct_of_gross != null ? `${Number(a.contra_pct_of_gross).toFixed(1)}%` : '—';
  const med   = a.median_24m_pct != null ? `${Number(a.median_24m_pct).toFixed(1)}%` : '—';

  const topName  = a.top_counterparty_name || '—';
  const topShare = a.top_counterparty_pct != null ? `${Number(a.top_counterparty_pct).toFixed(0)}%` : '—';
  const topAmt   = fmtTL(a.top_counterparty_tl);

  const total    = fmtTL(a.total_contra_tl);
  const returns  = fmtTL(a.returns_tl);
  const discnts  = fmtTL(a.discounts_tl);

  el.innerHTML = `
    <div class="ops-alert ops-alert-${sev}">
      <div class="ops-alert-header">
        <span class="ops-alert-title">Contra Revenue — ${a.month_label || ''}</span>
        <span class="ops-alert-badge ops-alert-badge-${sev}">${sevLabel}</span>
      </div>
      <div class="ops-alert-why">${buildContraNarrative(a)}</div>
      <div class="ops-alert-grid">
        <div class="ops-alert-cell">
          <div class="ops-alert-cell-label">Total contra</div>
          <div class="ops-alert-cell-value">${total}</div>
        </div>
        <div class="ops-alert-cell">
          <div class="ops-alert-cell-label">Contra % of gross</div>
          <div class="ops-alert-cell-value">${pct}</div>
          <div class="ops-alert-cell-sub">vs ${med} 24-mo median (${ratio} median)</div>
        </div>
        <div class="ops-alert-cell">
          <div class="ops-alert-cell-label">Returns / Discounts</div>
          <div class="ops-alert-cell-value">${returns} / ${discnts}</div>
        </div>
        <div class="ops-alert-cell">
          <div class="ops-alert-cell-label">Top contributor</div>
          <div class="ops-alert-cell-value ops-alert-cell-name">${topName}</div>
          <div class="ops-alert-cell-sub">${topAmt} · ${topShare} of total</div>
        </div>
      </div>
    </div>
  `;
}

/* ── Procurement chart ─────────────────────────────────────────────────────── */

function renderOpsProcurementChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = payload.buckets || [
    'raw_material_yarn', 'raw_material_chemical',
    'raw_material_dye', 'raw_material_greige_fabric',
  ];
  const colorMap = {
    raw_material_yarn:           C.blue,
    raw_material_chemical:       C.purple,
    raw_material_dye:            C.orange,
    raw_material_greige_fabric:  C.green,
  };
  const labelMap = {
    raw_material_yarn:           'Yarn',
    raw_material_chemical:       'Chemical',
    raw_material_dye:            'Dye',
    raw_material_greige_fabric:  'Greige fabric',
  };

  const traces = buckets.map(bucket => {
    const byMonth = Object.fromEntries(
      data.filter(d => d.business_bucket === bucket)
          .map(d => [d.month, d.amount_tl || 0])
    );
    return {
      x: months,
      y: months.map(m => byMonth[m] || 0),
      name: labelMap[bucket] || bucket,
      type: 'bar',
      marker: { color: colorMap[bucket] || C.muted, opacity: 0.85 },
      hovertemplate: `${labelMap[bucket] || bucket}: ₺%{y:,.0f}<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-procurement', traces, {
    ...PLOTLY_BASE,
    height: 360,
    barmode: 'stack',
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '₺', tickformat: '.2s' },
  }, PLOTLY_CONFIG);
}

/* -- Procurement mix % chart (M2.2.3) ----------------------------------- */
function renderOpsProcurementMixChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = payload.buckets || [
    'raw_material_yarn', 'raw_material_chemical',
    'raw_material_dye', 'raw_material_greige_fabric',
  ];
  const colorMap = {
    raw_material_yarn:           C.blue,
    raw_material_chemical:       C.purple,
    raw_material_dye:            C.orange,
    raw_material_greige_fabric:  C.green,
  };
  const labelMap = {
    raw_material_yarn:           'Yarn',
    raw_material_chemical:       'Chemical',
    raw_material_dye:            'Dye',
    raw_material_greige_fabric:  'Greige fabric',
  };

  const monthTotals = {};
  months.forEach(m => { monthTotals[m] = 0; });
  data.forEach(d => {
    if (buckets.includes(d.business_bucket)) {
      monthTotals[d.month] = (monthTotals[d.month] || 0) + (d.amount_tl || 0);
    }
  });

  const traces = buckets.map(bucket => {
    const byMonth = Object.fromEntries(
      data.filter(d => d.business_bucket === bucket)
          .map(d => [d.month, d.amount_tl || 0])
    );
    return {
      x: months,
      y: months.map(m => {
        const total = monthTotals[m] || 0;
        if (total === 0) return 0;
        return ((byMonth[m] || 0) / total) * 100;
      }),
      name: labelMap[bucket] || bucket,
      type: 'bar',
      marker: { color: colorMap[bucket] || C.muted, opacity: 0.85 },
      hovertemplate: `${labelMap[bucket] || bucket}: %{y:.1f}%<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-procurement-mix', traces, {
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

/* ── Procurement concentration trend chart (M2.2.4) ────────────────────── */
async function loadProcurementConcentrationChart() {
  try {
    const data = await api('/api/internal/procurement-concentration-trend');
    if (!data || !data.data || !data.data.length) return;
    renderOpsProcurementConcentrationChart(data);
  } catch (e) {
    console.error('procurement-concentration fetch failed', e);
  }
}

function renderOpsProcurementConcentrationChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = data.map(d => d.month);
  const top1   = data.map(d => d.top_1_share_pct  ?? null);
  const top3   = data.map(d => d.top_3_share_pct  ?? null);
  const top10  = data.map(d => d.top_10_share_pct ?? null);
  const threshold = payload.threshold ?? 33;

  const traces = [
    {
      x: months, y: top10,
      name: 'Top 10 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.green, width: 2 },
      marker: { color: C.green, size: 5 },
      hovertemplate: 'Top 10: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top3,
      name: 'Top 3 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.orange, width: 2.5 },
      marker: { color: C.orange, size: 6 },
      hovertemplate: 'Top 3: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top1,
      name: 'Top 1 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.blue, width: 2 },
      marker: { color: C.blue, size: 5 },
      hovertemplate: 'Top 1: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: months.map(_ => threshold),
      name: `Watch zone (${threshold}%)`,
      type: 'scatter', mode: 'lines',
      line: { color: C.red || '#e03131', width: 1.2, dash: 'dash' },
      hovertemplate: `Watch: ${threshold}%<extra></extra>`,
    },
  ];

  Plotly.newPlot('chart-ops-procurement-concentration', traces, {
    ...PLOTLY_BASE,
    height: 360,
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: {
      ...PLOTLY_BASE.yaxis,
      ticksuffix: '%',
      range: [0, 100],
      tickvals: [0, 25, 50, 75, 100],
    },
    annotations: [
      {
        xref: 'paper', yref: 'y',
        x: 1, xanchor: 'right',
        y: threshold, yanchor: 'bottom',
        text: `Top 3 watch zone (${threshold}%)`,
        showarrow: false,
        font: { color: C.red || '#e03131', size: 10 },
      },
    ],
  }, PLOTLY_CONFIG);
}

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




/* ── Cost structure chart ──────────────────────────────────────────────────── */

function renderOpsCostChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = payload.buckets || [
    'utilities', 'maintenance_factory', 'packaging',
    'factory_overhead', 'outsourced_processing', 'logistics_distribution',
  ];
  const colorMap = {
    utilities:              C.orange,
    maintenance_factory:    C.purple,
    packaging:              C.green,
    factory_overhead:       C.blue,
    outsourced_processing:  C.red,
    logistics_distribution: C.muted,
  };
  const labelMap = {
    utilities:              'Utilities',
    maintenance_factory:    'Maintenance',
    packaging:              'Packaging',
    factory_overhead:       'Factory overhead',
    outsourced_processing:  'FASON',
    logistics_distribution: 'Logistics (provisional)',
  };

  const traces = buckets.map(bucket => {
    const byMonth = Object.fromEntries(
      data.filter(d => d.business_bucket === bucket)
          .map(d => [d.month, d.amount_tl || 0])
    );
    return {
      x: months,
      y: months.map(m => byMonth[m] || 0),
      name: labelMap[bucket] || bucket,
      type: 'scatter',
      mode: 'lines',
      stackgroup: 'one',
      line: { width: 0 },
      fillcolor: hexAlpha(colorMap[bucket] || C.muted, 0.65),
      hovertemplate: `${labelMap[bucket] || bucket}: ₺%{y:,.0f}<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-cost', traces, {
    ...PLOTLY_BASE,
    height: 360,
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '₺', tickformat: '.2s' },
  }, PLOTLY_CONFIG);
}

/* ── Revenue chart (gross vs net) ──────────────────────────────────────────── */

function renderOpsRevenueChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = data.map(d => d.month);

  const traces = [
    {
      x: months,
      y: data.map(d => d.gross_revenue_tl || 0),
      name: 'Gross revenue',
      type: 'scatter',
      mode: 'lines',
      line: { color: C.blue, width: 2.5 },
      hovertemplate: 'Gross: ₺%{y:,.0f}<extra></extra>',
    },
    {
      x: months,
      y: data.map(d => d.net_revenue_tl || 0),
      name: 'Net revenue (after returns/discounts)',
      type: 'scatter',
      mode: 'lines',
      line: { color: C.green, width: 2.5 },
      fill: 'tozeroy',
      fillcolor: hexAlpha(C.green, 0.12),
      hovertemplate: 'Net: ₺%{y:,.0f}<extra></extra>',
    },
    {
      x: months,
      y: data.map(d => d.fason_revenue_tl || 0),
      name: 'Secondary service revenue',
      type: 'scatter',
      mode: 'lines',
      line: { color: C.muted, width: 1.5, dash: 'dot' },
      hovertemplate: 'Secondary: ₺%{y:,.0f}<extra></extra>',
    },
  ];

  Plotly.newPlot('chart-ops-revenue', traces, {
    ...PLOTLY_BASE,
    height: 360,
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: { ...PLOTLY_BASE.yaxis, tickprefix: '₺', tickformat: '.2s' },
  }, PLOTLY_CONFIG);
}

/* ── Supplier / Customer tables ────────────────────────────────────────────── */

function renderOpsSuppliersTable(payload) {
  const suppliers = payload?.suppliers || [];
  const el = document.getElementById('ops-suppliers-table');
  if (!el) return;
  if (!suppliers || suppliers.length === 0) {
    el.innerHTML = '<div class="empty-state">No supplier data.</div>';
    return;
  }

  // M2.2.1 enrichment helpers
  const _stripTaxZero = v => {
    if (v == null) return '';
    let s = String(v).trim();
    if (s.endsWith('.0')) s = s.slice(0, -2);
    return s;
  };
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };
  const _fmtFx = (v, sym) => {
    if (v == null || isNaN(v) || v === 0) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e6) return sym + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sym + (v/1e3).toFixed(0) + 'K';
    return sym + v.toFixed(0);
  };
  const _badges = s => {
    const out = [];
    if (s.is_verified === false) {
      out.push('<span class="ce-badge ce-badge-warn" title="No verified tax id — name-grouped">no-tax</span>');
    }
    if (s.name_variants_count > 1) {
      out.push(`<span class="ce-badge ce-badge-info" title="${s.name_variants_count} display name variants">${s.name_variants_count} vars</span>`);
    }
    return out.join(' ');
  };
  const _trendCell = t => {
    if (t === '▲') return '<span class="trend-up" title="Spend rising (last 6m vs prior 6m, ≥10%)">▲</span>';
    if (t === '▼') return '<span class="trend-down" title="Spend falling (last 6m vs prior 6m, ≥10%)">▼</span>';
    return '<span class="trend-flat" title="Spend stable (within ±10%)">–</span>';
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Supplier</th>
          <th class="num">TL spend</th>
          <th class="num">Share</th>
          <th class="num">USD invoiced</th>
          <th class="num">EUR invoiced</th>
          <th>Top bucket</th>
          <th class="num">Buckets</th>
          <th class="num">Last invoice</th>
          <th class="num">Trend</th>
        </tr>
      </thead>
      <tbody>
        ${suppliers.map((s, i) => `
          <tr>
            <td class="num">${i+1}</td>
            <td>
              <div class="cell-supplier">
                <span class="supplier-name">${(s.supplier_name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
                ${_badges(s) ? `<span class="supplier-badges">${_badges(s)}</span>` : ''}
              </div>
            </td>
            <td class="num">${_fmtTL(s.amount_tl)}</td>
            <td class="num">${s.share_pct != null ? s.share_pct.toFixed(2) + '%' : '—'}</td>
            <td class="num">${_fmtFx(s.amount_usd, '$')}</td>
            <td class="num">${_fmtFx(s.amount_eur, '€')}</td>
            <td>${(s.top_bucket || '—').replace(/_/g, ' ')}</td>
            <td class="num">${s.bucket_count}</td>
            <td class="num">${s.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(s.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderOpsCustomersTable(payload) {
  // Accept either an array (legacy callers) or a {customers: [...]} payload (new pattern)
  const customers = Array.isArray(payload)
    ? payload
    : (payload?.customers || []);
  const el = document.getElementById('ops-customers-table');
  if (!el) return;
  if (!customers || customers.length === 0) {
    el.innerHTML = '<div class="empty-state">No customer data.</div>';
    return;
  }

  // M2.3.1 enrichment helpers (same as M2.2.1)
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };
  const _fmtFx = (v, sym) => {
    if (v == null || isNaN(v) || v === 0) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e6) return sym + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sym + (v/1e3).toFixed(0) + 'K';
    return sym + v.toFixed(0);
  };
  const _badges = c => {
    const out = [];
    if (c.is_verified === false) {
      out.push('<span class="ce-badge ce-badge-warn" title="No verified tax id — name-grouped">no-tax</span>');
    }
    if (c.name_variants_count > 1) {
      out.push(`<span class="ce-badge ce-badge-info" title="${c.name_variants_count} display name variants">${c.name_variants_count} vars</span>`);
    }
    return out.join(' ');
  };
  const _trendCell = t => {
    if (t === '▲') return '<span class="trend-up" title="Revenue rising (last 6m vs prior 6m, ≥10%)">▲</span>';
    if (t === '▼') return '<span class="trend-down" title="Revenue falling (last 6m vs prior 6m, ≥10%)">▼</span>';
    return '<span class="trend-flat" title="Revenue stable (within ±10%)">–</span>';
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Customer</th>
          <th class="num">TL revenue</th>
          <th class="num">Share</th>
          <th class="num">USD invoiced</th>
          <th class="num">EUR invoiced</th>
          <th class="num">Buckets</th>
          <th class="num">Last invoice</th>
          <th class="num">Trend</th>
        </tr>
      </thead>
      <tbody>
        ${customers.map((c, i) => `
          <tr>
            <td class="num">${i+1}</td>
            <td>
              <div class="cell-supplier">
                <span class="supplier-name">${(c.customer_name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
                ${_badges(c) ? `<span class="supplier-badges">${_badges(c)}</span>` : ''}
              </div>
            </td>
            <td class="num">${_fmtTL(c.amount_tl)}</td>
            <td class="num">${c.share_pct != null ? c.share_pct.toFixed(2) + '%' : '—'}</td>
            <td class="num">${_fmtFx(c.amount_usd, '$')}</td>
            <td class="num">${_fmtFx(c.amount_eur, '€')}</td>
            <td class="num">${c.bucket_count}</td>
            <td class="num">${c.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(c.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

/* ── End of Operations Intelligence block ─────────────────────────────────── */


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
      ${item.vergi_numarasi ? `<div class="ce-li-tax">vn: ${stripTaxZero(item.vergi_numarasi)}</div>` : ''}
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
  // Fix 1: clear any lingering "Loading…" title with the actual name
  document.getElementById('ce-detail-name').textContent = d.display_name || '<unknown>';

  // Fix 4: explicit mode badge (Supplier/Customer)
  const modeLabel = (d.side === 'purchase')
    ? 'Mode: Supplier (ALIŞ)'
    : 'Mode: Customer (SATIŞ)';

  // Badges (mode + verification + name drift + counterparty type)
  const badgesEl = document.getElementById('ce-detail-badges');
  const bd = [];
  bd.push(`<span class="ce-badge ce-badge-mode">${modeLabel}</span>`);
  if (!d.is_verified) bd.push('<span class="ce-badge ce-badge-warn">tax id missing · name-grouped</span>');
  if (d.name_variants_count > 1) bd.push(`<span class="ce-badge ce-badge-info">${d.name_variants_count} name variants</span>`);
  if (d.counterparty_type) bd.push(`<span class="ce-badge ce-badge-neutral">${d.counterparty_type}</span>`);
  badgesEl.innerHTML = bd.join(' ');

  // Fix 2: meta line — strip .0 from tax id
  const metaEl = document.getElementById('ce-detail-meta');
  metaEl.innerHTML = `
    <div class="ce-meta-row"><span>Tax id:</span> <strong>${stripTaxZero(d.vergi_numarasi) || '—'}</strong></div>
    <div class="ce-meta-row"><span>Window:</span> <strong>${d.months}m</strong> ending ${d.data_horizon || '—'}</div>
    <div class="ce-meta-row"><span>First invoice:</span> <strong>${d.summary.first_invoice || '—'}</strong></div>
  `;

  // Summary KPIs
  document.getElementById('ce-stat-tl').textContent = ceFmtTL(d.summary.total_tl);
  document.getElementById('ce-stat-usd').textContent = d.summary.total_usd ? '$' + ceFmtNum(d.summary.total_usd) : '—';
  document.getElementById('ce-stat-eur').textContent = d.summary.total_eur ? '€' + ceFmtNum(d.summary.total_eur) : '—';
  document.getElementById('ce-stat-rows').textContent = d.summary.row_count.toLocaleString();
  document.getElementById('ce-stat-share').textContent = d.summary.share_of_total_pct.toFixed(2) + '%';
  document.getElementById('ce-stat-last').textContent = d.summary.last_invoice || '—';

  // Fix 3: relabel KPI tiles to be unambiguous
  const tlLabel = document.querySelector('#ce-stat-tl')?.parentElement?.querySelector('.ce-stat-label');
  const usdLabel = document.querySelector('#ce-stat-usd')?.parentElement?.querySelector('.ce-stat-label');
  const eurLabel = document.querySelector('#ce-stat-eur')?.parentElement?.querySelector('.ce-stat-label');
  if (tlLabel)  tlLabel.textContent  = `${d.months}m TL (all rows)`;
  if (usdLabel) usdLabel.textContent = `${d.months}m USD invoiced (orig. ccy)`;
  if (eurLabel) eurLabel.textContent = `${d.months}m EUR invoiced (orig. ccy)`;

  // Fix 4: bucket split heading reflects mode
  const bucketHeading = document.querySelector('#ce-bucket-table')?.closest('.ce-block')?.querySelector('h4');
  if (bucketHeading) {
    bucketHeading.textContent = (d.side === 'purchase')
      ? 'Purchase-side bucket split'
      : 'Sales-side bucket split';
  }

  // Monthly trend
  ceRenderMonthlyChart(d.monthly_trend);

  // Bucket table
  const bbody = document.querySelector('#ce-bucket-table tbody');
  bbody.innerHTML = '';
  d.bucket_split.forEach(b => {
    bbody.innerHTML += `<tr><td>${escapeHtml(b.bucket || '<null>')}</td><td class="num">${ceFmtTL(b.amount_tl)}</td><td class="num">${b.share_pct}%</td><td class="num">${b.rows}</td></tr>`;
  });

  // Currency split — note the "TL equivalent" semantics in the column header
  const ccyHeading = document.querySelector('#ce-ccy-table thead tr');
  if (ccyHeading) {
    ccyHeading.innerHTML = '<th>Original ccy</th><th class="num">TL equivalent</th><th class="num">Rows</th>';
  }
  const cbody = document.querySelector('#ce-ccy-table tbody');
  cbody.innerHTML = '';
  d.currency_split.forEach(c => {
    cbody.innerHTML += `<tr><td>${escapeHtml(c.ccy)}</td><td class="num">${ceFmtTL(c.amount_tl)}</td><td class="num">${c.rows}</td></tr>`;
  });

  // Top accounts
  const abody = document.querySelector('#ce-accounts-table tbody');
  abody.innerHTML = '';
  d.top_accounts.forEach(a => {
    abody.innerHTML += `<tr><td><code>${escapeHtml(a.hesap_kodu || '')}</code></td><td>${escapeHtml((a.hesap_aciklamasi || '').slice(0, 40))}</td><td class="num">${ceFmtTL(a.amount_tl)}</td><td class="num">${a.rows}</td></tr>`;
  });

  // Subtype
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

// stripTaxZero (M2.1 v1.1)
function stripTaxZero(v) {
  if (v == null) return '';
  let s = String(v).trim();
  if (s.endsWith('.0')) s = s.slice(0, -2);
  return s;
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


// === COUNTERPARTY SUB-TAB WIRING (M2.1 relocate) ===
// Initialize Counterparty Explorer when its sub-tab becomes active.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-sub="ops-counterparty"]').forEach(btn => {
    btn.addEventListener('click', () => {
      // Defer slightly to let the section become visible first
      setTimeout(() => {
        if (typeof ceInit === 'function' && !window.CE?._initialized) {
          ceInit();
          if (window.CE) window.CE._initialized = true;
          if (typeof ceFetchList === 'function') ceFetchList();
        }
      }, 50);
    });
  });
});
// === END COUNTERPARTY SUB-TAB WIRING ===

// === PROCUREMENT KPI STRIP (M2.2.2) ===
async function loadProcurementKpis() {
  const el = document.getElementById('ops-procurement-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/procurement-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No procurement KPI data.</div>';
      return;
    }
    renderProcurementKpis(data);
  } catch (e) {
    console.error('procurement-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderProcurementKpis(d) {
  const el = document.getElementById('ops-procurement-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtInt = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString();
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    const abs = Math.abs(v);
    if (abs >= 1e9) return sign + '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return sign + '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sign + '₺' + (v/1e3).toFixed(0) + 'K';
    return sign + '₺' + v.toFixed(0);
  };
  const _fmtPctSigned = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + '%';
  };
  const _bucketLabel = s => (s || '—').replace(/_/g, ' ');
  const _moverClass = v => v == null ? '' : (v >= 0 ? 'mover-up' : 'mover-down');

  const moverDirection = (d.biggest_mover_tl != null && d.biggest_mover_tl >= 0) ? '▲' : '▼';

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Top 3 supplier share</div>
        <div class="proc-kpi-value">${_fmtPct(d.top_3_supplier_share_pct)}</div>
        <div class="proc-kpi-sub">of cost-relevant 12m procurement</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">FX-invoiced share</div>
        <div class="proc-kpi-value">${_fmtPct(d.fx_invoiced_share_pct)}</div>
        <div class="proc-kpi-sub">USD + EUR invoicing</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active suppliers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_supplier_count)}</div>
        <div class="proc-kpi-sub">distinct cost-relevant</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Yarn share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.yarn_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Greige share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.greige_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Largest MoM mover (${d.latest_month || '—'} vs ${d.prior_month || '—'})</div>
        <div class="proc-kpi-value-sm ${_moverClass(d.biggest_mover_tl)}">
          ${moverDirection} ${_bucketLabel(d.biggest_mover_bucket)}
          <span class="proc-kpi-mover-detail">${_fmtPctSigned(d.biggest_mover_pct)} (${_fmtTL(d.biggest_mover_tl)})</span>
        </div>
      </div>
    </div>
  `;
}
// === END PROCUREMENT KPI STRIP ===


// === REVENUE KPI STRIP (M2.3.2) ===
async function loadRevenueKpis() {
  const el = document.getElementById('ops-revenue-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/revenue-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No revenue KPI data.</div>';
      return;
    }
    renderRevenueKpis(data);
  } catch (e) {
    console.error('revenue-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderRevenueKpis(d) {
  const el = document.getElementById('ops-revenue-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtInt = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString();
  const _fmtPP = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + 'pp';
  };
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };

  // Avg monthly revenue (frontend-computed)
  const avgMonthly = (d.core_total_12m_tl != null) ? d.core_total_12m_tl / 12 : null;

  // KPI 6: concentration shift — color INVERTED relative to Procurement.
  //   Δ positive (rising concentration)  → RED  (more risk)
  //   Δ negative (dispersing)            → GREEN (less risk)
  //   Δ small (stable)                   → muted
  const concDelta = d.top_3_share_delta_pp;
  let concClass = 'mover-flat';
  let concArrow = '–';
  if (concDelta != null) {
    if (concDelta >= 1.0) {
      concClass = 'mover-down'; // RED — concentration up = bad
      concArrow = '▲';
    } else if (concDelta <= -1.0) {
      concClass = 'mover-up';   // GREEN — concentration down = good
      concArrow = '▼';
    }
  }

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Top 3 customer share</div>
        <div class="proc-kpi-value">${_fmtPct(d.top_3_customer_share_pct)}</div>
        <div class="proc-kpi-sub">of core 12m revenue</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">FX-invoiced share</div>
        <div class="proc-kpi-value">${_fmtPct(d.fx_invoiced_share_pct)}</div>
        <div class="proc-kpi-sub">USD + EUR invoicing</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active customers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_customer_count)}</div>
        <div class="proc-kpi-sub">distinct core customers</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context-4">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Core revenue share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.core_revenue_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Avg monthly revenue</div>
        <div class="proc-kpi-value-sm">${_fmtTL(avgMonthly)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Contra share of gross</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.contra_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Top 3 share Δ (${d.latest_month || '—'} vs ${d.prior_month || '—'})</div>
        <div class="proc-kpi-value-sm ${concClass}">
          ${concArrow} ${_fmtPP(concDelta)}
          <span class="proc-kpi-mover-detail">${_fmtPct(d.top_3_share_prior_pct)} → ${_fmtPct(d.top_3_share_latest_pct)}</span>
        </div>
      </div>
    </div>
  `;
}
// === END REVENUE KPI STRIP ===


/* ── Customer concentration trend chart (M2.3.3) ───────────────────────── */
async function loadCustomerConcentrationChart() {
  try {
    const data = await api('/api/internal/customer-concentration-trend');
    if (!data || !data.data || !data.data.length) return;
    renderOpsCustomerConcentrationChart(data);
  } catch (e) {
    console.error('customer-concentration fetch failed', e);
  }
}

function renderOpsCustomerConcentrationChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = data.map(d => d.month);
  const top1   = data.map(d => d.top_1_share_pct  ?? null);
  const top3   = data.map(d => d.top_3_share_pct  ?? null);
  const top10  = data.map(d => d.top_10_share_pct ?? null);
  const threshold = payload.threshold ?? 33;

  const traces = [
    {
      x: months, y: top10,
      name: 'Top 10 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.green, width: 2 },
      marker: { color: C.green, size: 5 },
      hovertemplate: 'Top 10: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top3,
      name: 'Top 3 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.orange, width: 2.5 },
      marker: { color: C.orange, size: 6 },
      hovertemplate: 'Top 3: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top1,
      name: 'Top 1 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.blue, width: 2 },
      marker: { color: C.blue, size: 5 },
      hovertemplate: 'Top 1: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: months.map(_ => threshold),
      name: `Watch zone (${threshold}%)`,
      type: 'scatter', mode: 'lines',
      line: { color: C.red || '#e03131', width: 1.2, dash: 'dash' },
      hovertemplate: `Watch: ${threshold}%<extra></extra>`,
    },
  ];

  Plotly.newPlot('chart-ops-customer-concentration', traces, {
    ...PLOTLY_BASE,
    height: 360,
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: {
      ...PLOTLY_BASE.yaxis,
      ticksuffix: '%',
      range: [0, 100],
      tickvals: [0, 25, 50, 75, 100],
    },
    annotations: [
      {
        xref: 'paper', yref: 'y',
        x: 1, xanchor: 'right',
        y: threshold, yanchor: 'bottom',
        text: `Top 3 watch zone (${threshold}%)`,
        showarrow: false,
        font: { color: C.red || '#e03131', size: 10 },
      },
    ],
  }, PLOTLY_CONFIG);
}


/* ── Top Cost Suppliers table (M2.4.1) ────────────────────────────────── */
async function loadCostSuppliersTable() {
  try {
    const data = await api('/api/internal/top-cost-suppliers?limit=10');
    if (!data) return;
    renderOpsCostSuppliersTable(data);
  } catch (e) {
    console.error('top-cost-suppliers fetch failed', e);
  }
}

function renderOpsCostSuppliersTable(payload) {
  const suppliers = Array.isArray(payload) ? payload : (payload?.suppliers || []);
  const el = document.getElementById('ops-cost-suppliers-table');
  if (!el) return;
  if (!suppliers || suppliers.length === 0) {
    el.innerHTML = '<div class="empty-state">No cost supplier data.</div>';
    return;
  }

  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };
  const _fmtFx = (v, sym) => {
    if (v == null || isNaN(v) || v === 0) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e6) return sym + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sym + (v/1e3).toFixed(0) + 'K';
    return sym + v.toFixed(0);
  };
  const _badges = s => {
    const out = [];
    if (s.is_verified === false) {
      out.push('<span class="ce-badge ce-badge-warn" title="No verified tax id — name-grouped">no-tax</span>');
    }
    if (s.name_variants_count > 1) {
      out.push(`<span class="ce-badge ce-badge-info" title="${s.name_variants_count} display name variants">${s.name_variants_count} vars</span>`);
    }
    return out.join(' ');
  };
  const _trendCell = t => {
    if (t === '▲') return '<span class="trend-up" title="Spend rising (last 6m vs prior 6m, ≥10%)">▲</span>';
    if (t === '▼') return '<span class="trend-down" title="Spend falling (last 6m vs prior 6m, ≥10%)">▼</span>';
    return '<span class="trend-flat" title="Stable (within ±10%)">–</span>';
  };
  // Compact bucket spread cell:
  //   "utilities · 100%"   (when 2nd missing)
  //   "outsourced · 67% | factory_overhead · 22%"   (when 2nd present)
  const _bucketCell = s => {
    if (!s.top_bucket) return '—';
    const tb = s.top_bucket;
    const tbpct = (s.top_bucket_share_pct != null) ? s.top_bucket_share_pct.toFixed(0) + '%' : '—';
    let out = `${tb} · ${tbpct}`;
    if (s.secondary_bucket) {
      const sb = s.secondary_bucket;
      const sbpct = (s.secondary_bucket_share_pct != null) ? s.secondary_bucket_share_pct.toFixed(0) + '%' : '—';
      out += ` <span class="bucket-secondary">| ${sb} · ${sbpct}</span>`;
    }
    return out;
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers ops-cost-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Supplier</th>
          <th class="num">TL spend</th>
          <th class="num">Share</th>
          <th>Bucket spread</th>
          <th class="num">Buckets</th>
          <th class="num">Last invoice</th>
          <th class="num">Trend</th>
        </tr>
      </thead>
      <tbody>
        ${suppliers.map((s, i) => `
          <tr>
            <td class="num">${i+1}</td>
            <td>
              <div class="cell-supplier">
                <span class="supplier-name">${(s.supplier_name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
                ${_badges(s) ? `<span class="supplier-badges">${_badges(s)}</span>` : ''}
              </div>
            </td>
            <td class="num">${_fmtTL(s.amount_tl)}</td>
            <td class="num">${s.share_pct != null ? s.share_pct.toFixed(2) + '%' : '—'}</td>
            <td class="bucket-cell">${_bucketCell(s)}</td>
            <td class="num">${s.bucket_count}</td>
            <td class="num">${s.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(s.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}


// === COST KPI STRIP (M2.4.2) ===
async function loadCostKpis() {
  const el = document.getElementById('ops-cost-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/cost-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No cost KPI data.</div>';
      return;
    }
    renderCostKpis(data);
  } catch (e) {
    console.error('cost-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderCostKpis(d) {
  const el = document.getElementById('ops-cost-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtPctSm = v => (v == null || isNaN(v)) ? '—' : v.toFixed(1) + '%';
  const _fmtInt = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString();
  const _fmtPP = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + 'pp';
  };
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };

  // KPI 6: cost/revenue ratio shift — color INVERTED.
  //   Δ positive (ratio up = margin compression) → RED  (bad)
  //   Δ negative (ratio down = margin expansion) → GREEN (good)
  //   Δ small (stable)                          → muted
  const ratioDelta = d.cost_revenue_ratio_delta_pp;
  let ratioClass = 'mover-flat';
  let ratioArrow = '–';
  if (ratioDelta != null) {
    if (ratioDelta >= 0.5) {
      ratioClass = 'mover-down'; // RED — margin compression
      ratioArrow = '▲';
    } else if (ratioDelta <= -0.5) {
      ratioClass = 'mover-up';   // GREEN — margin expansion
      ratioArrow = '▼';
    }
  }

  // 3m window labels (e.g. "2026-01—2026-03 vs 2025-10—2025-12")
  const recentLabel = (d.recent_window_start && d.recent_window_end)
    ? `${d.recent_window_start}—${d.recent_window_end}`
    : '—';
  const priorLabel = (d.prior_window_start && d.prior_window_end)
    ? `${d.prior_window_start}—${d.prior_window_end}`
    : '—';

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Operating cost share of revenue</div>
        <div class="proc-kpi-value">${_fmtPct(d.cost_share_of_revenue_pct)}</div>
        <div class="proc-kpi-sub">excludes raw materials (in Procurement)</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Outsourced processing share</div>
        <div class="proc-kpi-value">${_fmtPct(d.outsourced_processing_share_pct)}</div>
        <div class="proc-kpi-sub">of total operating cost</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active cost suppliers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_cost_supplier_count)}</div>
        <div class="proc-kpi-sub">distinct, cost scope only</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context-3">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Maintenance share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.maintenance_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Avg monthly cost</div>
        <div class="proc-kpi-value-sm">${_fmtTL(d.avg_monthly_cost_tl)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Cost/revenue Δ (${recentLabel} vs ${priorLabel})</div>
        <div class="proc-kpi-value-sm ${ratioClass}">
          ${ratioArrow} ${_fmtPP(ratioDelta)}
          <span class="proc-kpi-mover-detail">${_fmtPctSm(d.cost_revenue_ratio_prior_pct)} → ${_fmtPctSm(d.cost_revenue_ratio_recent_pct)}</span>
        </div>
      </div>
    </div>
  `;
}
// === END COST KPI STRIP ===


/* ── Cost mix-% chart (M2.4.3) ───────────────────────────────────────── */
/* Frontend-only. Re-uses cost-structure-trend payload that the absolute  */
/* chart already fetches (renderOpsCostChart receives it).                */
/* The activation hook below calls renderOpsCostMixChart(_opsData.cost)   */
/* whenever the user opens the Cost sub-tab.                              */
function renderOpsCostMixChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  // Group by month, then compute per-bucket share within each month
  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = [...new Set(data.map(d => d.business_bucket))];

  // Build month -> bucket -> tl map
  const lookup = {};
  data.forEach(r => {
    if (!lookup[r.month]) lookup[r.month] = {};
    lookup[r.month][r.business_bucket] = r.amount_tl || 0;
  });

  // Per-bucket trace (% of monthly total)
  const bucketColor = {
    utilities:              '#4dabf7',
    maintenance_factory:    '#ffd43b',
    packaging:              '#74c0fc',
    factory_overhead:       '#a78bfa',
    outsourced_processing:  '#69db7c',
    logistics_distribution: '#ff8787',
  };

  const traces = buckets.map(b => {
    const y = months.map(m => {
      const monthRow = lookup[m] || {};
      const total = Object.values(monthRow).reduce((s, v) => s + (v || 0), 0);
      const val = monthRow[b] || 0;
      return total > 0 ? 100.0 * val / total : 0;
    });
    return {
      x: months, y: y,
      name: b,
      type: 'scatter', mode: 'lines',
      stackgroup: 'one',
      line: { width: 0.5, color: bucketColor[b] || C.muted },
      fillcolor: bucketColor[b] || C.muted,
      hovertemplate: `${b}: %{y:.1f}%<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-cost-mix', traces, {
    ...PLOTLY_BASE,
    height: 360,
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


// === COST MOVERS STRIP (M2.4.4) ===
async function loadCostMovers() {
  const el = document.getElementById('ops-cost-movers');
  if (!el) return;
  try {
    const data = await api('/api/internal/cost-movers');
    if (!data) return;
    renderCostMovers(data);
  } catch (e) {
    console.error('cost-movers fetch failed', e);
  }
}

function renderCostMovers(payload) {
  const el = document.getElementById('ops-cost-movers');
  const movers = payload?.movers || [];

  // Index by slot for O(1) lookup
  const bySlot = {};
  movers.forEach(m => { bySlot[m.slot] = m; });

  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    if (abs >= 1e9) return sign + '₺' + (abs/1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return sign + '₺' + (abs/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sign + '₺' + (abs/1e3).toFixed(0) + 'K';
    return sign + '₺' + abs.toFixed(0);
  };
  const _fmtPct = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + '%';
  };

  const _renderCard = (slotKey, label, kind) => {
    const m = bySlot[slotKey];
    const empty = !m || !m.bucket;
    const emptyMsg = (kind === 'volatility')
      ? 'no high-volatility bucket (CV < 0.20)'
      : 'no significant change this month';

    if (empty) {
      return `
        <div class="cost-mover-card cost-mover-${kind} cost-mover-empty">
          <div class="cost-mover-label">${label}</div>
          <div class="cost-mover-value">—</div>
          <div class="cost-mover-sub">${emptyMsg}</div>
        </div>`;
    }

    if (kind === 'volatility') {
      return `
        <div class="cost-mover-card cost-mover-${kind}">
          <div class="cost-mover-label">${label}</div>
          <div class="cost-mover-value">~ ${m.bucket}</div>
          <div class="cost-mover-sub">CV ${m.cv != null ? m.cv.toFixed(2) : '—'}</div>
        </div>`;
    }

    // increase / decrease
    const arrow = (kind === 'increase') ? '▲' : '▼';
    const pctStr = _fmtPct(m.pct_change);
    const absStr = _fmtTL(m.abs_change_tl);
    return `
      <div class="cost-mover-card cost-mover-${kind}">
        <div class="cost-mover-label">${label}</div>
        <div class="cost-mover-value">${arrow} ${m.bucket}</div>
        <div class="cost-mover-sub">${pctStr} <span class="cost-mover-abs">(${absStr})</span></div>
      </div>`;
  };

  el.innerHTML = `
    ${_renderCard('biggest_increase',   'Biggest increase',   'increase')}
    ${_renderCard('biggest_decrease',   'Biggest decrease',   'decrease')}
    ${_renderCard('highest_volatility', 'Highest volatility (12m)', 'volatility')}
  `;
}
// === END COST MOVERS STRIP ===


// === OVERVIEW SIGNALS STRIP (M2.5.1) ===
async function loadOverviewSignals() {
  const el = document.getElementById('ops-signals-strip');
  if (!el) return;
  try {
    const data = await api('/api/internal/overview-signals');
    if (!data) return;
    renderOverviewSignals(data);
  } catch (e) {
    console.error('overview-signals fetch failed', e);
  }
}

function renderOverviewSignals(payload) {
  const el = document.getElementById('ops-signals-strip');
  const signals = payload?.signals || [];
  if (!signals.length) {
    el.innerHTML = '';
    return;
  }

  // Severity → CSS class + icon
  const _sevIcon = sev => {
    if (sev === 'critical') return '🔴';
    if (sev === 'warning')  return '🟡';
    if (sev === 'ok')       return '🟢';
    return '⚪';
  };

  // Paint section health badges from the same payload (M2.5.3)
  if (typeof renderSectionHealthBadges === 'function') {
    renderSectionHealthBadges(payload); // renderSectionHealthBadges call inside renderOverviewSignals
  }

  el.innerHTML = signals.map(s => `
    <div class="signal-card signal-${s.severity || 'ok'}">
      <div class="signal-head">
        <span class="signal-icon">${_sevIcon(s.severity)}</span>
        <span class="signal-title">${(s.title || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
      </div>
      <div class="signal-metric">${(s.metric_text || '—').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>
      <div class="signal-why">${(s.why_text || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>
    </div>
  `).join('');
}
// === END OVERVIEW SIGNALS STRIP ===


/* ── Section health badges (M2.5.3) ──────────────────────────────────── */
/* Rolls up the overview-signals payload into one severity per section,   */
/* paints a dot on each section header, and wires the header to switch    */
/* to the corresponding sub-tab on click.                                 */
function renderSectionHealthBadges(signalsPayload) {
  const signals = signalsPayload?.signals || [];
  if (!signals.length) return;

  const bySlot = {};
  signals.forEach(s => { bySlot[s.signal_key] = s; });

  // Severity weight (higher = worse)
  const sevRank = { critical: 3, warning: 2, ok: 1, info: 1 };
  const _worst = (...keys) => {
    let worst = 'ok';
    keys.forEach(k => {
      const sev = bySlot[k]?.severity || 'ok';
      if ((sevRank[sev] || 0) > (sevRank[worst] || 0)) worst = sev;
    });
    return worst;
  };

  const sectionHealth = {
    procurement: _worst('procurement_concentration'),
    cost:        _worst('margin_trend'),
    revenue:     _worst('customer_concentration', 'contra_revenue'),
  };

  const _paintHeader = (id, severity) => {
    const el = document.getElementById(id);
    if (!el) return;
    // Reset previous severity classes
    el.classList.remove('section-health-critical', 'section-health-warning', 'section-health-ok');
    el.classList.add(`section-health-${severity}`);

    // Inject (or refresh) the dot + chevron decorations.
    // We rebuild the inner content each call so re-renders don't stack badges.
    const labelText = el.dataset.labelText || el.textContent.trim();
    el.dataset.labelText = labelText;
    el.innerHTML = `
      <span class="section-health-dot" aria-hidden="true"></span>
      <span class="section-health-label">${labelText}</span>
      <span class="section-health-chevron" aria-hidden="true">→</span>
    `;

    // Click handler — navigate to the matching sub-tab.
    if (!el.dataset.clickWired) {
      el.style.cursor = 'pointer';
      el.addEventListener('click', () => {
        const target = el.dataset.target;
        if (!target) return;
        const btn = document.querySelector(`.sub-nav-btn[data-sub="${target}"]`);
        if (btn) btn.click();
      });
      el.dataset.clickWired = '1';
    }
  };

  _paintHeader('ops-section-header-procurement', sectionHealth.procurement);
  _paintHeader('ops-section-header-cost',        sectionHealth.cost);
  _paintHeader('ops-section-header-revenue',     sectionHealth.revenue);
}


// PI-1.2: Price Intelligence KPI strip
async function _loadPriceIntelStats() {
  try {
    const stats = await api('/api/price_intelligence_stats');
    setText('kpi-pi-action',     stats.action_now ?? '—');
    setText('kpi-pi-cost-up',    stats.cost_pressure_up ?? '—');
    setText('kpi-pi-cost-down',  stats.cost_pressure_down ?? '—');

    const fdyUsd = stats.polyester_fdy_usd;
    setText('kpi-pi-fdy', fdyUsd != null ? `$${Math.round(fdyUsd).toLocaleString()}` : '—');

    const chg = stats.polyester_fdy_chg7d;
    const chgEl = document.getElementById('kpi-pi-fdy-change');
    if (chgEl) {
      if (chg != null) {
        const sign = chg >= 0 ? '+' : '';
        const cls = chg >= 0 ? 'kpi-change-up' : 'kpi-change-down';
        chgEl.textContent = `${sign}${chg.toFixed(1)}% 7d`;
        chgEl.className = `kpi-change ${cls}`;
      } else {
        chgEl.textContent = '';
      }
    }
  } catch (e) {
    console.warn('Price Intelligence stats failed:', e);
  }
}

// Show/hide the global header KPI strip vs the Price Intelligence-specific one.
// Called on every section navigation.
function _togglePriceIntelKpiStrip() {
  const active = document.querySelector('section.section.active');
  const isPriceTab = active && active.id === 'section-prices';

  // Global header strip lives in <header>, has class 'kpi-strip' and no id.
  // The PI-specific one has id='kpi-strip-price'. Hide global on price tab.
  const headerStrip = document.querySelector('header .kpi-strip');
  if (headerStrip) {
    headerStrip.style.display = isPriceTab ? 'none' : '';
  }

  if (isPriceTab) _loadPriceIntelStats();
}

// Hook into existing nav-item click handlers AFTER they've fired.
document.addEventListener('click', (ev) => {
  const navItem = ev.target.closest('.nav-item[data-section]');
  if (!navItem) return;
  // Defer to next tick so the .active class swap has happened.
  setTimeout(_togglePriceIntelKpiStrip, 0);
});

// Run once on initial load to catch direct landing on Price Intelligence.
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(_togglePriceIntelKpiStrip, 100);
});

