"""One-time backfill: blend_ratio_json populate for 23 blend yarns.

Date: 8 May 2026 (Phase D-A)
Context: dim_yarn_master.blend_ratio_json was NULL for 23 blend yarns
synced via sheet_to_db.py (which does not yet handle this column).
This caused build_yarn_pricing.py:compute_weighted_blend to return None
and pressure_signal to fall to tier_4_no_benchmark.

Populating blend_ratio_json unblocks both:
  - compute_weighted_blend (ratio-weighted upstream price)
  - driver_inference (rules now match because _has_fibers() works)

Result: 23/23 blend yarns now price via tier_4_proxy_fallback.
Total: 69/70 priced (1 PA66 placeholder skipped).

Future Phase D-C/E: add derive_blend_ratio_json helper to sheet_to_db.py
so new blend yarns are auto-populated on sync.
"""
import os
import json
import psycopg2

BLEND_RATIO_MAPPING = {
    # PV blends (PES + VIS, 65/35 standard)
    'PV_NE30_1_65_35':                  {'PES': 65, 'VIS': 35},
    'PV_NE28_1_65_35':                  {'PES': 65, 'VIS': 35},
    'PV_NE28_2_65_35':                  {'PES': 65, 'VIS': 35},
    'PV_NE40_1_65_35':                  {'PES': 65, 'VIS': 35},
    'PV_NE40_1_65_35_BLACK':            {'PES': 65, 'VIS': 35},
    'PV_NE40_2_65_35_BLACK':            {'PES': 65, 'VIS': 35},
    'PV_NE28_1_65_35_VORTEX':           {'PES': 65, 'VIS': 35},
    'PV_NE40_1_65_35_VORTEX':           {'PES': 65, 'VIS': 35},

    # PM blends (PES + MOD, 50/50)
    'PM_NE28_1_50_50':                  {'PES': 50, 'MOD': 50},
    'PM_NE28_2_50_50':                  {'PES': 50, 'MOD': 50},
    'PM_NE40_1_50_50':                  {'PES': 50, 'MOD': 50},

    # 3-component blends
    'PES_VIS_COT_50_30_20_NE30_1':      {'PES': 50, 'VIS': 30, 'COT': 20},
    'MOD_COT_PES_50_25_25_NE30_1':      {'MOD': 50, 'COT': 25, 'PES': 25},
    'MOD_COT_VIS_50_25_25_NE30_1':      {'MOD': 50, 'COT': 25, 'VIS': 25},

    # Corespun (base + ELASTANE 7%)
    'COT_ELASTANE_NE30_1_CORESPUN':     {'COT': 93, 'ELASTANE': 7},
    'VIS_ELASTANE_NE30_1_CORESPUN':     {'VIS': 93, 'ELASTANE': 7},
    'PV_ELASTANE_NE30_1_CORESPUN':      {'PES': 60.45, 'VIS': 32.55, 'ELASTANE': 7},
    'PV_NE40_2_LYCRA_CORESPUN_BLACK':   {'PES': 60.45, 'VIS': 32.55, 'ELASTANE': 7},

    # Cotton-anchored 2-component blends
    'COT_PES_70_30_NE30_1':             {'COT': 70, 'PES': 30},
    'COT_VIS_50_50_NE30_1':             {'COT': 50, 'VIS': 50},
    'COT_MOD_70_30_NE30_1':             {'COT': 70, 'MOD': 30},

    # Recycled blends (RCY_X tokens use built-in recycled premiums)
    'COT_RECYCLED_PES_50_50_NE30_1':    {'COT': 50, 'RCY_PES': 50},
    'COT_RECYCLED_COT_70_30_NE30_1':    {'COT': 70, 'RCY_COT': 30},
}


def main():
    url = os.environ.get('RAYON_DATABASE_URL') or os.environ['DATABASE_URL']
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    print(f'Populating blend_ratio_json for {len(BLEND_RATIO_MAPPING)} blend yarns...')
    updated, missing = 0, []
    for yarn_code, ratio in BLEND_RATIO_MAPPING.items():
        cur.execute(
            'UPDATE dim_yarn_master SET blend_ratio_json = %s::jsonb '
            'WHERE yarn_code = %s RETURNING yarn_id',
            (json.dumps(ratio), yarn_code)
        )
        if cur.fetchone():
            updated += 1
        else:
            missing.append(yarn_code)

    conn.commit()
    print(f'  Updated: {updated}/{len(BLEND_RATIO_MAPPING)}')
    if missing:
        print(f'  NOT FOUND: {missing}')

    cur.execute("""
        SELECT COUNT(*) FROM dim_yarn_master
        WHERE fiber_family = 'blend' AND blend_ratio_json IS NOT NULL
    """)
    print(f'  Verify: {cur.fetchone()[0]}/23 blend yarns have blend_ratio_json')

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()