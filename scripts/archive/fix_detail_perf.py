"""
Fix detail endpoint TRIM mismatch.

Problem:
  In counterparty_detail() the cp_filter uses:
      vergi_numarasi IS NOT NULL AND TRIM(vergi_numarasi) NOT IN ('', '0', '0.0')
      AND TRIM(vergi_numarasi) = %s
  with cp_param = h["vergi_numarasi"] which comes from dim_counterparty_mv as
  e.g. 'REDACTED_TAX_ID.0'. The TRIM only strips whitespace, not '.0', so the
  comparison NEVER matches → 0 rows returned for every counterparty → endpoint
  appears to "work" but produces empty data, taking 25s round-trip overhead.

Fix:
  Use raw equality. The MV stores vergi_numarasi exactly as it is in the fact
  tables, so direct equality matches without any transformation.
  Same fix for the unverified branch with cari_hesap_aciklamasi.

Backup: dashboard/server.py.bak_perf_fix
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
text = SERVER.read_text(encoding="utf-8")

bak = SERVER.with_suffix(".py.bak_perf_fix")
if not bak.exists():
    bak.write_text(text, encoding="utf-8")
    print(f"Backup: {bak}")

# Old verified branch
OLD_VERIFIED = '''        cp_filter = "vergi_numarasi IS NOT NULL AND TRIM(vergi_numarasi) NOT IN ('', '0', '0.0') AND TRIM(vergi_numarasi) = %s"
        cp_param = h["vergi_numarasi"]'''

NEW_VERIFIED = '''        # vergi_numarasi stored as-is (e.g. 'REDACTED_TAX_ID.0') — direct equality
        # matches the index idx_fact_purch_vn_date / idx_fact_sales_vn_date.
        cp_filter = "vergi_numarasi = %s"
        cp_param = h["vergi_numarasi"]'''

# Old unverified branch
OLD_UNVERIFIED = '''        cp_filter = """(vergi_numarasi IS NULL OR TRIM(vergi_numarasi) IN ('', '0', '0.0'))
                       AND TRIM(cari_hesap_aciklamasi) = %s"""
        # display_name is the latest spelling; for unverified we use it directly
        cp_param = h["display_name"]'''

NEW_UNVERIFIED = '''        # Unverified: tax id missing/zero — match by raw display name
        # Index idx_fact_purch_cariname_date / idx_fact_sales_cariname_date.
        cp_filter = """(vergi_numarasi IS NULL OR vergi_numarasi IN ('', '0', '0.0'))
                       AND cari_hesap_aciklamasi = %s"""
        cp_param = h["display_name"]'''

# Apply
patches_made = 0

if OLD_VERIFIED in text:
    text = text.replace(OLD_VERIFIED, NEW_VERIFIED, 1)
    patches_made += 1
    print("  ✓ verified branch fixed")
else:
    print("  ⏭  verified branch not found (already patched?)")

if OLD_UNVERIFIED in text:
    text = text.replace(OLD_UNVERIFIED, NEW_UNVERIFIED, 1)
    patches_made += 1
    print("  ✓ unverified branch fixed")
else:
    print("  ⏭  unverified branch not found (already patched?)")

if patches_made > 0:
    SERVER.write_text(text, encoding="utf-8")
    print(f"\nFile written. {patches_made} patches applied.")
else:
    print("\nNo changes made.")

print()
print("Restart uvicorn to load the new code:")
print("  Ctrl+C in uvicorn terminal, then:")
print("  python -m uvicorn dashboard.server:app --port 8000")
