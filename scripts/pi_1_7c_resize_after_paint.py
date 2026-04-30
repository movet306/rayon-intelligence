"""
pi_1_7c_resize_after_paint.py - Fix nylon chart shrinking on initial load.

Problem:
  On hard refresh, the nylon chart renders at Plotly's default ~450px height,
  even though chart-wrap is sized via flex to ~795px. Container size isn't
  finalized at the moment Plotly.newPlot runs, and 'responsive: true' alone
  only triggers on subsequent ResizeObserver events, not the initial paint.

Fix:
  After Plotly.newPlot completes, request a layout resize on the next
  animation frame. By then the browser has finalized the flex layout,
  and Plotly.Plots.resize() makes the chart fit its container.

Targets the inside of _renderMultiLine right after the Plotly.newPlot call.

Idempotent.
"""
from pathlib import Path
import re
import io
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

MARKER = "PI-1.7c: resize after paint"
if MARKER in src:
    print("[skip] resize-after-paint already added")
else:
    # Find the Plotly.newPlot call in _renderMultiLine. We expect:
    #   Plotly.newPlot(elId, traces, { ...layout... }, { responsive: true });
    # We want to add right after it (still inside _renderMultiLine):
    #   requestAnimationFrame(() => { try { Plotly.Plots.resize(elId); } catch {} });
    needle = "Plotly.newPlot(elId, traces,"
    idx = src.find(needle)
    if idx == -1:
        print("[X] Plotly.newPlot not found in _renderMultiLine")
        raise SystemExit(1)

    # Walk to the end of the call: matching ');'
    open_paren = src.find("(", idx)
    depth = 1
    i = open_paren + 1
    in_str = None
    in_template = False
    while i < len(src) and depth > 0:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < len(src) else ""
        if in_str:
            if ch == "\\":
                i += 2; continue
            if ch == in_str: in_str = None
            i += 1; continue
        if in_template:
            if ch == "\\":
                i += 2; continue
            if ch == "`":
                in_template = False
            elif ch == "$" and nxt == "{":
                depth += 1; i += 2; continue
            i += 1; continue
        if ch == "'" or ch == '"':
            in_str = ch; i += 1; continue
        if ch == "`":
            in_template = True; i += 1; continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # i is index of the closing ')'. The statement closes with
                # ');' so the semicolon is at i+1. Insert after that.
                # Look for the ';' after this position.
                end = i + 1
                if end < len(src) and src[end] == ";":
                    end += 1
                INSERT = (
                    "\n  // PI-1.7c: resize after paint — flex container height isn't\n"
                    "  // final at newPlot time on initial load. Plotly's responsive\n"
                    "  // observer fires later, but only on subsequent resizes. Force\n"
                    "  // an explicit resize on the next frame so the chart fills the\n"
                    "  // container immediately.\n"
                    "  requestAnimationFrame(() => {\n"
                    "    try { Plotly.Plots.resize(elId); } catch (e) { /* element may have unmounted */ }\n"
                    "  });"
                )
                src = src[:end] + INSERT + src[end:]
                break
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    APPJS.write_text(src, encoding="utf-8")
    print("[OK] _renderMultiLine: requestAnimationFrame resize added")

# Cache buster, UTF-8 no BOM
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
html = re.sub(r'app\.v5\.js\?v=\d+', f'app.v5.js?v={ts}', html)
html = re.sub(r'style\.v5\.css\?v=\d+', f'style.v5.css?v={ts}', html)
with io.open(INDEX, "w", encoding="utf-8", newline="") as f:
    f.write(html)
print(f"[OK] cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print("Expected: nylon chart fills its panel on first load (no shrinking).")
