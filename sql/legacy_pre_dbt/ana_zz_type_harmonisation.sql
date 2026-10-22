-- =====================================================================================================
-- Type harmonisation of the derived tables (runs LAST: file name starts with ana_zz).
-- Policy (README section 4): counts / people / years -> integer; continuous measures (rates, shares, money, distances, areas) -> double precision;
-- dates -> date; codes -> text. SQL arithmetic produces numeric (round(..., 2)) and bigint (sum / count), so every such column of schema ana is
-- converted here: numeric -> double precision, bigint -> integer when all values fit (the shared keys stay integer in every table).
-- Views of other schemas that depend on a column (e.g. dbt models) would block ALTER TYPE: such columns are reported and skipped.
-- =====================================================================================================
DO $$
DECLARE r record; mx numeric;
BEGIN
  FOR r IN SELECT c.table_name, c.column_name, c.data_type
           FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
           WHERE c.table_schema = 'ana' AND t.table_type = 'BASE TABLE' AND c.data_type IN ('numeric', 'bigint')
  LOOP
    BEGIN
      IF r.data_type = 'numeric' THEN
        EXECUTE format('ALTER TABLE ana.%I ALTER COLUMN %I TYPE double precision', r.table_name, r.column_name);
      ELSE
        EXECUTE format('SELECT max(abs(%I)) FROM ana.%I', r.column_name, r.table_name) INTO mx;
        IF coalesce(mx, 0) < 2147483647 THEN
          EXECUTE format('ALTER TABLE ana.%I ALTER COLUMN %I TYPE integer', r.table_name, r.column_name);
        END IF;
      END IF;
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'type harmonisation skipped ana.%.% (%): %', r.table_name, r.column_name, r.data_type, SQLERRM;
    END;
  END LOOP;
END $$;

-- count columns (name ending _n, not estimated / mean values) that are double precision but hold only whole numbers -> integer
DO $$
DECLARE r record; nonint bigint; mx double precision;
BEGIN
  FOR r IN SELECT c.table_name, c.column_name FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
           WHERE c.table_schema = 'ana' AND t.table_type = 'BASE TABLE' AND c.data_type = 'double precision'
             AND c.column_name ~ '_n$' AND c.column_name !~ '(_estimated_n|_mean_n)$'
  LOOP
    BEGIN
      EXECUTE format('SELECT count(*) FILTER (WHERE %I <> round(%I)), max(abs(%I)) FROM ana.%I', r.column_name, r.column_name, r.column_name, r.table_name) INTO nonint, mx;
      IF nonint = 0 AND coalesce(mx, 0) < 2147483647 THEN
        EXECUTE format('ALTER TABLE ana.%I ALTER COLUMN %I TYPE integer USING round(%I)::integer', r.table_name, r.column_name, r.column_name);
      END IF;
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'count harmonisation skipped ana.%.%: %', r.table_name, r.column_name, SQLERRM;
    END;
  END LOOP;
END $$;
