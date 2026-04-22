"""index.html'den yarn section'u cikar (tam blok)."""
import re

code = open('dashboard/static/index.html', encoding='utf-8').read()

# section-yarn blogunu bul
m = re.search(r'<section id="section-yarn"', code)

if m:
    start = m.start()
    # Ic ice nested section olmadigini varsayip bir sonraki </section>'u al
    end_match = re.search(r'</section>', code[start:])
    end = start + end_match.end() if end_match else len(code)
    print(f"--- Found section-yarn at char {start}, length {end - start} ---\n")
    print(code[start:end])
else:
    # Alternatif: yarn-pressure-tbody ya da yarn-pressure-summary'yi iceren
    # en yakin section'u bul
    m2 = re.search(r'yarn-pressure-tbody', code)
    if m2:
        # Geriye dogru en yakin <section ... bul
        before = code[:m2.start()]
        section_start = before.rfind('<section')
        end_match = re.search(r'</section>', code[m2.start():])
        end = m2.start() + end_match.end() if end_match else len(code)
        print(f"--- Found via yarn-pressure-tbody, section starts at {section_start} ---\n")
        print(code[section_start:end])
    else:
        print("yarn section not found")