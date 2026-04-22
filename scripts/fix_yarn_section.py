"""
Rebuild app.v5.js: keep everything BEFORE the old Yarn Intelligence section,
replace from there onwards with content of scripts/new_yarn_and_rest.js.
"""

import pathlib

APP_JS = pathlib.Path("dashboard/static/app.v5.js")
NEW_CONTENT = pathlib.Path("scripts/new_yarn_and_rest.js")

original = APP_JS.read_text(encoding="utf-8")
new_content = NEW_CONTENT.read_text(encoding="utf-8")

# Find where the Yarn Intelligence section begins.
# Try several possible markers.
candidates = [
    "/* \u2500\u2500 Yarn Intelligence",   # box-drawing dashes
    "/* -- Yarn Intelligence",              # plain dashes
    "async function loadYarnIntelligence",  # function declaration
]

cut_idx = -1
for marker in candidates:
    idx = original.find(marker)
    if idx != -1:
        cut_idx = idx
        print(f"Found cut point via marker: {marker!r}")
        break

if cut_idx == -1:
    raise SystemExit("ERROR: Could not find Yarn Intelligence section in app.v5.js")

# If we matched on the function name, back up to the comment line above if possible.
if not original[cut_idx:cut_idx+10].startswith("/*"):
    prev_newline = original.rfind("\n", 0, cut_idx)
    if prev_newline > 0:
        line_before_start = original.rfind("\n", 0, prev_newline) + 1
        line_before = original[line_before_start:prev_newline]
        if line_before.strip().startswith("/*"):
            cut_idx = line_before_start

kept = original[:cut_idx].rstrip()
result = kept + "\n\n" + new_content.lstrip()

APP_JS.write_text(result, encoding="utf-8")

print(f"Kept characters: {len(kept)}")
print(f"New content characters: {len(new_content)}")
print(f"Final file characters: {len(result)}")
print(f"Final line count: {result.count(chr(10)) + 1}")
print("DONE")