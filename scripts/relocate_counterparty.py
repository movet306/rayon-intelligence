"""
Relocate Counterparty Explorer:
  - Remove from sidebar
  - Add as 5th sub-tab inside Operations Intelligence
  - Re-wire JS to trigger ceInit on sub-tab click

Backups: .bak_m21_relocate suffix.
"""
from pathlib import Path
import re

INDEX = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m21_relocate")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# Step 1: Remove sidebar nav item
# ─────────────────────────────────────────────────────────────────────────
print("[1/4] Removing sidebar nav item...")
text = INDEX.read_text(encoding="utf-8")
backup(INDEX)

sidebar_pattern = re.compile(
    r'\n\s*<div class="nav-item"[^>]*data-section="counterparty"[^>]*>.*?</div>',
    re.DOTALL
)
new_text, n = sidebar_pattern.subn("", text)
if n > 0:
    print(f"  ✓ removed {n} sidebar nav item(s)")
else:
    print(f"  ⏭  no sidebar nav item found (already removed?)")
text = new_text


# ─────────────────────────────────────────────────────────────────────────
# Step 2: Add 5th sub-tab to Operations Intelligence sub-nav
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/4] Adding sub-tab button to Operations Intelligence...")

NEW_SUBTAB = '      <div class="sub-nav-btn" data-sub="ops-counterparty">👥 Counterparty</div>\n'

# Insert after the Revenue Reality sub-nav-btn
revenue_btn_pattern = re.compile(
    r'(\s*<div class="sub-nav-btn"[^>]*data-sub="ops-revenue"[^>]*>[^<]*</div>\s*\n)'
)
match = revenue_btn_pattern.search(text)
if not match:
    print("  ❌ could not find ops-revenue sub-nav-btn anchor")
    raise SystemExit(1)

if 'data-sub="ops-counterparty"' in text:
    print("  ⏭  ops-counterparty sub-tab already present")
else:
    text = text[:match.end()] + NEW_SUBTAB + text[match.end():]
    print(f"  ✓ added Counterparty sub-tab after Revenue Reality")


# ─────────────────────────────────────────────────────────────────────────
# Step 3: Move <section id="section-counterparty"> INTO Operations Intelligence
#   - Change ID from "section-counterparty" to "ops-counterparty"
#   - Move it INSIDE the section-internal block (right before its </section>)
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/4] Relocating Counterparty section into Operations Intelligence...")

# Extract the existing section-counterparty block
ce_section_pattern = re.compile(
    r'<!-- === COUNTERPARTY EXPLORER \(M2\.1\) === -->.*?<!-- === END COUNTERPARTY EXPLORER \(M2\.1\) === -->',
    re.DOTALL
)
ce_match = ce_section_pattern.search(text)
if not ce_match:
    print("  ⚠️  Counterparty section block not found — was it removed earlier?")
    print("     Will skip relocation. Check the file manually.")
else:
    ce_block = ce_match.group(0)

    # Re-tag the section id and class for sub-tab switching
    # Original was: <section id="section-counterparty" class="section" style="display:none;">
    # We want it to behave like other ops sub-sections: <div class="ops-section" id="ops-counterparty" style="display:none;">
    relocated_block = ce_block

    # Replace the wrapper element
    relocated_block = re.sub(
        r'<section id="section-counterparty"[^>]*>',
        '<div class="ops-section" id="ops-counterparty" style="display:none;">',
        relocated_block,
        count=1,
    )
    # Replace the matching closing </section> (the LAST one in the block, before END marker)
    # The block ends with </section>\n<!-- === END...
    relocated_block = re.sub(
        r'</section>\s*(<!-- === END COUNTERPARTY EXPLORER)',
        r'</div>\n\1',
        relocated_block,
        count=1,
    )

    # Remove from old location
    text = text.replace(ce_block, "", 1)

    # Find the closing </section> of section-internal and insert before it
    # section-internal pattern: <section id="section-internal" ... > ... </section>
    internal_close_pattern = re.compile(
        r'(<section id="section-internal"[^>]*>.*?)(\s*</section>)',
        re.DOTALL
    )
    internal_match = internal_close_pattern.search(text)
    if not internal_match:
        print("  ❌ could not find section-internal closing tag")
        raise SystemExit(1)

    text = (
        text[:internal_match.end(1)]
        + "\n\n"
        + relocated_block
        + text[internal_match.end(1):]
    )
    print(f"  ✓ Counterparty section relocated and re-tagged as ops-counterparty")

INDEX.write_text(text, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# Step 4: Wire ceInit() to sub-tab click in JS
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/4] Wiring JS to fire ceInit on sub-tab click...")

js_text = APP_JS.read_text(encoding="utf-8")
backup(APP_JS)

# Add a hook: when ops-counterparty sub-tab activates, run ceInit (once) and ceFetchList
# Insert this hook into the existing sub-nav-btn click handler (around line 120)

WIRE_MARKER = "// === COUNTERPARTY SUB-TAB WIRING (M2.1 relocate) ==="

if WIRE_MARKER in js_text:
    print("  ⏭  JS wiring already present")
else:
    # Append a delegated click handler at the end of the file (won't conflict)
    wiring = f'''

{WIRE_MARKER}
// Initialize Counterparty Explorer when its sub-tab becomes active.
document.addEventListener('DOMContentLoaded', () => {{
  document.querySelectorAll('[data-sub="ops-counterparty"]').forEach(btn => {{
    btn.addEventListener('click', () => {{
      // Defer slightly to let the section become visible first
      setTimeout(() => {{
        if (typeof ceInit === 'function' && !window.CE?._initialized) {{
          ceInit();
          if (window.CE) window.CE._initialized = true;
          if (typeof ceFetchList === 'function') ceFetchList();
        }}
      }}, 50);
    }});
  }});
}});
// === END COUNTERPARTY SUB-TAB WIRING ===
'''
    js_text = js_text.rstrip() + "\n" + wiring
    APP_JS.write_text(js_text, encoding="utf-8")
    print(f"  ✓ wired sub-tab click handler")


print()
print("=" * 60)
print("Counterparty Explorer relocated to Operations Intelligence.")
print("=" * 60)
print()
print("Next:")
print("  1. uvicorn auto-reloads HTML/JS — just hard-refresh browser")
print("     (Ctrl+Shift+R) on http://localhost:8000")
print("  2. Click 'Operations Intelligence' in sidebar")
print("  3. Click '👥 Counterparty' sub-tab")
