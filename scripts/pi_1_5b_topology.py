"""
pi_1_5b_topology.py - Polyester chain topology correction.

Replaces the misleading linear chain (PTA → PSF → FDY → POY → DTY) with the
industrially correct branched topology:

                    ┌── PSF                     (staple branch)
    PTA ────────────┤
                    └── POY ─── DTY             (filament branch)
                         │
                         └── FDY                (parallel filament)

What changes:
  - JS:  POLY_CHAIN linear array replaced with POLY_TOPOLOGY branched object.
  - JS:  _renderChainFlow rewritten to render the branched layout via CSS grid.
  - JS:  POLY_MATS reordered so chart legend reads in branch order
         (PTA, PSF, POY, DTY, FDY) instead of the false linear order.
  - HTML: section title updated to "Polyester Chain — Staple & Filament".
  - CSS: new classes for branched chain layout appended.

What does NOT change:
  - The chart itself (still 5 lines with the same colors).
  - Chart line colors. PSF stays blue, FDY stays orange, POY stays green,
    DTY stays purple. PTA teal (set in PI-1.5).
  - CHAIN_UPSTREAM mapping. Already correct: PSF/POY/FDY all point to PTA;
    DTY points to POY. Divergence badges keep working.
  - Any backend / SQL / data.

Reversal: revert _renderChainFlow + POLY_TOPOLOGY + the HTML title;
the CSS additions are inert if the new classes are unused.

Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS   = REPO / "dashboard" / "static" / "style.v5.css"

src = APPJS.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Change 1: replace POLY_CHAIN with POLY_TOPOLOGY (branched object)
# ─────────────────────────────────────────────────────────────────────────────
OLD_POLY_CHAIN = """const POLY_CHAIN = [
  { key: 'pta',                    label: 'PTA',  color: C.blue   },
  { key: 'polyester_staple_fiber', label: 'PSF',  color: C.purple },
  { key: 'polyester_fdy',          label: 'FDY',  color: C.orange },
  { key: 'polyester_poy',          label: 'POY',  color: C.green  },
  { key: 'polyester_dty',          label: 'DTY',  color: '#a371f7'},
];"""

NEW_POLY_CHAIN = """// PI-1.5b: linear POLY_CHAIN replaced with branched POLY_TOPOLOGY.
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
];"""

if "POLY_TOPOLOGY" in src:
    print("[skip] (1) POLY_TOPOLOGY already present")
elif OLD_POLY_CHAIN in src:
    src = src.replace(OLD_POLY_CHAIN, NEW_POLY_CHAIN)
    print("[OK]   (1) POLY_CHAIN replaced with branched POLY_TOPOLOGY")
else:
    print("[X]    (1) POLY_CHAIN block not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 2: reorder POLY_MATS so chart legend reads in branch order
#   PTA, PSF (staple), POY, DTY (filament main), FDY (parallel)
# ─────────────────────────────────────────────────────────────────────────────
OLD_POLY_MATS = """const POLY_MATS = [
  // PI-1.5: PTA added (upstream trigger of polyester chain).
  { key: 'pta',                    color: '#22c1c3',  label: 'PTA' },  // PI-1.5 closeout: teal, distinct from DTY purple
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
];"""

NEW_POLY_MATS = """const POLY_MATS = [
  // PI-1.5: PTA added (upstream trigger of polyester chain).
  // PI-1.5b: order now reflects branch structure, not the false linear chain.
  //   PTA -> PSF (staple) -> POY -> DTY (filament main) -> FDY (parallel)
  { key: 'pta',                    color: '#22c1c3',  label: 'PTA' },
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
];"""

if "PI-1.5b: order now reflects branch structure" in src:
    print("[skip] (2) POLY_MATS already reordered")
elif OLD_POLY_MATS in src:
    src = src.replace(OLD_POLY_MATS, NEW_POLY_MATS)
    print("[OK]   (2) POLY_MATS reordered to branch order")
else:
    print("[X]    (2) POLY_MATS block not found in expected form (was PI-1.5 patch applied?)")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 3: rewrite _renderChainFlow to draw the branched layout.
#
# We replace the entire function body. The previous body is identifiable by
# its opening signature plus the chain-separator construction.
# ─────────────────────────────────────────────────────────────────────────────
OLD_RENDER_CHAIN = """function _renderChainFlow(data) {
  const el = document.getElementById('chain-flow-polyester');
  if (!el) return;

  let html = '';
  POLY_CHAIN.forEach((node, idx) => {
    const d       = data[node.key];
    const latest  = d?.latest;
    const price   = latest?.price_usd != null ? `$${Math.round(latest.price_usd).toLocaleString('en')}` : '—';
    const c7      = latest?.change_7d;
    const c7Html  = c7 != null
      ? `<div class="chain-node-change ${c7 > 0 ? 'stat-up' : c7 < 0 ? 'stat-down' : ''}">${c7 > 0 ? '+' : ''}${c7.toFixed(1)}%</div>`
      : '<div class="chain-node-change" style="color:var(--muted)">—</div>';
    const tier    = latest?.confidence_tier;
    const mom     = _momentumArrow(latest?.momentum_score);
    const tierHtml = _tierBadge(tier);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;
    // PI-1.5: sigma (7d volatility) moved here from poly-metric-cards.
    const vol     = latest?.volatility_7d;
    const volHtml = vol != null
      ? `<span class="chain-vol" style="font-size:11px; color:var(--muted); margin-left:6px">σ ${vol.toFixed(1)}</span>`
      : '';

    let divHtml = '';
    if (idx > 0) {
      const leftKey    = POLY_CHAIN[idx - 1].key;
      const upstreamOf = CHAIN_UPSTREAM[node.key];
      const div        = latest?.divergence_score;
      const showDiv    = div != null && Math.abs(div) >= 3.0 && upstreamOf === leftKey;
      divHtml = showDiv
        ? `<span class="divergence-badge">&#9889; ${div.toFixed(1)}%</span>`
        : '';
    }

    if (idx > 0) {
      html += `<div class="chain-separator"><span class="chain-arrow-icon">&#8594;</span>${divHtml}</div>`;
    }
    html += `
      <div class="chain-node" style="border-top: 2px solid ${node.color}">
        <div class="chain-node-name">${node.label}</div>
        <div class="chain-node-price">${price}</div>
        ${c7Html}
        <div class="chain-node-footer">${tierHtml}${momHtml}${volHtml}</div>
      </div>`;
  });

  el.innerHTML = html;
}"""

NEW_RENDER_CHAIN = '''function _renderChainFlow(data) {
  // PI-1.5b: branched topology rendering.
  //
  //                ┌── PSF                  (staple branch)
  // PTA ──────────┤
  //                └── POY ─── DTY          (filament branch)
  //                     │
  //                     └── FDY             (parallel filament)
  //
  const el = document.getElementById('chain-flow-polyester');
  if (!el) return;

  // Render a single chain-node card. Same HTML structure as before so
  // existing CSS (chain-node, chain-node-name, etc.) keeps working.
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

  // Divergence badge between two adjacent nodes (used between PTA and PSF,
  // PTA and POY, POY and DTY, PTA and FDY).
  const renderDivBadge = (childKey, expectedUpstreamKey) => {
    const latest = data[childKey]?.latest;
    const upstreamOf = CHAIN_UPSTREAM[childKey];
    const div = latest?.divergence_score;
    if (div == null || Math.abs(div) < 3.0 || upstreamOf !== expectedUpstreamKey) return '';
    return `<span class="divergence-badge">&#9889; ${div.toFixed(1)}%</span>`;
  };

  const T = POLY_TOPOLOGY;

  // Build the branched layout. CSS grid (see .chain-branched in style.v5.css)
  // places PTA on the left and the two branches stacked on the right.
  const html = `
    <div class="chain-branched">
      <div class="chain-root">
        ${renderNode(T.root)}
      </div>

      <div class="chain-branches">

        <div class="chain-branch chain-branch-staple">
          <div class="chain-branch-label">${T.branches.staple.label}</div>
          <div class="chain-branch-flow">
            <div class="chain-connector chain-connector-h">
              <span class="chain-arrow-icon">&#8594;</span>
              ${renderDivBadge(T.branches.staple.nodes[0].key, T.root.key)}
            </div>
            ${T.branches.staple.nodes.map(renderNode).join('<div class="chain-connector chain-connector-h"><span class="chain-arrow-icon">&#8594;</span></div>')}
          </div>
        </div>

        <div class="chain-branch chain-branch-filament">
          <div class="chain-branch-label">${T.branches.filament.label}</div>
          <div class="chain-branch-flow">
            <div class="chain-connector chain-connector-h">
              <span class="chain-arrow-icon">&#8594;</span>
              ${renderDivBadge(T.branches.filament.main[0].key, T.root.key)}
            </div>
            ${renderNode(T.branches.filament.main[0])}
            <div class="chain-connector chain-connector-h">
              <span class="chain-arrow-icon">&#8594;</span>
              ${renderDivBadge(T.branches.filament.main[1].key, T.branches.filament.main[0].key)}
            </div>
            ${renderNode(T.branches.filament.main[1])}
          </div>

          <div class="chain-parallel">
            <div class="chain-branch-label chain-branch-label-sub">${T.branches.filament.parallel.label}</div>
            <div class="chain-parallel-flow">
              <div class="chain-connector chain-connector-v">
                <span class="chain-arrow-icon">&#8595;</span>
                ${renderDivBadge(T.branches.filament.parallel.nodes[0].key, T.root.key)}
              </div>
              ${T.branches.filament.parallel.nodes.map(renderNode).join('')}
            </div>
          </div>
        </div>

      </div>
    </div>`;

  el.innerHTML = html;
}'''

if "PI-1.5b: branched topology rendering" in src:
    print("[skip] (3) _renderChainFlow already branched")
elif OLD_RENDER_CHAIN in src:
    src = src.replace(OLD_RENDER_CHAIN, NEW_RENDER_CHAIN)
    print("[OK]   (3) _renderChainFlow rewritten with branched layout")
else:
    print("[X]    (3) _renderChainFlow body did not match expected form")
    sys.exit(1)

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Change 4: HTML title update
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

OLD_TITLE = '<span class="price-block-title">Polyester Zinciri &#8212; PTA &#8594; PSF &#8594; FDY &#8594; POY &#8594; DTY</span>'
NEW_TITLE = '<span class="price-block-title">Polyester Chain &#8212; Staple &amp; Filament</span>'

# Try multiple plausible encodings of the dash/arrows in the existing HTML.
title_replaced = False
for old in [
    OLD_TITLE,
    '<span class="price-block-title">Polyester Zinciri — PTA → PSF → FDY → POY → DTY</span>',
    '<span class="price-block-title">Polyester Zinciri &mdash; PTA &rarr; PSF &rarr; FDY &rarr; POY &rarr; DTY</span>',
]:
    if old in html:
        html = html.replace(old, NEW_TITLE)
        title_replaced = True
        break

if "Polyester Chain &#8212; Staple &amp; Filament" in html or "Polyester Chain — Staple & Filament" in html:
    print("[skip] (4) section title already updated")
elif title_replaced:
    print("[OK]   (4) section title -> 'Polyester Chain — Staple & Filament'")
else:
    print("[!]    (4) section title not found in expected form; please update line ~157 manually")

# ─────────────────────────────────────────────────────────────────────────────
# Change 5: bump cache busters on JS + CSS
# ─────────────────────────────────────────────────────────────────────────────
ts = int(time.time())

m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]   (5a) app.v5.js cache buster -> {ts}")

m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]   (5b) style.v5.css cache buster -> {ts}")

INDEX.write_text(html, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Change 6: append CSS for the branched layout
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

NEW_CSS = """

/* ── PI-1.5b: branched polyester chain topology ───────────────────────────── */
.chain-branched {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 18px;
  align-items: center;
  padding: 8px 4px;
}
.chain-root {
  display: flex;
  align-items: center;
}
.chain-branches {
  display: grid;
  grid-template-rows: auto auto;
  gap: 16px;
}
.chain-branch {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chain-branch-label {
  font-size: 11px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--muted, #8a92a3);
  padding-left: 4px;
}
.chain-branch-label-sub {
  font-size: 10px;
  opacity: 0.85;
}
.chain-branch-flow {
  display: flex;
  align-items: center;
  gap: 4px;
}
.chain-parallel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
  margin-left: 56px;
}
.chain-parallel-flow {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.chain-connector {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted, #8a92a3);
}
.chain-connector-h {
  flex-direction: row;
}
.chain-connector-v {
  flex-direction: column;
}
.chain-connector-v .chain-arrow-icon {
  transform: rotate(0deg);
  font-size: 14px;
  line-height: 1;
}
"""

if "/* ── PI-1.5b: branched polyester chain topology" in css_src:
    print("[skip] (6) CSS for branched layout already present")
else:
    CSS.write_text(css_src.rstrip() + NEW_CSS, encoding="utf-8")
    print("[OK]   (6) CSS for branched layout appended")

print()
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
print()
print("Expected layout:")
print()
print("                  ┌── PSF                  (Staple branch)")
print("   PTA ──────────┤")
print("                  └── POY ──→ DTY          (Filament branch)")
print("                       │")
print("                       └── FDY             (Parallel filament)")
print()
print("Section title now reads: 'Polyester Chain — Staple & Filament'")
print("Chart unchanged: 5 lines in branch-order legend (PTA, PSF, POY, DTY, FDY)")
