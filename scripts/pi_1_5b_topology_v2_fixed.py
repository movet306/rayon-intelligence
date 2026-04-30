"""
pi_1_5b_topology_v2_fixed.py - Reliable string-based replacement.

Replaces the v1 PI-1.5b _renderChainFlow function body with a v2 grouped-card
layout. Uses exact start and end markers from the v1 body so we don't need
a JS brace parser.

Also handles the section title fix and the cache busters that the
previous attempt should have applied.

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

V2_MARKER = "// PI-1.5b v2: grouped-card layout"

# ─────────────────────────────────────────────────────────────────────────────
# (1) Replace _renderChainFlow function body with v2 grouped-card layout.
# Find from the v1 function header up to the closing `}` of v1 body.
# ─────────────────────────────────────────────────────────────────────────────

V1_START = "function _renderChainFlow(data) {\n  // PI-1.5b: branched topology rendering."

# v1 body ends with these two lines as the last lines of the function:
#       el.innerHTML = html;
#     }
V1_END   = "\n  el.innerHTML = html;\n}\n"

NEW_FN = '''function _renderChainFlow(data) {
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
'''

if V2_MARKER in src:
    print("[skip] (1) _renderChainFlow already at v2 grouped layout")
else:
    start_idx = src.find(V1_START)
    if start_idx == -1:
        print("[X]    (1) v1 PI-1.5b function start marker not found")
        sys.exit(1)
    end_idx = src.find(V1_END, start_idx)
    if end_idx == -1:
        print("[X]    (1) v1 PI-1.5b function end marker not found")
        sys.exit(1)
    end_idx += len(V1_END)
    src = src[:start_idx] + NEW_FN + src[end_idx:]
    APPJS.write_text(src, encoding="utf-8")
    print("[OK]   (1) _renderChainFlow replaced with v2 grouped-card layout")

# ─────────────────────────────────────────────────────────────────────────────
# (2) CSS: replace v1 chain-branched block with v2 grouped block
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

V1_CSS_HEADER = "/* ── PI-1.5b: branched polyester chain topology"
V2_CSS_HEADER = "/* ── PI-1.5b v2: grouped-card polyester chain topology"

V2_CSS_BLOCK = """

/* ── PI-1.5b v2: grouped-card polyester chain topology ───────────────────── */
.chain-grouped {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 6px 4px 2px;
}
.chain-grouped-root {
  display: flex;
  justify-content: stretch;
}
.chain-grouped-root .chain-node {
  flex: 1 1 auto;
  min-width: 0;
}
.chain-grouped-arrow {
  text-align: center;
  font-size: 16px;
  color: var(--muted, #8a92a3);
  line-height: 1;
}
.chain-grouped-branches {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}
.chain-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 6px;
}
.chain-group-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--muted, #8a92a3);
  padding: 2px 0 4px;
}
.chain-group-flow {
  display: flex;
  align-items: stretch;
  gap: 6px;
}
.chain-group-flow > .chain-node {
  flex: 1 1 0;
  min-width: 0;
}
.chain-group-arrow {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--muted, #8a92a3);
}
"""

if V2_CSS_HEADER in css_src:
    print("[skip] (2) v2 grouped-layout CSS already present")
else:
    if V1_CSS_HEADER in css_src:
        cut = css_src.index(V1_CSS_HEADER)
        css_src = css_src[:cut].rstrip()
        print("[OK]   (2a) v1 PI-1.5b CSS block removed")
    css_src = css_src.rstrip() + V2_CSS_BLOCK
    CSS.write_text(css_src, encoding="utf-8")
    print("[OK]   (2b) v2 grouped-layout CSS appended")

# ─────────────────────────────────────────────────────────────────────────────
# (3) Section title — handle the literal-character version we now know is in
# the file (from screenshot: "Polyester Zinciri — PTA → PSF → FDY → POY → DTY")
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

NEW_TITLE = '<span class="price-block-title">Polyester Chain &#8212; Staple &amp; Filament</span>'

if "Polyester Chain &#8212; Staple &amp; Filament" in html or "Polyester Chain — Staple & Filament" in html:
    print("[skip] (3) section title already updated")
else:
    candidates = [
        '<span class="price-block-title">Polyester Zinciri &#8212; PTA &#8594; PSF &#8594; FDY &#8594; POY &#8594; DTY</span>',
        '<span class="price-block-title">Polyester Zinciri — PTA → PSF → FDY → POY → DTY</span>',
        '<span class="price-block-title">Polyester Zinciri &mdash; PTA &rarr; PSF &rarr; FDY &rarr; POY &rarr; DTY</span>',
    ]
    title_replaced = False
    for old in candidates:
        if old in html:
            html = html.replace(old, NEW_TITLE)
            title_replaced = True
            break
    if not title_replaced:
        # Regex fallback
        m = re.search(
            r'<span class="price-block-title">[^<]*Polyester Zinciri[^<]*</span>',
            html,
        )
        if m:
            html = html[:m.start()] + NEW_TITLE + html[m.end():]
            title_replaced = True
    if title_replaced:
        print("[OK]   (3) section title updated")
    else:
        print("[!]    (3) section title not found; please update line ~157 manually")

# ─────────────────────────────────────────────────────────────────────────────
# (4) Cache busters
# ─────────────────────────────────────────────────────────────────────────────
ts = int(time.time())
m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]   (4a) app.v5.js cache buster -> {ts}")
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]   (4b) style.v5.css cache buster -> {ts}")

INDEX.write_text(html, encoding="utf-8")

print()
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
