\set ON_ERROR_STOP on
\echo === section 4 (clear, revision 3 block)
\set ON_ERROR_STOP off
\i /tmp/lat2316-fixture/r3/section4.sql
\set ON_ERROR_STOP on
\echo === A1
\i /tmp/lat2316-fixture/r3/a1.sql
\echo === A2
\i /tmp/lat2316-fixture/r3/a2.sql
\echo === A3
ANALYZE futures_markets;
\i /tmp/lat2316-fixture/r3/gate.sql
\echo === R1a
\i /tmp/lat2316-fixture/r3/r1a-parallel.sql
\echo === section 4 (rollback, revision 3 block)
\set ON_ERROR_STOP off
\i /tmp/lat2316-fixture/r3/section4.sql
