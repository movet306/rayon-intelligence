"""
pi_1_5b_topology_v2.py - Layout direction change for PI-1.5b.

Reaction to first attempt: technical correctness improved but UI got worse.
The connector-heavy branched layout was sparse and fragmented (PSF too high,
FDY too far below, floating spread badges, vertical arrows looking detached).

This patch replaces that with a compact grouped-card layout:

  ┌──────────────────────────────────────┐
  │  PTA  $1,005  +4.5%  σ 113.8         │   upstream root (full width)
  └──────────────────────────────────────┘
       │
       ▼
  ┌──────────┐  ┌─────────────────────┐  ┌──────────┐
  │ STAPLE   │  │ FILAMENT            │  │ FDY      │
  │  PSF     │  │  POY  →  DTY        │  │  ref     │
  │  $1,230  │  │  $1,281    $1,462   │  │  $1,343  │
  │  +2.8%   │  │  -1.5%     -2.7%    │  │  -1.6%   │
  └──────────┘  └─────────────────────┘  └──────────┘

Changes vs the first PI-1.5b patch:
  - Group cards instead of free connectors. Each group has a small label
    ('Staple', 'Filament', 'FDY reference') and contains its node card(s).
  - PTA spans the full width on top, single arrow down, then three groups
    side by side. No more vertical FDY column or stretched PSF row.
  - Floating spread badges (the +6.0% / +6.1% chips) removed for now.
    They were ambiguous in this layout. Can come back in a clearer form
    inside PI-1.4 (cluster cards + tooltips) if still useful.
  - Branch labels shortened: "Staple branch" → "Staple", "Parallel
    filament" → "FDY reference".
  - Vertical real estate reduced: the topology block no longer steals
    space from the chart below.

Also fixes:
  - The HTML section title that the previous patch failed to update
    (the actual HTML uses literal "—" and "→", not numeric entities).

Idempotent. Reverses cleanly: revert _renderChainFlow + the new CSS group.
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
# Replace _renderChainFlow body (the v1 PI-1.5b version) with the v2 grouped
# layout.
# ─────────────────────────────────────────────────────────────────────────────
# v1 marker — what's currently in the file after the first patch:
V1_MARKER = "// PI-1.5b: branched topology rendering."
# v2 marker — what we'll replace it with:
V2_MARKER = "// PI-1.5b v2: grouped-card layout"

# We don't try to do a single str-replace of the whole long v1 body. Instead
# we slice out _renderChainFlow by locating its `function _renderChainFlow(`
# header and its matching closing brace, then write the v2 body in its place.
def replace_function(source: str, fn_name: str, new_body: str) -> str:
    """
    Replace `function fn_name(...) { ... }` in `source` with `new_body`.
    Tracks brace depth to find the closing `}`. Returns the modified source.
    Raises if the function is not found.
    """
    sig = f"function {fn_name}("
    start = source.find(sig)
    if start == -1:
        raise ValueError(f"function {fn_name} not found")
    # Find the opening brace.
    open_idx = source.find("{", start)
    if open_idx == -1:
        raise ValueError(f"opening brace for {fn_name} not found")
    depth = 1
    i = open_idx + 1
    in_str = None  # quote char if inside string, else None
    in_line_comment = False
    in_block_comment = False
    in_template = False
    while i < len(source) and depth > 0:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        # Handle comments first
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if in_template:
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                in_template = False
            elif ch == "$" and nxt == "{":
                # Template expression: bump depth as if it were a brace.
                depth += 1
                i += 2
                continue
            i += 1
            continue
        # Not in any string/comment.
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "'" or ch == '"':
            in_str = ch
            i += 1
            continue
        if ch == "`":
            in_template = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return source[:start] + new_body + source[end:]
        i += 1
    raise ValueError(f"closing brace for {fn_name} not found")


NEW_RENDER_CHAIN = '''function _renderChainFlow(data) {
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
}'''

if V2_MARKER in src:
    print("[skip] (1) _renderChainFlow already at v2 grouped layout")
else:
    if V1_MARKER not in src:
        print("[X]    (1) v1 PI-1.5b layout marker missing; cannot reliably replace")
        sys.exit(1)
    try:
        src = replace_function(src, "_renderChainFlow", NEW_RENDER_CHAIN)
    except ValueError as e:
        print(f"[X]    (1) {e}")
        sys.exit(1)
    print("[OK]   (1) _renderChainFlow replaced with grouped-card layout")

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Replace v1 CSS block with v2 CSS for the grouped layout
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
  /* PTA spans full available width. Use a node card slightly stretched. */
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
    # Try to remove the v1 CSS block first (everything from its header to end of
    # file, since it was appended). Walk forward and chop at start of the v1
    # block so we can replace it cleanly.
    if V1_CSS_HEADER in css_src:
        cut = css_src.index(V1_CSS_HEADER)
        css_src = css_src[:cut].rstrip()
        print("[OK]   (2a) v1 PI-1.5b CSS block removed")
    css_src = css_src.rstrip() + V2_CSS_BLOCK
    CSS.write_text(css_src, encoding="utf-8")
    print("[OK]   (2b) v2 grouped-layout CSS appended")

# ─────────────────────────────────────────────────────────────────────────────
# Now actually fix the section title — the v1 patch failed because the
# encoding in HTML was different. Try the literal-character version now.
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

NEW_TITLE = '<span class="price-block-title">Polyester Chain &#8212; Staple &amp; Filament</span>'

title_replaced = False
if "Polyester Chain &#8212; Staple &amp; Filament" in html or "Polyester Chain — Staple & Filament" in html:
    print("[skip] (3) section title already updated")
else:
    # Try every plausible encoding of the original linear title.
    candidates = [
        '<span class="price-block-title">Polyester Zinciri &#8212; PTA &#8594; PSF &#8594; FDY &#8594; POY &#8594; DTY</span>',
        '<span class="price-block-title">Polyester Zinciri — PTA → PSF → FDY → POY → DTY</span>',
        '<span class="price-block-title">Polyester Zinciri &mdash; PTA &rarr; PSF &rarr; FDY &rarr; POY &rarr; DTY</span>',
    ]
    for old in candidates:
        if old in html:
            html = html.replace(old, NEW_TITLE)
            title_replaced = True
            break
    if title_replaced:
        print("[OK]   (3) section title updated")
    else:
        # Last resort: regex on the title span itself.
        m = re.search(
            r'<span class="price-block-title">[^<]*Polyester[^<]*</span>',
            html,
        )
        if m:
            html = html[:m.start()] + NEW_TITLE + html[m.end():]
            print("[OK]   (3) section title updated via regex fallback")
        else:
            print("[!]    (3) could not locate section title; please update line ~157 manually")

# ─────────────────────────────────────────────────────────────────────────────
# Bump cache busters
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
print()
print("Expected: PTA full-width on top, then three groups side by side:")
print("  Staple (PSF)  |  Filament (POY -> DTY)  |  FDY reference (FDY)")
print("Section title: 'Polyester Chain — Staple & Filament'")
