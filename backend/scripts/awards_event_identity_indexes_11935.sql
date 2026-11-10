-- DISCOVER / TRUTH. A ceremony card opens its complete collection (#11935).
-- Operator applies after Alex's schema approval under NOW 92-C.
-- Run with psql ON_ERROR_STOP enabled, outside a transaction and Alembic.
SET lock_timeout = '2s';
SET statement_timeout = '15min';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fm_kalshi_event_identity_11935
    ON public.futures_markets
    ((COALESCE(market_metadata->>'kalshi_event_ticker', external_id)))
    WHERE source = 'kalshi';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fm_polymarket_event_identity_11935
    ON public.futures_markets
    ((market_metadata->>'polymarket_event_id'))
    WHERE source = 'polymarket';

DO $$
BEGIN
    IF (
        SELECT count(*) = 2 AND bool_and(i.indisvalid AND i.indisready)
        FROM pg_index AS i
        JOIN pg_class AS index_relation ON index_relation.oid = i.indexrelid
        JOIN pg_namespace AS namespace ON namespace.oid = index_relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND i.indrelid = 'public.futures_markets'::regclass
          AND index_relation.relname IN (
              'ix_fm_kalshi_event_identity_11935',
              'ix_fm_polymarket_event_identity_11935'
          )
    ) IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION '11935 provider-event indexes require operator inspection';
    END IF;
END;
$$;
