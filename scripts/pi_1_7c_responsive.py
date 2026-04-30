"""
pi_1_7c_responsive.py - Make _renderMultiLine charts responsive.

Problem: nylon panel's chart-wrap is correctly sized via CSS flex (794px tall
verified in DevTools), but the inner Plotly SVG chart doesn't fill it.
Result: visible empty space below the chart in the nylon panel.

Cause: Plotly.newPlot is called without responsive config. The chart fixes
its dimensions at render time and ignores subsequent container resizes.

Fix: pass `{ responsive: true }` as the config (4th) argument to
Plotly.newPlot inside _renderMultiLine. Plotly attaches a ResizeObserver
and the chart now grows/shrinks with its container.

Idempotent.
"""
from pathlib import Path
import re
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

if "{ responsive: true }" in src or "responsive:true" in src.replace(" ", ""):
    print("[skip] responsive config already present in _renderMultiLine")
else:
    # Find the Plotly.newPlot call inside _renderMultiLine. Locate the
    # closing ');' of the call and inject ', { responsive: true }' before it.
    # The call is: Plotly.newPlot(elId, traces, { ... layout ... });
    # We find the start, then walk to the matching ');' that closes the call.
    needle = "Plotly.newPlot(elId, traces,"
    idx = src.find(needle)
    if idx == -1:
        print("[X] could not locate Plotly.newPlot inside _renderMultiLine")
        raise SystemExit(1)
    # Skip past the opening (
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
                depth += 1
                i += 2
                continue
            i += 1
            continue
        if ch == "'" or ch == '"':
            in_str = ch
            i += 1
            continue
        if ch == "`":
            in_template = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # Inject before this closing paren
                src = src[:i] + ", { responsive: true }" + src[i:]
                break
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    APPJS.write_text(src, encoding="utf-8")
    print("[OK] Plotly.newPlot in _renderMultiLine: { responsive: true } added")

# Cache buster, UTF-8 no BOM (avoid prior BOM mishap)
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
html = re.sub(r'app\.v5\.js\?v=\d+', f'app.v5.js?v={ts}', html)
html = re.sub(r'style\.v5\.css\?v=\d+', f'style.v5.css?v={ts}', html)

import io
with io.open(INDEX, "w", encoding="utf-8", newline="") as f:
    f.write(html)
print(f"[OK] cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print("Expected: nylon chart now fills the panel; cotton sub-charts unchanged.")
