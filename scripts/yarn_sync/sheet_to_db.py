#!/usr/bin/env python3
"""
sheet_to_db.py v2 - Phase C+1 sync from yarn evidence sheet to dim_yarn_master.

Reads a tab-separated (or comma-separated) export from the Phase B evidence
sheet, filters rows where status='research_filled', and upserts into
dim_yarn_master via the yarn_code unique key.

Candidate fields are mapped to production fields:
    market_common_candidate    -> is_market_common
    pricing_basis_candidate    -> pricing_basis
    primary_driver_candidate   -> primary_driver_slug
    secondary_driver_candidate -> secondary_driver_slug
    rayon_confirmed_candidate  -> is_rayon_confirmed
    active_tracked_candidate   -> is_active_tracked
    evidence_strength          -> spec_confidence (strong->high, moderate->medium, weak->low)

material_form is DERIVED from subfamily:
    staple_ring   -> staple
    staple_vortex -> staple
    filament      -> filament
    textured      -> textured_filament
    industrial    -> industrial_filament

Usage:
    python scripts/yarn_sync/sheet_to_db.py <csv_path> --tab viscose [--dry-run]
"""
import argparse
import json
import os
import re
import sys

import pandas as pd
import psycopg2


# Helpers - type coercion from sheet strings

def s(value, default=None):
    """Normalize string: empty/NaN -> default, else stripped string."""
    if value is None:
        return default
    if pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default


def b(value, default=None):
    """Normalize boolean: TRUE/FALSE strings (case-insensitive) -> bool, else default."""
    text = s(value)
    if text is None:
        return default
    upper = text.upper()
    if upper in ('TRUE', 'YES', '1'):
        return True
    if upper in ('FALSE', 'NO', '0'):
        return False
    return default


def n(value, default=None, int_type=False):
    """Normalize numeric: empty/NaN -> default, else float (or int)."""
    text = s(value)
    if text is None:
        return default
    try:
        result = float(text)
        return int(result) if int_type else result
    except (ValueError, TypeError):
        return default


CONFIDENCE_MAP = {
    'strong':       'high',
    'moderate':     'medium',
    'weak':         'low',
    'insufficient': None,
}


# Phase C+1: driver slug normalization
# Sheet workflow may use _NEW: prefix for drivers not yet in dim_material,
# or generic family names. Map to existing canonical slugs to satisfy FK.
DRIVER_ALIAS = {
    'polyester_filament': 'polyester_dty',  # generic filament -> closest existing
}


def normalize_driver(driver_str):
    """Normalize driver slug from sheet: strip _NEW: prefix, apply aliases."""
    text = s(driver_str)
    if text is None:
        return None
    if text.startswith('_NEW:'):
        text = text[5:]
    return DRIVER_ALIAS.get(text, text)


def derive_subfamily(yarn_code, subfamily_raw):
    """Derive specific subfamily (staple_ring/vortex/oe) from yarn_code suffix
    when sheet provides only generic 'staple'. Keeps existing specific values
    untouched (e.g., DTY, staple_vortex from sheet pass through).
    """
    if subfamily_raw and subfamily_raw.lower().strip() != 'staple':
        return subfamily_raw
    code = (yarn_code or '').upper()
    for spec, label in [('RING', 'staple_ring'), ('VORTEX', 'staple_vortex'), ('OE', 'staple_oe')]:
        if code.endswith(f'_{spec}') or f'_{spec}_' in code:
            return label
    return subfamily_raw


def derive_blend_ratio_json(yarn_code, fiber_family):
    """Auto-derive blend_ratio_json (JSON string) from yarn_code patterns.

    Only applies when fiber_family='blend'. Returns a JSON-encoded string
    matching dim_yarn_master.blend_ratio_json (jsonb), or None.

    Recognized patterns (checked in order):
      1. Corespun (CORESPUN/ELASTANE/LYCRA keyword) -> base 93 + ELASTANE 7
      2. PV_*_{a}_{b}              -> {PES: a, VIS: b}
      3. PM_*_{a}_{b}              -> {PES: a, MOD: b}
      4. COT_RECYCLED_{F}_{a}_{b}  -> {COT: a, RCY_PES/RCY_COT: b}
      5. {F1}_{F2}_{F3}_{a}_{b}_{c} -> 3-component blend
      6. COT_{F}_{a}_{b}           -> cotton-anchored 2-component
    """
    if fiber_family != 'blend' or not yarn_code:
        return None

    code = yarn_code.upper()

    # 1) Corespun first (keyword can co-occur with PV/COT/VIS prefixes)
    if 'CORESPUN' in code or 'ELASTANE' in code or 'LYCRA' in code:
        if code.startswith('PV_'):
            return json.dumps({"PES": 60.45, "VIS": 32.55, "ELASTANE": 7})
        if code.startswith('COT_'):
            return json.dumps({"COT": 93, "ELASTANE": 7})
        if code.startswith('VIS_'):
            return json.dumps({"VIS": 93, "ELASTANE": 7})

    # 2) PV blends (PES + VIS)
    m = re.match(r'^PV_(?:NE\d+_\d+_)?(\d{2})_(\d{2})', code)
    if m:
        return json.dumps({"PES": int(m.group(1)), "VIS": int(m.group(2))})

    # 3) PM blends (PES + MOD)
    m = re.match(r'^PM_(?:NE\d+_\d+_)?(\d{2})_(\d{2})', code)
    if m:
        return json.dumps({"PES": int(m.group(1)), "MOD": int(m.group(2))})

    # 4) Cotton + recycled (must precede COT_X to win specificity)
    m = re.match(r'^COT_RECYCLED_(\w+?)_(\d{2})_(\d{2})', code)
    if m:
        f, r1, r2 = m.group(1), int(m.group(2)), int(m.group(3))
        if f == 'PES':
            return json.dumps({"COT": r1, "RCY_PES": r2})
        if f == 'COT':
            return json.dumps({"COT": r1, "RCY_COT": r2})

    # 5) 3-component blends
    m = re.match(r'^([A-Z]{2,3})_([A-Z]{2,3})_([A-Z]{2,3})_(\d{2})_(\d{2})_(\d{2})', code)
    if m:
        valid = {"PES", "VIS", "MOD", "COT", "PA"}
        f1, f2, f3 = m.group(1), m.group(2), m.group(3)
        if f1 in valid and f2 in valid and f3 in valid:
            return json.dumps({
                f1: int(m.group(4)),
                f2: int(m.group(5)),
                f3: int(m.group(6)),
            })

    # 6) Cotton-anchored 2-component (COT_PES/VIS/MOD)
    m = re.match(r'^COT_([A-Z]+)_(\d{2})_(\d{2})', code)
    if m:
        f = m.group(1)
        if f in {"PES", "VIS", "MOD"}:
            return json.dumps({"COT": int(m.group(2)), f: int(m.group(3))})

    return None


def derive_material_form(subfamily):
    """Derive material_form (NOT NULL in dim_yarn_master) from subfamily.

    Existing 21 yarns use: filament / industrial_filament / textured_filament.
    New spun yarns from sheet use 'staple_ring', 'staple_vortex', etc.
    Mapping is permissive: unknown subfamilies fall through as-is.
    """
    if not subfamily:
        return 'unknown'
    sub = subfamily.lower().strip()
    if 'textured' in sub:
        return 'textured_filament'
    if 'industrial' in sub:
        return 'industrial_filament'
    if 'staple' in sub:
        return 'staple'
    if 'monofilament' in sub:
        return 'monofilament'
    if 'filament' in sub:
        return 'filament'
    return sub  # fallback - use as-is


# Main upsert

UPSERT_SQL = """
INSERT INTO dim_yarn_master (
    yarn_code, display_name, fiber_family, material_form, subfamily,
    count_type, denier, filament_count, ne_count, ply, twist_direction,
    luster, recycle_flag, color_state, specialty_flags,
    blend_ratio_json,
    primary_driver_slug, secondary_driver_slug,
    is_market_common, is_rayon_confirmed, is_active_tracked,
    pricing_basis, spec_confidence,
    pricing_eligible, is_placeholder, subspec_sensitive,
    sheet_row_id, sheet_synced_at
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s,
    %s, %s, %s,
    %s, %s,
    %s, %s, %s,
    %s, NOW()
)
ON CONFLICT (yarn_code) DO UPDATE SET
    display_name          = EXCLUDED.display_name,
    fiber_family          = EXCLUDED.fiber_family,
    material_form         = EXCLUDED.material_form,
    subfamily             = EXCLUDED.subfamily,
    count_type            = EXCLUDED.count_type,
    denier                = EXCLUDED.denier,
    filament_count        = EXCLUDED.filament_count,
    ne_count              = EXCLUDED.ne_count,
    ply                   = EXCLUDED.ply,
    twist_direction       = EXCLUDED.twist_direction,
    luster                = EXCLUDED.luster,
    recycle_flag          = EXCLUDED.recycle_flag,
    color_state           = EXCLUDED.color_state,
    specialty_flags       = EXCLUDED.specialty_flags,
    blend_ratio_json      = COALESCE(EXCLUDED.blend_ratio_json, dim_yarn_master.blend_ratio_json),
    primary_driver_slug   = EXCLUDED.primary_driver_slug,
    secondary_driver_slug = EXCLUDED.secondary_driver_slug,
    is_market_common      = EXCLUDED.is_market_common,
    is_rayon_confirmed    = EXCLUDED.is_rayon_confirmed,
    is_active_tracked     = EXCLUDED.is_active_tracked,
    pricing_basis         = EXCLUDED.pricing_basis,
    spec_confidence       = EXCLUDED.spec_confidence,
    pricing_eligible      = EXCLUDED.pricing_eligible,
    sheet_synced_at       = NOW()
"""


def read_sheet(csv_path):
    """Read CSV/TSV from sheet export. Auto-detects separator."""
    try:
        df = pd.read_csv(csv_path, sep='\t', dtype=str, keep_default_na=False)
        if len(df.columns) > 5:
            return df
    except Exception:
        pass
    return pd.read_csv(csv_path, sep=',', dtype=str, keep_default_na=False)


def filter_rows(df):
    """Filter to research_filled rows with non-empty canonical_code."""
    if 'status' not in df.columns:
        raise ValueError(f"Sheet missing 'status' column. Columns: {list(df.columns)[:10]}...")
    if 'canonical_code' not in df.columns:
        raise ValueError(f"Sheet missing 'canonical_code' column. Columns: {list(df.columns)[:10]}...")

    initial = len(df)
    df = df[df['status'].str.strip() == 'research_filled']
    df = df[df['canonical_code'].str.strip() != '']
    print(f'  Filtered: {initial} rows -> {len(df)} actionable rows '
          f'(status=research_filled, canonical_code not empty)')
    return df


def row_to_params(row, sheet_row_id):
    """Map a sheet row to UPSERT_SQL parameter tuple."""
    yarn_code = s(row.get('canonical_code'))
    if not yarn_code:
        return None

    ne_count = n(row.get('ne_count'))
    denier = n(row.get('denier'))

    # count_type discriminator
    if ne_count is not None:
        count_type = 'Ne'
    elif denier is not None:
        count_type = 'denier'
    else:
        count_type = None

    subfamily = derive_subfamily(s(row.get('canonical_code')), s(row.get('subfamily')))
    material_form = derive_material_form(subfamily)

    # Phase C+1 semantics: rows reaching here are already filtered to
    # status='research_filled', which implies sufficient evidence for
    # market_common=True. An explicit TRUE/FALSE in market_common_candidate
    # overrides this default; 'pending' falls back to True.
    explicit_mc = b(row.get('market_common_candidate'))
    is_market_common = explicit_mc if explicit_mc is not None else True
    pricing_eligible = is_market_common is True

    confidence = CONFIDENCE_MAP.get(
        s(row.get('evidence_strength'), '').lower(), None
    )

    return (
        yarn_code,
        s(row.get('display_name')),
        s(row.get('family')),
        material_form,
        subfamily,
        count_type,
        denier,
        n(row.get('filament_count'), int_type=True),
        ne_count,
        n(row.get('ply'), int_type=True),
        s(row.get('twist_direction')),
        s(row.get('luster')),
        b(row.get('recycle_flag'), default=False),
        s(row.get('color_state')),
        s(row.get('specialty_flags')),
        derive_blend_ratio_json(yarn_code, s(row.get('fiber_family'))),
        normalize_driver(row.get('primary_driver_candidate')),
        normalize_driver(row.get('secondary_driver_candidate')),
        is_market_common,
        b(row.get('rayon_confirmed_candidate'), default=False),
        b(row.get('active_tracked_candidate'), default=False),
        s(row.get('pricing_basis_candidate')),
        confidence,
        pricing_eligible,
        False,  # is_placeholder
        False,  # subspec_sensitive default
        sheet_row_id,
    )


def main():
    parser = argparse.ArgumentParser(description='Sync evidence sheet rows to dim_yarn_master')
    parser.add_argument('csv_path', help='Path to TSV/CSV from sheet (export or paste)')
    parser.add_argument('--tab', required=True,
                        help='Tab name for sheet_row_id prefix (e.g., viscose, modal, cotton)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview rows without writing to DB')
    args = parser.parse_args()

    DATABASE_URL = os.environ.get('RAYON_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        print('ERROR: RAYON_DATABASE_URL or DATABASE_URL env var must be set', file=sys.stderr)
        sys.exit(1)

    print(f'Reading: {args.csv_path}')
    df = read_sheet(args.csv_path)
    print(f'  Loaded {len(df)} rows, {len(df.columns)} columns')
    df = filter_rows(df)

    if df.empty:
        print('No rows to sync.')
        return

    print(f'\nRows to sync (tab={args.tab}):')
    print('-' * 110)
    print(f'  {"sheet_row_id":<18} {"yarn_code":<28} {"family":<10} {"m_form":<10} {"driver":<22} {"market_common"}')
    print('-' * 110)
    rows_with_meta = []
    for idx, row in df.iterrows():
        sheet_row_id = f'{args.tab}_{idx + 2}'
        params = row_to_params(row, sheet_row_id)
        if params is None:
            continue
        rows_with_meta.append((sheet_row_id, params))
        # params indices: 0=yarn_code, 2=fiber_family, 3=material_form, 15=primary_driver, 17=is_market_common
        print(f'  {sheet_row_id:<18} {params[0]:<28} {(params[2] or ""):<10} '
              f'{(params[3] or ""):<10} {(params[15] or ""):<22} {params[17]}')
    print('-' * 110)
    print(f'  Total: {len(rows_with_meta)} rows')

    if args.dry_run:
        print('\n[DRY RUN] No DB writes performed.')
        return

    print(f'\nConnecting to DB...')
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    inserted = 0
    updated = 0
    for sheet_row_id, params in rows_with_meta:
        yarn_code = params[0]
        cur.execute('SELECT 1 FROM dim_yarn_master WHERE yarn_code = %s', (yarn_code,))
        exists = cur.fetchone() is not None
        cur.execute(UPSERT_SQL, params)
        if exists:
            updated += 1
        else:
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f'\nDone. Inserted: {inserted}, Updated: {updated}')
    print(f"Verify: SELECT COUNT(*) FROM dim_yarn_master WHERE sheet_row_id LIKE '{args.tab}_%';")


if __name__ == '__main__':
    main()
