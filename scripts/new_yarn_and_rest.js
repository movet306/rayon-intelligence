/* ── Yarn Intelligence — Phase A 1.5 ─────────────────────────────────────────── */
async function loadYarnIntelligence() {
  const tbody    = document.getElementById('yarn-pressure-tbody');
  const summary  = document.getElementById('yarn-pressure-summary');
  const covStrip = document.getElementById('yarn-coverage-strip');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="8" class="loading">Yukleniyor...</td></tr>';

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
      ? `<span class="turkey-lag-badge">${a}\u2013${b} hf</span>`
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
        </tr>`;
      } else {
        html += `<tr class="yarn-driver-row yarn-driver-row-nodriver" data-group="${groupId}">
          <td class="yarn-expand-cell">
            <span class="yarn-expand-caret">\u25B6</span>
          </td>
          <td colspan="7" class="muted">
            <em>No driver assigned</em> \u00B7 ${items.length} spec${items.length === 1 ? '' : 's'}
          </td>
        </tr>`;
      }

      // SPEC (child) rows — metadata only
      items.forEach(y => {
        const subspec = y.subspec_sensitive
          ? ' <span title="Alt-spec varyantlar mevcut \u2014 fiyat farki olabilir" style="color:#f0883e;font-size:10px">\u26a0</span>'
          : '';

        const chips = [];
        if (y.denier != null)         chips.push(`<span class="spec-meta-chip chip-denier">${y.denier}D</span>`);
        if (y.filament_count != null) chips.push(`<span class="spec-meta-chip chip-filament">${y.filament_count}F</span>`);
        if (y.luster)                 chips.push(`<span class="spec-meta-chip chip-luster">${esc(y.luster)}</span>`);
        if (y.recycle_flag)           chips.push(`<span class="spec-meta-chip chip-recycle">GRS</span>`);
        if (y.alias_count)            chips.push(`<span class="spec-meta-chip chip-alias" title="${y.alias_count} label alias(es) mapped to this spec">${y.alias_count} alias${y.alias_count === 1 ? '' : 'es'}</span>`);
        if (y.is_placeholder)         chips.push(`<span class="spec-meta-chip chip-placeholder">placeholder</span>`);

        const coverageCell = renderCoverageChip(y.coverage_status || 'driver-priced');

        html += `<tr class="yarn-spec-row" data-group="${groupId}" style="display:none">
          <td></td>
          <td class="spec-primary">${esc(y.yarn_code)}${subspec}</td>
          <td colspan="5" class="spec-meta-cell">${chips.join(' ')}</td>
          <td class="num">${coverageCell}</td>
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
    tbody.innerHTML = `<tr><td colspan="8" class="error">Yuklenemedi: ${e.message}</td></tr>`;
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