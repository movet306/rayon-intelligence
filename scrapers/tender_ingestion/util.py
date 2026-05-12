"""Shared utilities for Phase F tender ingestion (Silver + Gold layers)."""

# Turkish to ASCII map for normalized keyword matching.
# Original text is preserved in the database; matching uses normalized form.
TR_NORMALIZE_MAP = str.maketrans({
    "\u00e7": "c", "\u00c7": "c",   # c-cedilla
    "\u011f": "g", "\u011e": "g",   # g-breve
    "\u0131": "i", "\u0130": "i",   # dotless i / dotted I
    "\u00f6": "o", "\u00d6": "o",   # o-umlaut
    "\u015f": "s", "\u015e": "s",   # s-cedilla
    "\u00fc": "u", "\u00dc": "u",   # u-umlaut
})


def tr_normalize(text: str) -> str:
    """Lowercase + remove Turkish diacritics for keyword matching.

    Examples:
        >>> tr_normalize("KumaĹŸ")  # 'KumaĹŸ' = Turkish for 'fabric' with cedilla
        'kumas'
        >>> tr_normalize("Ä°stanbul BĂĽyĂĽkĹŸehir")
        'istanbul buyuksehir'
    """
    if not text:
        return ""
    # Translate FIRST (replaces İ->i directly) then lower() to avoid Python's
    # default Unicode behavior of decomposing İ into "i" + U+0307 (combining dot).
    return text.translate(TR_NORMALIZE_MAP).lower()
