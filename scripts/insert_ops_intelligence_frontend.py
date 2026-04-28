"""
Frontend patch for Operations Intelligence (M2).

Performs three operations:
  1. Replaces the entire <section id="section-internal">...</section> in
     dashboard/static/index.html with the new layout.
  2. Replaces the body of `async function loadInternal()` in
     dashboard/static/app.v5.js with the new ops loader and appends new
     render functions / helpers at the bottom (BEFORE the closing brace
     of the file if any, but app.v5.js is plain script so we just append).
  3. Appends Operations Intelligence styles to dashboard/static/style.v5.css.

All operations are idempotent: if the marker is already present, that step
is skipped.

Usage:
    python scripts/insert_ops_intelligence_frontend.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML  = ROOT / "dashboard" / "static" / "index.html"
JS    = ROOT / "dashboard" / "static" / "app.v5.js"
CSS   = ROOT / "dashboard" / "static" / "style.v5.css"

HTML_BLOCK = ROOT / "scripts" / "section_internal_replacement.html"
JS_BLOCK   = ROOT / "scripts" / "operations_intelligence_block.js"
CSS_BLOCK  = ROOT / "scripts" / "operations_intelligence.css"

JS_MARKER  = "Operations Intelligence (M2)"
CSS_MARKER = "Operations Intelligence (M2)"
HTML_MARKER = 'id="sub-ops-overview"'


def patch_html():
    if not HTML.exists():
        print(f"ERROR: {HTML} not found.")
        return False
    text = HTML.read_text(encoding="utf-8")
    if HTML_MARKER in text:
        print("HTML: marker already present, skipping.")
        return True

    # Find the section
    pat = re.compile(
        r'<section id="section-internal" class="section">.*?</section>',
        re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        print("ERROR: <section id='section-internal'> not found in index.html.")
        return False

    new_block = HTML_BLOCK.read_text(encoding="utf-8").rstrip()

    # Backup
    HTML.with_suffix(".html.bak_m2").write_text(text, encoding="utf-8")
    new_text = text[:m.start()] + new_block + text[m.end():]
    HTML.write_text(new_text, encoding="utf-8")
    print(f"HTML patched. ({m.end() - m.start()} bytes removed, "
          f"{len(new_block)} bytes inserted)")
    return True


def patch_js():
    if not JS.exists():
        print(f"ERROR: {JS} not found.")
        return False
    text = JS.read_text(encoding="utf-8")
    if JS_MARKER in text:
        print("JS: marker already present, skipping.")
        return True

    # Replace `let _internalData = null;` with `let _internalData = null; let _opsData = null;`
    # but the new block declares its own _opsData, so we just neutralize the old declaration.
    # Strategy: comment out the old loadInternal function body (preserve the rest of the file
    # for any references), and append the new block.
    #
    # Actually simplest: find `async function loadInternal() {` and the matching `}`, replace
    # with a stub that calls the new loader, then append the new block.
    #
    # Even simpler: just append the new block. The new `async function loadInternal()` will
    # SHADOW the old one (last declaration wins in JS for `function` declarations? No — async
    # function expressions don't hoist that way). Instead, rename old: regex-rename
    # `async function loadInternal()` → `async function _loadInternal_legacy()`, then append
    # new block which provides the canonical loadInternal.

    old_decl = "async function loadInternal() {"
    if old_decl not in text:
        print(f"ERROR: could not find `{old_decl}` in app.v5.js.")
        return False

    text2 = text.replace(old_decl, "async function _loadInternal_legacy() {", 1)

    new_block = JS_BLOCK.read_text(encoding="utf-8").rstrip()

    # Backup
    JS.with_suffix(".js.bak_m2").write_text(text, encoding="utf-8")
    new_text = text2.rstrip() + "\n\n\n" + new_block + "\n"
    JS.write_text(new_text, encoding="utf-8")
    print(f"JS patched. ({len(new_block)} bytes appended; "
          f"old loadInternal renamed to _loadInternal_legacy)")
    return True


def patch_css():
    if not CSS.exists():
        print(f"ERROR: {CSS} not found.")
        return False
    text = CSS.read_text(encoding="utf-8")
    if CSS_MARKER in text:
        print("CSS: marker already present, skipping.")
        return True

    new_block = CSS_BLOCK.read_text(encoding="utf-8").rstrip()

    # Backup
    CSS.with_suffix(".css.bak_m2").write_text(text, encoding="utf-8")
    new_text = text.rstrip() + "\n\n\n" + new_block + "\n"
    CSS.write_text(new_text, encoding="utf-8")
    print(f"CSS patched. ({len(new_block)} bytes appended)")
    return True


def main():
    ok_html = patch_html()
    ok_js   = patch_js()
    ok_css  = patch_css()

    print()
    print("=" * 60)
    print(f"HTML: {'OK' if ok_html else 'FAILED'}")
    print(f"JS:   {'OK' if ok_js else 'FAILED'}")
    print(f"CSS:  {'OK' if ok_css else 'FAILED'}")
    print("=" * 60)

    if not (ok_html and ok_js and ok_css):
        print()
        print("Some patches failed. Check messages above.")
        print("Backups available:")
        print("  dashboard/static/index.html.bak_m2")
        print("  dashboard/static/app.v5.js.bak_m2")
        print("  dashboard/static/style.v5.css.bak_m2")
        sys.exit(1)

    print()
    print("All three patched. Restart uvicorn (or rely on --reload for backend) and reload browser.")
    print("To revert any single file: copy .bak_m2 back over the original.")


if __name__ == "__main__":
    main()
