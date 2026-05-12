"""
Phase F: Tender Intelligence module.

Three-layer architecture:
- Bronze: tender_bulletin_scraper (daily PDF) + tender_ekap_v2_scraper (F2)
- Silver: tender_normalize (Turkish normalization, status interpretation)
- Gold:   tender_relevance_engine (rule-based scoring) + tender_llm_analyzer (F3)

See docs/PHASE_F_TENDER_INTELLIGENCE_DESIGN.md for the full design.
"""

__version__ = "0.1.0-F0"
