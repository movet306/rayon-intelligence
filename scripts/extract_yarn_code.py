"""
app.v5.js ve style.v5.css dosyalarindan yarn ile ilgili bolumleri cikar.
"""
import re

def extract_js_yarn_sections(path):
    code = open(path, encoding="utf-8").read()
    print(f"\n{'='*70}\nJS FILE: {path} ({len(code)} chars)\n{'='*70}")

    # Yarn ile ilgili fonksiyonlari bul
    # Pattern: "yarn", "Yarn" iceren fonksiyon tanimlari
    patterns = [
        r'(async\s+function\s+\w*[Yy]arn\w*[^{]*\{)',
        r'(function\s+\w*[Yy]arn\w*[^{]*\{)',
        r'(const\s+\w*[Yy]arn\w*\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{)',
        r'(\w*[Yy]arn\w*\s*:\s*(?:async\s*)?(?:function)?\s*\([^)]*\)\s*(?:=>)?\s*\{)',
    ]

    found_positions = []
    for pat in patterns:
        for m in re.finditer(pat, code):
            found_positions.append((m.start(), m.group(0)[:80]))

    found_positions.sort()
    print(f"\nFound {len(found_positions)} yarn-related entry points:\n")
    for pos, snippet in found_positions:
        line_num = code[:pos].count('\n') + 1
        print(f"  Line ~{line_num}: {snippet}")

    # Simdi her matchi genisleterek bracket-matched fonksiyonu cikar
    print(f"\n{'─'*70}\nFULL YARN-RELATED BLOCKS:\n{'─'*70}")
    seen_starts = set()
    for pos, _ in found_positions:
        if pos in seen_starts:
            continue
        seen_starts.add(pos)
        # Find matching closing brace
        depth = 0
        i = pos
        started = False
        while i < len(code):
            if code[i] == '{':
                depth += 1
                started = True
            elif code[i] == '}':
                depth -= 1
                if started and depth == 0:
                    end = i + 1
                    break
            i += 1
        else:
            end = min(pos + 3000, len(code))

        block = code[pos:end]
        line_num = code[:pos].count('\n') + 1
        print(f"\n--- Block starting line {line_num} ---")
        print(block)
        print()

    # Bonus: "yarn" gecen diger tum satirlari (fonksiyon disinda) bul
    print(f"\n{'─'*70}\nALL LINES MENTIONING 'yarn' (case-insensitive):\n{'─'*70}")
    for i, line in enumerate(code.split('\n'), 1):
        if re.search(r'yarn', line, re.IGNORECASE):
            print(f"  L{i}: {line.rstrip()}")


def extract_css_yarn_sections(path):
    code = open(path, encoding="utf-8").read()
    print(f"\n{'='*70}\nCSS FILE: {path} ({len(code)} chars)\n{'='*70}")

    # Yarn ile ilgili CSS bloklarini bul
    # Pattern: selector with "yarn" -> { ... }
    matches = re.finditer(
        r'([^{}]*\byarn\b[^{}]*\{[^}]*\})',
        code,
        re.IGNORECASE
    )

    blocks = list(matches)
    print(f"\nFound {len(blocks)} yarn-related CSS blocks:\n")
    for m in blocks:
        line_num = code[:m.start()].count('\n') + 1
        print(f"--- CSS block at line {line_num} ---")
        print(m.group(0))
        print()

    # Bonus: chip, badge, expandable gecen selectorler
    print(f"\n{'─'*70}\nRELATED UTILITY CLASSES (chip, badge, pill):\n{'─'*70}")
    for m in re.finditer(r'(\.[\w-]*(?:chip|badge|pill|expand|collapse)[\w-]*\s*\{[^}]*\})', code, re.IGNORECASE):
        line_num = code[:m.start()].count('\n') + 1
        print(f"  L{line_num}: {m.group(0)[:200]}")


extract_js_yarn_sections("dashboard/static/app.v5.js")
extract_css_yarn_sections("dashboard/static/style.v5.css")