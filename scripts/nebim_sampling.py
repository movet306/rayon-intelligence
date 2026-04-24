"""
M1.1 - Nebim classification sampling.

Reads the Nebim Excel file (ALIŞ/SATIŞ), applies the v2 classification
rules, and produces two outputs for manual review:

  1) SAMPLING_REVIEW.xlsx  — 20 random rows per bucket for visual inspection
  2) SAMPLING_STATS.txt    — per-bucket statistics for quick sanity check

Usage:
    python scripts/nebim_sampling.py <path_to_nebim_excel>

If no path given, defaults to C:\\Projects\\rayon-intelligence\\data\\ALIŞ_SATIŞ_22042026.xlsx
"""
import sys
import os
import re
import random
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CLASSIFICATION LOGIC (copied from cloud version, kept inline for portability)
# ---------------------------------------------------------------------------

def _normalize(series):
    return series.fillna("").astype(str).str.upper().str.strip()


def _unit_group(unit_series):
    u = _normalize(unit_series)
    return np.select(
        [
            u.isin(["KG", "KGM", "TON", "KGS"]),
            u.isin(["MTR", "MT", "M"]),
            u.isin(["AD", "ADT", "ADET"]),
            u.isin(["LT", "LTR", "LITRE"]),
            u.eq("M3"),
            u.eq("KWH"),
        ],
        ["weight", "length", "count", "volume_lt", "volume_m3", "energy_kwh"],
        default="other",
    )


BUCKET_RELEVANCE = {
    "raw_material_yarn":            (True,  True),
    "raw_material_chemical":        (True,  True),
    "raw_material_dye":             (True,  True),
    "raw_material_greige_fabric":   (True,  True),
    "outsourced_processing":        (False, True),
    "utilities":                    (False, True),
    "maintenance_factory":          (False, True),
    "packaging":                    (False, True),
    "factory_overhead":             (False, True),
    "logistics_distribution":       (False, True),
    "selling_distribution":         (False, True),
    "admin_gna":                    (False, False),
    "professional_services":        (False, False),
    "tax_nondeductible":            (False, False),
    "core_product_sales":           (True,  False),
    "outsourced_service_revenue":   (True,  False),
    "sales_return_contra":          (True,  False),
    "scrap_sales":                  (False, False),
    "fx_gain_loss":                 (False, False),
    "misc_noncore_sales":           (False, False),
    "other_noncore_income":         (False, False),
    "adjustments_noncore":          (False, False),
    "non_core_trading":             (False, False),
    "anomalous_review":             (None,  None),
}


def classify_alis_vec(df):
    code = df["Hesap Kodu"].fillna("").astype(str).str.strip()
    desc = _normalize(df["Hesap Açıklaması"])
    unit = df["Birim Cinsi (1)"]
    p3 = code.str.extract(r"^(\d{3})", expand=False).fillna("")
    p6 = code.str.replace(" ", "", regex=False).str[:6]
    n = len(df)

    out = pd.DataFrame({
        "account_prefix_3": p3,
        "business_bucket": np.full(n, "anomalous_review", dtype=object),
        "clean_product_type": np.full(n, None, dtype=object),
        "clean_unit_group": _unit_group(unit),
        "classification_reason": np.full(n, "Default fallback.", dtype=object),
        "review_flag": np.ones(n, dtype=bool),
        "confidence_level": np.full(n, "low", dtype=object),
    }, index=df.index)

    # 600 in ALIŞ = anomalous
    m = p3.eq("600")
    out.loc[m, "business_bucket"] = "anomalous_review"
    out.loc[m, "review_flag"] = True
    out.loc[m, "classification_reason"] = "Revenue 600-series on ALIŞ side (likely return)."

    # 150 inventory/material
    m150 = p3.eq("150")
    out.loc[m150, "review_flag"] = False
    out.loc[m150, "confidence_level"] = "medium"

    m_yarn = m150 & (p6.str.startswith("15006") | desc.str.contains(r"\bİPLİK\b|\bYARN\b", regex=True, na=False))
    out.loc[m_yarn, "business_bucket"] = "raw_material_yarn"
    out.loc[m_yarn, "confidence_level"] = "high"
    out.loc[m_yarn, "classification_reason"] = "150-06 + yarn keyword."
    out.loc[m_yarn & desc.str.contains("POLYESTER", na=False), "clean_product_type"] = "polyester_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bPAMUK\b|\bCOTTON\b", regex=True, na=False), "clean_product_type"] = "cotton_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bNAYLON\b|\bNYLON\b", regex=True, na=False), "clean_product_type"] = "nylon_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bELASTAN\b|\bLYCRA\b|\bSPANDEX\b", regex=True, na=False), "clean_product_type"] = "elastane_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bKARIŞIM\b|\bBLEND\b", regex=True, na=False), "clean_product_type"] = "blend_yarn"

    m_chem = m150 & (p6.str.startswith("15004") | desc.str.contains("KİMYASAL", na=False)) & ~m_yarn
    out.loc[m_chem, "business_bucket"] = "raw_material_chemical"
    out.loc[m_chem, "clean_product_type"] = "chemical"
    out.loc[m_chem, "confidence_level"] = "high"
    out.loc[m_chem, "classification_reason"] = "150-04 chemical."

    m_dye = m150 & (p6.str.startswith("15005") | desc.str.contains(r"\bBOYA\b|\bBOYALAR\b|DYE", regex=True, na=False)) & ~m_yarn & ~m_chem
    out.loc[m_dye, "business_bucket"] = "raw_material_dye"
    out.loc[m_dye, "clean_product_type"] = "dye"
    out.loc[m_dye, "confidence_level"] = "high"
    out.loc[m_dye, "classification_reason"] = "150-05 dye."

    m_greige = m150 & (p6.str.startswith("15010") | desc.str.contains(r"\bHAM\b", regex=True, na=False)) & ~m_yarn & ~m_chem & ~m_dye
    out.loc[m_greige, "business_bucket"] = "raw_material_greige_fabric"
    out.loc[m_greige, "confidence_level"] = "high"
    out.loc[m_greige, "classification_reason"] = "150-10 greige / HAM."

    m_fuel = m150 & (p6.str.startswith("15007") | desc.str.contains(r"KÖMÜR|FINDIK KABUĞU|FUEL", regex=True, na=False)) & ~m_yarn & ~m_chem & ~m_dye & ~m_greige
    out.loc[m_fuel, "business_bucket"] = "utilities"
    out.loc[m_fuel, "clean_product_type"] = "solid_fuel"
    out.loc[m_fuel, "confidence_level"] = "high"
    out.loc[m_fuel, "classification_reason"] = "Solid fuel for boiler."

    m_150_fb = m150 & ~m_yarn & ~m_chem & ~m_dye & ~m_greige & ~m_fuel
    out.loc[m_150_fb, "business_bucket"] = "anomalous_review"
    out.loc[m_150_fb, "review_flag"] = True
    out.loc[m_150_fb, "confidence_level"] = "low"
    out.loc[m_150_fb, "classification_reason"] = "150-prefix but no sub-match."

    # 153, 159 balance-sheet
    m_bs = p3.isin(["153", "159"])
    out.loc[m_bs, "business_bucket"] = "anomalous_review"
    out.loc[m_bs, "review_flag"] = True
    out.loc[m_bs, "confidence_level"] = "low"
    out.loc[m_bs, "classification_reason"] = "Balance-sheet-like."

    # 730 production cost
    m730 = p3.eq("730")
    out.loc[m730, "review_flag"] = False
    out.loc[m730, "confidence_level"] = "medium"

    m_fason = m730 & desc.str.contains(r"\bFASON\b", regex=True, na=False)
    out.loc[m_fason, "business_bucket"] = "outsourced_processing"
    out.loc[m_fason, "confidence_level"] = "high"
    out.loc[m_fason, "classification_reason"] = "730 + FASON."

    m_util = m730 & desc.str.contains(r"\bELEKTRİK\b|\bDOĞALGAZ\b|\bDOGALGAZ\b|\bSU\b|\bBUHAR\b|\bGAZ\b", regex=True, na=False) & ~m_fason
    out.loc[m_util, "business_bucket"] = "utilities"
    out.loc[m_util, "confidence_level"] = "high"
    out.loc[m_util, "classification_reason"] = "730 + utility."

    m_maint = m730 & desc.str.contains(r"\bBAKIM\b|\bONARIM\b|MAINTENANCE", regex=True, na=False) & ~m_fason & ~m_util
    out.loc[m_maint, "business_bucket"] = "maintenance_factory"
    out.loc[m_maint, "confidence_level"] = "high"
    out.loc[m_maint, "classification_reason"] = "730 + maintenance."

    m_pack = m730 & desc.str.contains(r"\bAMBALAJ\b|PACKAGING", regex=True, na=False) & ~m_fason & ~m_util & ~m_maint
    out.loc[m_pack, "business_bucket"] = "packaging"
    out.loc[m_pack, "confidence_level"] = "high"
    out.loc[m_pack, "classification_reason"] = "730 + packaging."

    overhead_kws = ["YEMEK", "TAŞIMA", "GÜVENLİK", "PERSONEL", "DEMİRBAŞ",
                    "İŞ GÜVENLİĞİ", "ÇEVRE", "ATIK", "ODA AİDAT", "ŞABLON", "DANIŞMAN"]
    m_overhead = m730 & desc.str.contains("|".join(overhead_kws), regex=True, na=False) & ~m_fason & ~m_util & ~m_maint & ~m_pack
    out.loc[m_overhead, "business_bucket"] = "factory_overhead"
    out.loc[m_overhead, "confidence_level"] = "medium"
    out.loc[m_overhead, "classification_reason"] = "730 + overhead keyword."

    m_730_fb = m730 & ~m_fason & ~m_util & ~m_maint & ~m_pack & ~m_overhead
    out.loc[m_730_fb, "business_bucket"] = "factory_overhead"
    out.loc[m_730_fb, "review_flag"] = True
    out.loc[m_730_fb, "confidence_level"] = "low"
    out.loc[m_730_fb, "classification_reason"] = "730 fallback."

    # 760
    m760 = p3.eq("760")
    out.loc[m760, "review_flag"] = False
    m_log = m760 & desc.str.contains(r"NAKLİYE|KARGO|LOJİSTİK|GÜMRÜK|IHRACAT", regex=True, na=False)
    out.loc[m_log, "business_bucket"] = "logistics_distribution"
    out.loc[m_log, "confidence_level"] = "high"
    out.loc[m_log, "classification_reason"] = "760 + logistics."
    m_760_fb = m760 & ~m_log
    out.loc[m_760_fb, "business_bucket"] = "selling_distribution"
    out.loc[m_760_fb, "confidence_level"] = "medium"
    out.loc[m_760_fb, "classification_reason"] = "760 generic."

    # 770
    m770 = p3.eq("770")
    out.loc[m770, "review_flag"] = False
    m_prof = m770 & desc.str.contains(r"DANIŞMAN|AVUKAT|MALİ MÜŞAVİR|DENETİM|NOTER|CONSULT", regex=True, na=False)
    out.loc[m_prof, "business_bucket"] = "professional_services"
    out.loc[m_prof, "confidence_level"] = "high"
    out.loc[m_prof, "classification_reason"] = "770 + professional services."
    m_770_fb = m770 & ~m_prof
    out.loc[m_770_fb, "business_bucket"] = "admin_gna"
    out.loc[m_770_fb, "confidence_level"] = "medium"
    out.loc[m_770_fb, "classification_reason"] = "770 general admin."

    # 689 non-deductible
    m689 = p3.eq("689")
    out.loc[m689, "business_bucket"] = "tax_nondeductible"
    out.loc[m689, "review_flag"] = False
    out.loc[m689, "confidence_level"] = "high"
    out.loc[m689, "classification_reason"] = "689 non-deductible."

    # 656
    m656 = p3.eq("656")
    out.loc[m656, "business_bucket"] = "fx_gain_loss"
    out.loc[m656, "review_flag"] = False
    out.loc[m656, "confidence_level"] = "high"
    out.loc[m656, "classification_reason"] = "656 non-op."

    # 611, 612
    m61x = p3.isin(["611", "612"])
    out.loc[m61x, "business_bucket"] = "anomalous_review"
    out.loc[m61x, "review_flag"] = True
    out.loc[m61x, "confidence_level"] = "low"
    out.loc[m61x, "classification_reason"] = "611/612 in ALIŞ — review."

    return out


def classify_satis_vec(df):
    code = df["Hesap Kodu"].fillna("").astype(str).str.strip()
    desc = _normalize(df["Hesap Açıklaması"])
    unit = df["Birim Cinsi (1)"]
    p3 = code.str.extract(r"^(\d{3})", expand=False).fillna("")
    p6 = code.str.replace(" ", "", regex=False).str[:6]
    n = len(df)

    out = pd.DataFrame({
        "account_prefix_3": p3,
        "business_bucket": np.full(n, "anomalous_review", dtype=object),
        "clean_product_type": np.full(n, None, dtype=object),
        "clean_unit_group": _unit_group(unit),
        "classification_reason": np.full(n, "Default fallback.", dtype=object),
        "review_flag": np.ones(n, dtype=bool),
        "confidence_level": np.full(n, "low", dtype=object),
    }, index=df.index)

    # 600 revenue
    m600 = p3.eq("600")
    out.loc[m600, "review_flag"] = False
    out.loc[m600, "confidence_level"] = "high"

    m_yarn_resale = m600 & (p6.str.startswith("60013") | (desc.str.contains("İPLİK", na=False) & desc.str.contains("TİCARİ", na=False)))
    out.loc[m_yarn_resale, "business_bucket"] = "anomalous_review"
    out.loc[m_yarn_resale, "review_flag"] = True
    out.loc[m_yarn_resale, "clean_product_type"] = "yarn_resale"
    out.loc[m_yarn_resale, "classification_reason"] = "Yarn resale — NOT core revenue (Rayon is fabric producer)."

    m_trading = m600 & desc.str.contains("TİCARİ MAL", na=False) & ~m_yarn_resale
    out.loc[m_trading, "business_bucket"] = "non_core_trading"
    out.loc[m_trading, "review_flag"] = True
    out.loc[m_trading, "classification_reason"] = "Trading goods resale."

    fason_p6 = p6.isin(["60003", "60018", "60022", "60023", "60024", "60025", "60030"])
    m_fason_sv = m600 & (desc.str.contains("FASON", na=False) | fason_p6) & ~m_yarn_resale & ~m_trading
    out.loc[m_fason_sv, "business_bucket"] = "outsourced_service_revenue"
    out.loc[m_fason_sv, "confidence_level"] = "high"
    out.loc[m_fason_sv, "classification_reason"] = "FASON service revenue."

    m_knit = m600 & p6.str.startswith("60002") & ~m_yarn_resale & ~m_trading & ~m_fason_sv
    out.loc[m_knit, "business_bucket"] = "core_product_sales"
    out.loc[m_knit, "clean_product_type"] = "knit_fabric"
    out.loc[m_knit, "classification_reason"] = "600-02 knit fabric."

    m_woven = m600 & p6.str.startswith("60061") & ~m_yarn_resale & ~m_trading & ~m_fason_sv & ~m_knit
    out.loc[m_woven, "business_bucket"] = "core_product_sales"
    out.loc[m_woven, "classification_reason"] = "600-61 woven fabric."
    out.loc[m_woven & desc.str.contains("POLYESTER", na=False), "clean_product_type"] = "polyester_woven"
    out.loc[m_woven & desc.str.contains("NAYLON", na=False), "clean_product_type"] = "nylon_woven"
    out.loc[m_woven & desc.str.contains("KARIŞIM", na=False), "clean_product_type"] = "blend_woven"
    out.loc[m_woven & desc.str.contains("PAMUK", na=False), "clean_product_type"] = "cotton_woven"

    m_600_other = m600 & ~m_yarn_resale & ~m_trading & ~m_fason_sv & ~m_knit & ~m_woven
    out.loc[m_600_other, "business_bucket"] = "anomalous_review"
    out.loc[m_600_other, "review_flag"] = True
    out.loc[m_600_other, "confidence_level"] = "low"
    out.loc[m_600_other, "classification_reason"] = "600-prefix no core match."

    # 601, 612
    m601 = p3.eq("601")
    out.loc[m601, "business_bucket"] = "sales_return_contra"
    out.loc[m601, "review_flag"] = False
    out.loc[m601, "confidence_level"] = "high"
    out.loc[m601, "classification_reason"] = "601 sales return."

    m612 = p3.eq("612")
    out.loc[m612, "business_bucket"] = "sales_return_contra"
    out.loc[m612, "review_flag"] = False
    out.loc[m612, "confidence_level"] = "medium"
    out.loc[m612, "classification_reason"] = "612 sales discount."

    # 602
    m602 = p3.eq("602")
    out.loc[m602, "review_flag"] = False

    m_scrap = m602 & desc.str.contains(r"\bHURDA\b|\bATIK\b|\bSCRAP\b", regex=True, na=False)
    out.loc[m_scrap, "business_bucket"] = "scrap_sales"
    out.loc[m_scrap, "confidence_level"] = "high"
    out.loc[m_scrap, "classification_reason"] = "602 scrap."

    m_pfark = m602 & desc.str.contains(r"FIYAT FARK|FARK FATURA", regex=True, na=False) & ~m_scrap
    out.loc[m_pfark, "business_bucket"] = "adjustments_noncore"
    out.loc[m_pfark, "confidence_level"] = "high"
    out.loc[m_pfark, "classification_reason"] = "602 price diff."

    m_claim = m602 & desc.str.contains(r"REKLAMASYON|\bHASAR\b|\bSİGORTA\b", regex=True, na=False) & ~m_scrap & ~m_pfark
    out.loc[m_claim, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_claim, "confidence_level"] = "high"
    out.loc[m_claim, "classification_reason"] = "602 claim/insurance."

    m_misc = m602 & desc.str.contains(r"DİĞER GELİR|\bÇEŞİTLİ\b", regex=True, na=False) & ~m_scrap & ~m_pfark & ~m_claim
    out.loc[m_misc, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_misc, "review_flag"] = True
    out.loc[m_misc, "confidence_level"] = "low"
    out.loc[m_misc, "classification_reason"] = "602 vague 'other income' — REVIEW."

    m_602_fb = m602 & ~m_scrap & ~m_pfark & ~m_claim & ~m_misc
    out.loc[m_602_fb, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_602_fb, "confidence_level"] = "medium"
    out.loc[m_602_fb, "classification_reason"] = "602 fallback."

    # 646 FX
    m646 = p3.eq("646")
    out.loc[m646, "business_bucket"] = "fx_gain_loss"
    out.loc[m646, "review_flag"] = False
    out.loc[m646, "confidence_level"] = "high"
    out.loc[m646, "classification_reason"] = "646 FX."

    # 679
    m679 = p3.eq("679")
    out.loc[m679, "business_bucket"] = "other_noncore_income"
    out.loc[m679, "review_flag"] = False
    out.loc[m679, "confidence_level"] = "high"
    out.loc[m679, "classification_reason"] = "679 other non-core."

    # balance/expense in SATIŞ
    bal_exp = p3.isin(["150", "152", "153", "253", "254", "255", "258", "730", "760", "770"])
    out.loc[bal_exp, "business_bucket"] = "anomalous_review"
    out.loc[bal_exp, "review_flag"] = True
    out.loc[bal_exp, "confidence_level"] = "low"
    out.loc[bal_exp, "classification_reason"] = "Balance/expense account in SATIŞ."

    # 656
    m656s = p3.eq("656")
    out.loc[m656s, "business_bucket"] = "other_noncore_income"
    out.loc[m656s, "review_flag"] = False
    out.loc[m656s, "confidence_level"] = "high"
    out.loc[m656s, "classification_reason"] = "656 non-op."

    return out


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    default_path = r"C:\Projects\rayon-intelligence\data\ALIŞ SATIŞ 22042026.xlsx"
    src = sys.argv[1] if len(sys.argv) > 1 else default_path

    if not os.path.exists(src):
        print(f"ERROR: File not found: {src}")
        print("Usage: python scripts/nebim_sampling.py <path_to_nebim_excel>")
        sys.exit(1)

    print(f"Loading: {src}")
    alis_raw = pd.read_excel(src, sheet_name="ALIŞ")
    satis_raw = pd.read_excel(src, sheet_name="SATIŞ")
    print(f"  ALIŞ : {len(alis_raw):,} rows")
    print(f"  SATIŞ: {len(satis_raw):,} rows")

    print("Classifying...")
    alis_cls = classify_alis_vec(alis_raw)
    satis_cls = classify_satis_vec(satis_raw)

    alis_clean = pd.concat([alis_raw.reset_index(drop=True), alis_cls.reset_index(drop=True)], axis=1)
    alis_clean.insert(0, "source_sheet", "ALIS")
    satis_clean = pd.concat([satis_raw.reset_index(drop=True), satis_cls.reset_index(drop=True)], axis=1)
    satis_clean.insert(0, "source_sheet", "SATIS")

    # Apply dual relevance
    for df in (alis_clean, satis_clean):
        df["is_core_business_relevant"] = df["business_bucket"].map(lambda b: BUCKET_RELEVANCE.get(b, (None, None))[0])
        df["is_cost_model_relevant"] = df["business_bucket"].map(lambda b: BUCKET_RELEVANCE.get(b, (None, None))[1])

    combined = pd.concat([alis_clean, satis_clean], ignore_index=True)

    # --- Stats
    out_dir = Path("outputs/sampling")
    out_dir.mkdir(parents=True, exist_ok=True)

    stats_path = out_dir / "SAMPLING_STATS.txt"
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("NEBIM SAMPLING STATS — per bucket\n")
        f.write("=" * 80 + "\n\n")

        for sheet in ("ALIS", "SATIS"):
            sub = combined[combined["source_sheet"] == sheet]
            f.write(f"\n### {sheet} — {len(sub):,} rows total ###\n")
            g = sub.groupby("business_bucket").agg(
                rows=("Hesap Kodu", "size"),
                amount_tl=("Net Tutar (Y)", "sum"),
                unique_counterparties=("Cari Hesap Açıklaması", "nunique"),
                unique_accounts=("Hesap Kodu", "nunique"),
            ).sort_values("amount_tl", ascending=False)
            for b, r in g.iterrows():
                f.write(f"  {b:30s}  rows={int(r['rows']):6,}  "
                        f"amt={r['amount_tl']:>15,.0f} TL  "
                        f"counterparties={int(r['unique_counterparties']):4d}  "
                        f"distinct_accounts={int(r['unique_accounts']):3d}\n")
    print(f"Wrote: {stats_path}")

    # --- Sampling workbook
    sampling_path = out_dir / "SAMPLING_REVIEW.xlsx"
    print(f"Building {sampling_path} ...")

    cols_to_show = [
        "source_sheet", "Fatura Tarihi", "Cari Hesap Açıklaması",
        "Hesap Kodu", "Hesap Açıklaması", "Birim Cinsi (1)", "Miktar",
        "Net Tutar (Y)", "Net Tutar (D)", "Para Birimi (D)",
        "business_bucket", "clean_product_type",
        "is_core_business_relevant", "is_cost_model_relevant",
        "confidence_level", "review_flag", "classification_reason",
    ]

    random.seed(42)

    with pd.ExcelWriter(sampling_path, engine="openpyxl") as writer:
        # TOC sheet
        buckets_sorted = combined.groupby("business_bucket").size().sort_values(ascending=False).reset_index()
        buckets_sorted.columns = ["business_bucket", "total_rows"]
        buckets_sorted.to_excel(writer, sheet_name="_INDEX", index=False)

        for bucket in buckets_sorted["business_bucket"]:
            sub = combined[combined["business_bucket"] == bucket]
            n = min(20, len(sub))
            if len(sub) > n:
                sample = sub.sample(n=n, random_state=42)
            else:
                sample = sub
            sample = sample[cols_to_show].sort_values(["source_sheet", "Hesap Kodu"])
            # Excel sheet name limit: 31 chars, no special chars
            safe = re.sub(r"[^\w]", "_", bucket)[:28]
            sample.to_excel(writer, sheet_name=safe, index=False)

    print(f"Wrote: {sampling_path}")
    print("\nDone. Review both files before deciding classification v3.")


if __name__ == "__main__":
    main()