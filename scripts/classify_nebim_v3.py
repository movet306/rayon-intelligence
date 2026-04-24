"""
v3 classification rules for Rayon Nebim ALIŞ/SATIŞ data.

Reads raw Nebim Excel, applies v3 classification rules (post-sampling review),
and writes enriched pickles ready for DB load.

Usage:
    python scripts/classify_nebim_v3.py

Inputs:
    data/ALIŞ SATIŞ 22042026.xlsx

Outputs (in outputs/v3/):
    alis_clean_v3.pkl
    satis_clean_v3.pkl
    alis_raw.pkl
    satis_raw.pkl
    classification_summary.txt
"""
import sys
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================================
# HELPERS
# ============================================================================

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


def _counterparty_type(cari_series):
    d = _normalize(cari_series)
    company_pat = r"A\.Ş\.|\bAŞ\b|\bLTD\b|LİMİTED|TİCARET|SANAYİ|SAN\.|TİC\.|\bCO\.\b|\bINC\b|\bCORP\b|\bGMBH\b|\bS\.A\.\b|\bSRL\b|\bLLC\b"
    is_company = d.str.contains(company_pat, regex=True, na=False)
    return np.where(d.eq(""), "", np.where(is_company, "company", "other_or_individual"))


# ============================================================================
# BUCKET RELEVANCE MAP
# ============================================================================

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
    "customer_claims":              (True,  False),
    "scrap_sales":                  (False, False),
    "fx_gain_loss":                 (False, False),
    "misc_noncore_sales":           (False, False),
    "other_noncore_income":         (False, False),
    "adjustments_noncore":          (False, False),
    "non_core_trading":             (False, False),
    "leasing_financial":            (False, False),
    "capex_investment":             (False, False),
    "capex_disposal":               (False, False),
    "supplier_prepayments":         (None,  None),
    "anomalous_review":             (None,  None),
}


# ============================================================================
# ALIŞ classification
# ============================================================================

def classify_alis_v3(df):
    code = df["Hesap Kodu"].fillna("").astype(str).str.strip()
    desc = _normalize(df["Hesap Açıklaması"])
    unit = df["Birim Cinsi (1)"]
    p3 = code.str.extract(r"^(\d{3})", expand=False).fillna("")
    p6 = code.str.replace(" ", "", regex=False).str[:6]
    n = len(df)

    out = pd.DataFrame({
        "account_prefix_3": p3,
        "account_class_main": np.full(n, "UNCLASSIFIED", dtype=object),
        "account_class_sub": np.full(n, None, dtype=object),
        "business_bucket": np.full(n, "anomalous_review", dtype=object),
        "subtype": np.full(n, None, dtype=object),
        "project_use_case": np.full(n, "manual_review", dtype=object),
        "review_flag": np.ones(n, dtype=bool),
        "confidence_level": np.full(n, "low", dtype=object),
        "classification_reason": np.full(n, "Default fallback.", dtype=object),
        "clean_unit_group": _unit_group(unit),
        "clean_product_type": np.full(n, None, dtype=object),
        "is_prepayment": np.zeros(n, dtype=bool),
        "realized_in_procurement": np.full(n, None, dtype=object),
    }, index=df.index)

    # 600 in ALIŞ — customer returns
    m600 = p3.eq("600")
    out.loc[m600, "account_class_main"] = "CUSTOMER_RETURN"
    out.loc[m600, "business_bucket"] = "sales_return_contra"
    out.loc[m600, "subtype"] = "contra_revenue_return"
    out.loc[m600, "project_use_case"] = "core_sales_analysis"
    out.loc[m600, "review_flag"] = False
    out.loc[m600, "confidence_level"] = "high"
    out.loc[m600, "classification_reason"] = "Revenue 600-series on ALIŞ side = customer return invoice."

    # 611 Sales discounts
    m611 = p3.eq("611")
    out.loc[m611, "account_class_main"] = "SALES_DISCOUNT"
    out.loc[m611, "business_bucket"] = "sales_return_contra"
    out.loc[m611, "subtype"] = "contra_revenue_discount"
    out.loc[m611, "project_use_case"] = "core_sales_analysis"
    out.loc[m611, "review_flag"] = False
    out.loc[m611, "confidence_level"] = "high"
    out.loc[m611, "classification_reason"] = "611 sales discount (contra-revenue)."

    # 612 Customer claims
    m612 = p3.eq("612")
    out.loc[m612, "account_class_main"] = "CUSTOMER_CLAIM"
    out.loc[m612, "business_bucket"] = "customer_claims"
    out.loc[m612, "project_use_case"] = "core_sales_analysis"
    out.loc[m612, "review_flag"] = False
    out.loc[m612, "confidence_level"] = "high"
    out.loc[m612, "classification_reason"] = "612 reklamasyon giderleri."

    # 150 INVENTORY
    m150 = p3.eq("150")
    out.loc[m150, "account_class_main"] = "INVENTORY_MATERIAL"
    out.loc[m150, "review_flag"] = False
    out.loc[m150, "confidence_level"] = "medium"

    m_yarn = m150 & (p6.str.startswith("15006") | desc.str.contains(r"\bİPLİK\b|\bYARN\b", regex=True, na=False))
    out.loc[m_yarn, "account_class_sub"] = "yarn"
    out.loc[m_yarn, "business_bucket"] = "raw_material_yarn"
    out.loc[m_yarn, "project_use_case"] = "yarn_intelligence"
    out.loc[m_yarn, "confidence_level"] = "high"
    out.loc[m_yarn, "classification_reason"] = "150-06 + yarn keyword."
    out.loc[m_yarn & desc.str.contains("POLYESTER", na=False), "clean_product_type"] = "polyester_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bPAMUK\b|\bCOTTON\b", regex=True, na=False), "clean_product_type"] = "cotton_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bNAYLON\b|\bNYLON\b", regex=True, na=False), "clean_product_type"] = "nylon_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bELASTAN\b|\bLYCRA\b|\bSPANDEX\b", regex=True, na=False), "clean_product_type"] = "elastane_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bKARIŞIM\b|\bBLEND\b", regex=True, na=False), "clean_product_type"] = "blend_yarn"
    out.loc[m_yarn & desc.str.contains(r"\bVİSKON\b|\bVİSCOSE\b", regex=True, na=False), "clean_product_type"] = "viscose_yarn"

    m_chem = m150 & (p6.str.startswith("15004") | desc.str.contains("KİMYASAL", na=False)) & ~m_yarn
    out.loc[m_chem, "account_class_sub"] = "chemical"
    out.loc[m_chem, "business_bucket"] = "raw_material_chemical"
    out.loc[m_chem, "project_use_case"] = "chemical_dye_analysis"
    out.loc[m_chem, "confidence_level"] = "high"
    out.loc[m_chem, "clean_product_type"] = "chemical"
    out.loc[m_chem, "classification_reason"] = "150-04 chemical."

    m_dye = m150 & (p6.str.startswith("15005") | desc.str.contains(r"\bBOYA\b|\bBOYALAR\b|DYE", regex=True, na=False)) & ~m_yarn & ~m_chem
    out.loc[m_dye, "account_class_sub"] = "dye"
    out.loc[m_dye, "business_bucket"] = "raw_material_dye"
    out.loc[m_dye, "project_use_case"] = "chemical_dye_analysis"
    out.loc[m_dye, "confidence_level"] = "high"
    out.loc[m_dye, "clean_product_type"] = "dye"
    out.loc[m_dye, "classification_reason"] = "150-05 dye."

    m_greige = m150 & (p6.str.startswith("15010") | desc.str.contains(r"\bHAM\b", regex=True, na=False)) & ~m_yarn & ~m_chem & ~m_dye
    out.loc[m_greige, "account_class_sub"] = "greige_fabric"
    out.loc[m_greige, "business_bucket"] = "raw_material_greige_fabric"
    out.loc[m_greige, "project_use_case"] = "material_cost_model"
    out.loc[m_greige, "confidence_level"] = "high"
    out.loc[m_greige, "classification_reason"] = "150-10 greige / HAM."
    out.loc[m_greige & desc.str.contains("POLYESTER", na=False), "clean_product_type"] = "polyester_greige"
    out.loc[m_greige & desc.str.contains("NAYLON", na=False), "clean_product_type"] = "nylon_greige"
    out.loc[m_greige & desc.str.contains("PAMUK", na=False), "clean_product_type"] = "cotton_greige"
    out.loc[m_greige & desc.str.contains("KARIŞIM", na=False), "clean_product_type"] = "blend_greige"

    # 150-07 solid fuel
    m_fuel = m150 & p6.str.startswith("15007") & desc.str.contains(r"KÖMÜR|FINDIK KABUĞU|FUEL", regex=True, na=False) & ~m_yarn & ~m_chem & ~m_dye & ~m_greige
    out.loc[m_fuel, "account_class_sub"] = "fuel"
    out.loc[m_fuel, "business_bucket"] = "utilities"
    out.loc[m_fuel, "project_use_case"] = "production_cost_model"
    out.loc[m_fuel, "confidence_level"] = "high"
    out.loc[m_fuel, "clean_product_type"] = "solid_fuel"
    out.loc[m_fuel, "classification_reason"] = "Solid fuel for boiler."

    # 150-07 KEÇE/KERESTE → maintenance
    m_maint_mat = m150 & p6.str.startswith("15007") & desc.str.contains(r"KEÇE|KERESTE", regex=True, na=False)
    out.loc[m_maint_mat, "account_class_sub"] = "factory_supplies"
    out.loc[m_maint_mat, "business_bucket"] = "maintenance_factory"
    out.loc[m_maint_mat, "project_use_case"] = "production_cost_model"
    out.loc[m_maint_mat, "confidence_level"] = "high"
    out.loc[m_maint_mat, "classification_reason"] = "150-07 KEÇE/KERESTE → maintenance."

    # 150-07 VARAK → packaging
    m_varak = m150 & p6.str.startswith("15007") & desc.str.contains("VARAK", na=False)
    out.loc[m_varak, "account_class_sub"] = "packaging_supply"
    out.loc[m_varak, "business_bucket"] = "packaging"
    out.loc[m_varak, "project_use_case"] = "production_cost_model"
    out.loc[m_varak, "confidence_level"] = "high"
    out.loc[m_varak, "classification_reason"] = "150-07 VARAK → packaging consumable."

    m_150_fb = m150 & ~m_yarn & ~m_chem & ~m_dye & ~m_greige & ~m_fuel & ~m_maint_mat & ~m_varak
    out.loc[m_150_fb, "account_class_sub"] = "material_other"
    out.loc[m_150_fb, "business_bucket"] = "anomalous_review"
    out.loc[m_150_fb, "review_flag"] = True
    out.loc[m_150_fb, "confidence_level"] = "low"
    out.loc[m_150_fb, "classification_reason"] = "150-prefix but no sub-match."

    # 159 supplier prepayments
    m159 = p3.eq("159")
    out.loc[m159, "account_class_main"] = "SUPPLIER_PREPAYMENT"
    out.loc[m159, "business_bucket"] = "supplier_prepayments"
    out.loc[m159, "project_use_case"] = "manual_review"
    out.loc[m159, "review_flag"] = True
    out.loc[m159, "confidence_level"] = "medium"
    out.loc[m159, "is_prepayment"] = True
    out.loc[m159, "realized_in_procurement"] = "unknown"
    out.loc[m159, "classification_reason"] = "159 verilen avanslar — supplier prepayments."

    # 153
    m153 = p3.eq("153")
    out.loc[m153, "account_class_main"] = "INVENTORY_TRADE_GOODS"
    out.loc[m153, "business_bucket"] = "anomalous_review"
    out.loc[m153, "review_flag"] = True
    out.loc[m153, "confidence_level"] = "low"
    out.loc[m153, "classification_reason"] = "153 ticari mal stoğu."

    # 253, 254, 255, 258 CAPEX
    m_capex = p3.isin(["253", "254", "255", "258"])
    out.loc[m_capex, "account_class_main"] = "CAPEX"
    out.loc[m_capex, "business_bucket"] = "capex_investment"
    out.loc[m_capex, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_capex, "review_flag"] = False
    out.loc[m_capex, "confidence_level"] = "high"
    out.loc[m_capex, "classification_reason"] = "CAPEX investment."

    # 301 leasing
    m301 = p3.eq("301")
    out.loc[m301, "account_class_main"] = "LEASING"
    out.loc[m301, "business_bucket"] = "leasing_financial"
    out.loc[m301, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m301, "review_flag"] = False
    out.loc[m301, "confidence_level"] = "high"
    out.loc[m301, "classification_reason"] = "301 finansal kiralama."

    # 730 PRODUCTION COST
    m730 = p3.eq("730")
    out.loc[m730, "account_class_main"] = "PRODUCTION_COST"
    out.loc[m730, "review_flag"] = False
    out.loc[m730, "confidence_level"] = "medium"

    m_fason = m730 & desc.str.contains(r"\bFASON\b", regex=True, na=False)
    out.loc[m_fason, "account_class_sub"] = "outsourced_processing"
    out.loc[m_fason, "business_bucket"] = "outsourced_processing"
    out.loc[m_fason, "project_use_case"] = "outsourced_process_model"
    out.loc[m_fason, "confidence_level"] = "high"
    out.loc[m_fason, "classification_reason"] = "730 + FASON."
    for proc in ["BOYAMA", "DOKUMA", "TEKSTURE", "FIRÇA", "BASKI", "LAMİNASYON", "ÖRGÜ", "RAM", "SANFOR", "FIKSE", "PUNTOLAMA", "TRAŞ"]:
        m_p = m_fason & desc.str.contains(rf"\b{proc}\b", regex=True, na=False)
        out.loc[m_p, "clean_product_type"] = f"fason_{proc.lower()}"

    m_util = m730 & desc.str.contains(r"\bELEKTRİK\b|\bDOĞALGAZ\b|\bDOGALGAZ\b|\bSU\b|\bBUHAR\b|\bGAZ\b", regex=True, na=False) & ~m_fason
    out.loc[m_util, "account_class_sub"] = "utility"
    out.loc[m_util, "business_bucket"] = "utilities"
    out.loc[m_util, "project_use_case"] = "production_cost_model"
    out.loc[m_util, "confidence_level"] = "high"
    out.loc[m_util, "classification_reason"] = "730 + utility."
    out.loc[m_util & desc.str.contains("ELEKTRİK", na=False), "clean_product_type"] = "electricity"
    out.loc[m_util & desc.str.contains(r"DOĞALGAZ|DOGALGAZ|\bGAZ\b", regex=True, na=False), "clean_product_type"] = "natural_gas"

    m_maint = m730 & desc.str.contains(r"\bBAKIM\b|\bONARIM\b|MAINTENANCE", regex=True, na=False) & ~m_fason & ~m_util
    out.loc[m_maint, "account_class_sub"] = "maintenance"
    out.loc[m_maint, "business_bucket"] = "maintenance_factory"
    out.loc[m_maint, "project_use_case"] = "production_cost_model"
    out.loc[m_maint, "confidence_level"] = "high"
    out.loc[m_maint, "classification_reason"] = "730 + maintenance."

    m_pack = m730 & desc.str.contains(r"\bAMBALAJ\b|PACKAGING", regex=True, na=False) & ~m_fason & ~m_util & ~m_maint
    out.loc[m_pack, "account_class_sub"] = "packaging"
    out.loc[m_pack, "business_bucket"] = "packaging"
    out.loc[m_pack, "project_use_case"] = "production_cost_model"
    out.loc[m_pack, "confidence_level"] = "high"
    out.loc[m_pack, "classification_reason"] = "730 + packaging."

    overhead_kws = ["YEMEK", "TAŞIMA", "GÜVENLİK", "PERSONEL", "DEMİRBAŞ", "İŞ GÜVENLİĞİ", "ÇEVRE", "ATIK", "ODA AİDAT", "ŞABLON", "DANIŞMAN"]
    m_overhead = m730 & desc.str.contains("|".join(overhead_kws), regex=True, na=False) & ~m_fason & ~m_util & ~m_maint & ~m_pack
    out.loc[m_overhead, "account_class_sub"] = "factory_overhead"
    out.loc[m_overhead, "business_bucket"] = "factory_overhead"
    out.loc[m_overhead, "project_use_case"] = "production_cost_model"
    out.loc[m_overhead, "confidence_level"] = "medium"
    out.loc[m_overhead, "classification_reason"] = "730 + overhead."

    m_730_fb = m730 & ~m_fason & ~m_util & ~m_maint & ~m_pack & ~m_overhead
    out.loc[m_730_fb, "account_class_sub"] = "production_misc"
    out.loc[m_730_fb, "business_bucket"] = "factory_overhead"
    out.loc[m_730_fb, "project_use_case"] = "production_cost_model"
    out.loc[m_730_fb, "review_flag"] = True
    out.loc[m_730_fb, "confidence_level"] = "low"
    out.loc[m_730_fb, "classification_reason"] = "730 fallback."

    # 760
    m760 = p3.eq("760")
    out.loc[m760, "account_class_main"] = "SELLING_DISTRIBUTION"
    out.loc[m760, "review_flag"] = False
    m_log = m760 & desc.str.contains(r"NAKLİYE|KARGO|LOJİSTİK|GÜMRÜK|IHRACAT", regex=True, na=False)
    out.loc[m_log, "account_class_sub"] = "logistics"
    out.loc[m_log, "business_bucket"] = "logistics_distribution"
    out.loc[m_log, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_log, "confidence_level"] = "high"
    out.loc[m_log, "classification_reason"] = "760 + logistics."

    m_760_fb = m760 & ~m_log
    out.loc[m_760_fb, "account_class_sub"] = "selling_other"
    out.loc[m_760_fb, "business_bucket"] = "selling_distribution"
    out.loc[m_760_fb, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_760_fb, "confidence_level"] = "medium"
    out.loc[m_760_fb, "classification_reason"] = "760 generic."

    # 770
    m770 = p3.eq("770")
    out.loc[m770, "account_class_main"] = "GENERAL_ADMIN"
    out.loc[m770, "review_flag"] = False
    m_prof = m770 & desc.str.contains(r"DANIŞMAN|AVUKAT|MALİ MÜŞAVİR|DENETİM|NOTER|CONSULT", regex=True, na=False)
    out.loc[m_prof, "account_class_sub"] = "professional_services"
    out.loc[m_prof, "business_bucket"] = "professional_services"
    out.loc[m_prof, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_prof, "confidence_level"] = "high"
    out.loc[m_prof, "classification_reason"] = "770 + professional."

    m_770_fb = m770 & ~m_prof
    out.loc[m_770_fb, "account_class_sub"] = "admin_gna"
    out.loc[m_770_fb, "business_bucket"] = "admin_gna"
    out.loc[m_770_fb, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_770_fb, "confidence_level"] = "medium"
    out.loc[m_770_fb, "classification_reason"] = "770 general admin."

    # 689, 656, 646, 602, 679, 264 — minor tails
    m689 = p3.eq("689")
    out.loc[m689, "account_class_main"] = "NON_OPERATING"
    out.loc[m689, "business_bucket"] = "tax_nondeductible"
    out.loc[m689, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m689, "review_flag"] = False
    out.loc[m689, "confidence_level"] = "high"
    out.loc[m689, "classification_reason"] = "689 KKEG."

    for p, b in [("656", "fx_gain_loss"), ("646", "fx_gain_loss")]:
        m = p3.eq(p)
        out.loc[m, "business_bucket"] = b
        out.loc[m, "review_flag"] = False
        out.loc[m, "confidence_level"] = "high"
        out.loc[m, "classification_reason"] = f"{p} non-op / FX."

    m602a = p3.eq("602")
    out.loc[m602a, "business_bucket"] = "misc_noncore_sales"
    out.loc[m602a, "review_flag"] = False
    out.loc[m602a, "confidence_level"] = "low"
    out.loc[m602a, "classification_reason"] = "602 in ALIŞ (rare)."

    m679a = p3.eq("679")
    out.loc[m679a, "business_bucket"] = "other_noncore_income"
    out.loc[m679a, "review_flag"] = False
    out.loc[m679a, "classification_reason"] = "679 in ALIŞ."

    m264 = p3.eq("264")
    out.loc[m264, "business_bucket"] = "anomalous_review"
    out.loc[m264, "review_flag"] = True
    out.loc[m264, "classification_reason"] = "264 small — review."

    return out


# ============================================================================
# SATIŞ classification
# ============================================================================

def classify_satis_v3(df):
    code = df["Hesap Kodu"].fillna("").astype(str).str.strip()
    desc = _normalize(df["Hesap Açıklaması"])
    unit = df["Birim Cinsi (1)"]
    amt = df["Net Tutar (Y)"].fillna(0).astype(float)
    p3 = code.str.extract(r"^(\d{3})", expand=False).fillna("")
    p6 = code.str.replace(" ", "", regex=False).str[:6]
    n = len(df)

    out = pd.DataFrame({
        "account_prefix_3": p3,
        "account_class_main": np.full(n, "UNCLASSIFIED", dtype=object),
        "account_class_sub": np.full(n, None, dtype=object),
        "business_bucket": np.full(n, "anomalous_review", dtype=object),
        "subtype": np.full(n, None, dtype=object),
        "project_use_case": np.full(n, "manual_review", dtype=object),
        "review_flag": np.ones(n, dtype=bool),
        "confidence_level": np.full(n, "low", dtype=object),
        "classification_reason": np.full(n, "Default fallback.", dtype=object),
        "clean_unit_group": _unit_group(unit),
        "clean_product_type": np.full(n, None, dtype=object),
        "is_prepayment": np.zeros(n, dtype=bool),
        "realized_in_procurement": np.full(n, None, dtype=object),
    }, index=df.index)

    # 600 revenue
    m600 = p3.eq("600")
    out.loc[m600, "account_class_main"] = "REVENUE"
    out.loc[m600, "review_flag"] = False
    out.loc[m600, "confidence_level"] = "high"

    m_yarn_resale = m600 & (p6.str.startswith("60013") | (desc.str.contains("İPLİK", na=False) & desc.str.contains("TİCARİ", na=False)))
    out.loc[m_yarn_resale, "account_class_sub"] = "yarn_resale_noncore"
    out.loc[m_yarn_resale, "business_bucket"] = "anomalous_review"
    out.loc[m_yarn_resale, "subtype"] = "yarn_resale"
    out.loc[m_yarn_resale, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_yarn_resale, "review_flag"] = True
    out.loc[m_yarn_resale, "clean_product_type"] = "yarn_resale"
    out.loc[m_yarn_resale, "classification_reason"] = "Yarn resale — NOT core revenue."

    m_trading = m600 & desc.str.contains("TİCARİ MAL", na=False) & ~m_yarn_resale
    out.loc[m_trading, "account_class_sub"] = "trading_goods_noncore"
    out.loc[m_trading, "business_bucket"] = "non_core_trading"
    out.loc[m_trading, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_trading, "review_flag"] = False
    out.loc[m_trading, "classification_reason"] = "Trading goods resale."

    fason_p6 = p6.isin(["60003", "60018", "60022", "60023", "60024", "60025", "60030"])
    m_fason_sv = m600 & (desc.str.contains("FASON", na=False) | fason_p6 | desc.str.contains("KAPLAMA UC", na=False)) & ~m_yarn_resale & ~m_trading
    out.loc[m_fason_sv, "account_class_sub"] = "outsourced_service_revenue"
    out.loc[m_fason_sv, "business_bucket"] = "outsourced_service_revenue"
    out.loc[m_fason_sv, "project_use_case"] = "core_sales_analysis"
    out.loc[m_fason_sv, "confidence_level"] = "high"
    out.loc[m_fason_sv, "classification_reason"] = "FASON service revenue."

    m_knit = m600 & p6.str.startswith("60002") & ~m_yarn_resale & ~m_trading & ~m_fason_sv
    out.loc[m_knit, "account_class_sub"] = "knit_fabric"
    out.loc[m_knit, "business_bucket"] = "core_product_sales"
    out.loc[m_knit, "project_use_case"] = "core_sales_analysis"
    out.loc[m_knit, "clean_product_type"] = "knit_fabric"
    out.loc[m_knit, "classification_reason"] = "600-02 knit fabric."

    m_woven = m600 & p6.str.startswith("60061") & ~m_yarn_resale & ~m_trading & ~m_fason_sv & ~m_knit
    out.loc[m_woven, "account_class_sub"] = "woven_fabric"
    out.loc[m_woven, "business_bucket"] = "core_product_sales"
    out.loc[m_woven, "project_use_case"] = "core_sales_analysis"
    out.loc[m_woven, "classification_reason"] = "600-61 woven fabric."
    out.loc[m_woven & desc.str.contains("POLYESTER", na=False), "clean_product_type"] = "polyester_woven"
    out.loc[m_woven & desc.str.contains("NAYLON", na=False), "clean_product_type"] = "nylon_woven"
    out.loc[m_woven & desc.str.contains("KARIŞIM", na=False), "clean_product_type"] = "blend_woven"
    out.loc[m_woven & desc.str.contains("PAMUK", na=False), "clean_product_type"] = "cotton_woven"

    m_600_other = m600 & ~m_yarn_resale & ~m_trading & ~m_fason_sv & ~m_knit & ~m_woven
    out.loc[m_600_other, "account_class_sub"] = "revenue_other"
    out.loc[m_600_other, "business_bucket"] = "non_core_trading"
    out.loc[m_600_other, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_600_other, "review_flag"] = False
    out.loc[m_600_other, "confidence_level"] = "medium"
    out.loc[m_600_other, "classification_reason"] = "600 non-core sub (TRİKO/TAKIM)."

    # 601, 612 contra
    m601 = p3.eq("601")
    out.loc[m601, "account_class_main"] = "SALES_RETURN"
    out.loc[m601, "business_bucket"] = "sales_return_contra"
    out.loc[m601, "subtype"] = "contra_revenue_return"
    out.loc[m601, "project_use_case"] = "core_sales_analysis"
    out.loc[m601, "review_flag"] = False
    out.loc[m601, "confidence_level"] = "high"
    out.loc[m601, "classification_reason"] = "601 sales return."

    m612 = p3.eq("612")
    out.loc[m612, "account_class_main"] = "SALES_DISCOUNT"
    out.loc[m612, "business_bucket"] = "sales_return_contra"
    out.loc[m612, "subtype"] = "contra_revenue_discount"
    out.loc[m612, "project_use_case"] = "core_sales_analysis"
    out.loc[m612, "review_flag"] = False
    out.loc[m612, "confidence_level"] = "medium"
    out.loc[m612, "classification_reason"] = "612 sales discount."

    # 602 OTHER OPERATING INCOME
    m602 = p3.eq("602")
    out.loc[m602, "account_class_main"] = "OTHER_OPERATING_INCOME"
    out.loc[m602, "review_flag"] = False

    m_scrap = m602 & desc.str.contains(r"\bHURDA\b|\bATIK\b|\bSCRAP\b", regex=True, na=False)
    out.loc[m_scrap, "account_class_sub"] = "scrap"
    out.loc[m_scrap, "business_bucket"] = "scrap_sales"
    out.loc[m_scrap, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_scrap, "confidence_level"] = "high"
    out.loc[m_scrap, "classification_reason"] = "602 scrap."

    m_pfark = m602 & desc.str.contains(r"FIYAT FARK|FARK FATURA", regex=True, na=False) & ~m_scrap
    out.loc[m_pfark, "account_class_sub"] = "price_adjustment"
    out.loc[m_pfark, "business_bucket"] = "adjustments_noncore"
    out.loc[m_pfark, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_pfark, "confidence_level"] = "high"
    out.loc[m_pfark, "classification_reason"] = "602 price diff."

    m_ciro = m602 & desc.str.contains("CİRO PRİM", na=False) & ~m_scrap & ~m_pfark
    out.loc[m_ciro, "account_class_sub"] = "volume_rebate"
    out.loc[m_ciro, "business_bucket"] = "adjustments_noncore"
    out.loc[m_ciro, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_ciro, "confidence_level"] = "high"
    out.loc[m_ciro, "classification_reason"] = "602 CİRO PRİMLERİ → adjustments."

    m_claim = m602 & desc.str.contains(r"REKLAMASYON|\bHASAR\b|\bSİGORTA\b", regex=True, na=False) & ~m_scrap & ~m_pfark & ~m_ciro
    out.loc[m_claim, "account_class_sub"] = "claim_insurance"
    out.loc[m_claim, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_claim, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_claim, "confidence_level"] = "high"
    out.loc[m_claim, "classification_reason"] = "602 reklamasyon."

    m_other_income = m602 & desc.str.contains(r"DİĞER GELİR|\bÇEŞİTLİ\b", regex=True, na=False) & ~m_scrap & ~m_pfark & ~m_ciro & ~m_claim
    out.loc[m_other_income, "account_class_sub"] = "misc_other"
    out.loc[m_other_income, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_other_income, "project_use_case"] = "manual_review"
    out.loc[m_other_income, "review_flag"] = True
    out.loc[m_other_income, "confidence_level"] = "low"
    out.loc[m_other_income, "classification_reason"] = "602 DİĞER GELİRLER — review."

    # Large outliers → suspected_asset_sale
    m_suspect = m_other_income & (amt >= 10_000_000)
    out.loc[m_suspect, "account_class_sub"] = "suspected_asset_sale"
    out.loc[m_suspect, "business_bucket"] = "anomalous_review"
    out.loc[m_suspect, "subtype"] = "suspected_asset_sale"
    out.loc[m_suspect, "project_use_case"] = "manual_review"
    out.loc[m_suspect, "review_flag"] = True
    out.loc[m_suspect, "confidence_level"] = "low"
    out.loc[m_suspect, "classification_reason"] = "Large DİĞER GELİRLER (>10M TL) — likely asset sale."

    m_602_fb = m602 & ~m_scrap & ~m_pfark & ~m_ciro & ~m_claim & ~m_other_income
    out.loc[m_602_fb, "account_class_sub"] = "operating_other"
    out.loc[m_602_fb, "business_bucket"] = "misc_noncore_sales"
    out.loc[m_602_fb, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_602_fb, "confidence_level"] = "medium"
    out.loc[m_602_fb, "classification_reason"] = "602 fallback."

    # 646 FX
    m646 = p3.eq("646")
    out.loc[m646, "account_class_main"] = "FX"
    out.loc[m646, "business_bucket"] = "fx_gain_loss"
    out.loc[m646, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m646, "review_flag"] = False
    out.loc[m646, "confidence_level"] = "high"
    out.loc[m646, "classification_reason"] = "646 FX."

    # 679
    m679 = p3.eq("679")
    out.loc[m679, "account_class_main"] = "NON_CORE_INCOME"
    out.loc[m679, "business_bucket"] = "other_noncore_income"
    out.loc[m679, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m679, "review_flag"] = False
    out.loc[m679, "confidence_level"] = "high"
    out.loc[m679, "classification_reason"] = "679 other non-core."

    # 656
    m656s = p3.eq("656")
    out.loc[m656s, "account_class_main"] = "NON_OPERATING"
    out.loc[m656s, "business_bucket"] = "other_noncore_income"
    out.loc[m656s, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m656s, "review_flag"] = False
    out.loc[m656s, "confidence_level"] = "high"
    out.loc[m656s, "classification_reason"] = "656 non-op."

    # 254/253/255/258 in SATIŞ → capex_disposal
    m_capex_disp = p3.isin(["253", "254", "255", "258"])
    out.loc[m_capex_disp, "account_class_main"] = "CAPEX_DISPOSAL"
    out.loc[m_capex_disp, "business_bucket"] = "capex_disposal"
    out.loc[m_capex_disp, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m_capex_disp, "review_flag"] = False
    out.loc[m_capex_disp, "confidence_level"] = "high"
    out.loc[m_capex_disp, "classification_reason"] = "Fixed-asset disposal in SATIŞ."

    # 150/153 in SATIŞ → non_core_trading
    m150_satis = p3.eq("150")
    out.loc[m150_satis, "account_class_main"] = "TRADING_IN_SATIS"
    out.loc[m150_satis, "business_bucket"] = "non_core_trading"
    out.loc[m150_satis, "subtype"] = "inventory_resale"
    out.loc[m150_satis, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m150_satis, "review_flag"] = False
    out.loc[m150_satis, "confidence_level"] = "medium"
    out.loc[m150_satis, "classification_reason"] = "150 inventory resale in SATIŞ."

    m153_satis = p3.eq("153")
    out.loc[m153_satis, "account_class_main"] = "TRADING_IN_SATIS"
    out.loc[m153_satis, "business_bucket"] = "non_core_trading"
    out.loc[m153_satis, "subtype"] = "trade_goods_resale"
    out.loc[m153_satis, "project_use_case"] = "non_core_noise_exclusion"
    out.loc[m153_satis, "review_flag"] = False
    out.loc[m153_satis, "confidence_level"] = "medium"
    out.loc[m153_satis, "classification_reason"] = "153 trade goods resale in SATIŞ."

    # 730/760/770 in SATIŞ → anomalous_review (reversal)
    for p in ["730", "760", "770"]:
        m = p3.eq(p)
        out.loc[m, "business_bucket"] = "anomalous_review"
        out.loc[m, "review_flag"] = True
        out.loc[m, "confidence_level"] = "low"
        out.loc[m, "classification_reason"] = f"{p} in SATIŞ — likely reversal."

    return out


# ============================================================================
# MAIN
# ============================================================================

def main():
    default_path = r"C:\Projects\rayon-intelligence\data\ALIŞ SATIŞ 22042026.xlsx"
    src = sys.argv[1] if len(sys.argv) > 1 else default_path

    if not os.path.exists(src):
        print(f"ERROR: File not found: {src}")
        sys.exit(1)

    out_dir = Path("outputs/v3")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading: {src}")
    t0 = time.time()
    alis_raw = pd.read_excel(src, sheet_name="ALIŞ")
    satis_raw = pd.read_excel(src, sheet_name="SATIŞ")
    print(f"  [{time.time()-t0:.1f}s] ALIŞ: {len(alis_raw):,} / SATIŞ: {len(satis_raw):,}")

    t0 = time.time()
    alis_derived = classify_alis_v3(alis_raw)
    alis_derived["clean_counterparty_type"] = _counterparty_type(alis_raw["Cari Hesap Açıklaması"])
    alis_clean = pd.concat([alis_raw.reset_index(drop=True), alis_derived.reset_index(drop=True)], axis=1)
    alis_clean.insert(0, "source_sheet", "ALIS")
    print(f"  [{time.time()-t0:.1f}s] ALIŞ classified")

    t0 = time.time()
    satis_derived = classify_satis_v3(satis_raw)
    satis_derived["clean_counterparty_type"] = _counterparty_type(satis_raw["Cari Hesap Açıklaması"])
    satis_clean = pd.concat([satis_raw.reset_index(drop=True), satis_derived.reset_index(drop=True)], axis=1)
    satis_clean.insert(0, "source_sheet", "SATIS")
    print(f"  [{time.time()-t0:.1f}s] SATIŞ classified")

    # Dual relevance
    for df in (alis_clean, satis_clean):
        df["is_core_business_relevant"] = df["business_bucket"].map(lambda b: BUCKET_RELEVANCE.get(b, (None, None))[0])
        df["is_cost_model_relevant"] = df["business_bucket"].map(lambda b: BUCKET_RELEVANCE.get(b, (None, None))[1])

    # Save pickles for ETL consumption
    alis_raw.to_pickle(out_dir / "alis_raw.pkl")
    satis_raw.to_pickle(out_dir / "satis_raw.pkl")
    alis_clean.to_pickle(out_dir / "alis_clean_v3.pkl")
    satis_clean.to_pickle(out_dir / "satis_clean_v3.pkl")

    # Summary
    with open(out_dir / "classification_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Nebim classification v3 — {pd.Timestamp.now():%Y-%m-%d %H:%M}\n\n")
        for label, df in [("ALIŞ", alis_clean), ("SATIŞ", satis_clean)]:
            f.write(f"=== {label} — {len(df):,} rows ===\n")
            g = df.groupby("business_bucket").agg(
                rows=("Hesap Kodu", "size"),
                amount=("Net Tutar (Y)", "sum"),
            ).sort_values("amount", ascending=False)
            for b, r in g.iterrows():
                f.write(f"  {b:30s}  {int(r['rows']):6,}  {r['amount']:>15,.0f} TL\n")
            f.write("\n")

    print(f"\nOutputs in {out_dir.absolute()}")
    print(f"  alis_raw.pkl        ({len(alis_raw):,} rows)")
    print(f"  satis_raw.pkl       ({len(satis_raw):,} rows)")
    print(f"  alis_clean_v3.pkl   ({len(alis_clean):,} rows, {len(alis_clean.columns)} cols)")
    print(f"  satis_clean_v3.pkl  ({len(satis_clean):,} rows, {len(satis_clean.columns)} cols)")
    print(f"  classification_summary.txt")
    print("\nNext: python scripts/etl_nebim_load.py")


if __name__ == "__main__":
    main()
