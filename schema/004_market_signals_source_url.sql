-- Rayon Intelligence Platform — Market Signals source URL
-- Adds source_url so signal cards can link back to the original article.

BEGIN;

ALTER TABLE market_signals
    ADD COLUMN IF NOT EXISTS source_url TEXT;

COMMENT ON COLUMN market_signals.source_url IS
    'URL of the source article/page that generated this signal (from news_items.url).';

-- Backfill from existing news_items rows
UPDATE market_signals ms
SET    source_url = ni.url
FROM   news_items ni
WHERE  ms.source_table = 'news_items'
  AND  ms.source_id::uuid = ni.id
  AND  ms.source_url IS NULL;

COMMIT;
