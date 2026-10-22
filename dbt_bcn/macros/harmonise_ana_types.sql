-- Type harmonisation of every table of schemas ana and gis (dbt models and the Python / import tables), run once at the END of dbt run / dbt build
-- (on-run-end in dbt_project.yml). Policy (README section 4): counts / people / years -> integer; continuous measures -> double precision.
-- SQL arithmetic produces numeric (round(..., 2)) and bigint (count / sum), so: numeric -> double precision; bigint -> integer when all values fit;
-- count columns (name ending _n, not *_estimated_n / *_mean_n) that are double precision but hold only whole numbers -> integer.
-- A column used by a view of another schema cannot change type: it is reported (NOTICE) and skipped.
{% macro harmonise_ana_types() %}
{% if flags.WHICH in ('run', 'build') %}
DO $$
DECLARE r record; mx numeric;
BEGIN
  FOR r IN SELECT c.table_schema, c.table_name, c.column_name, c.data_type
           FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
           WHERE c.table_schema IN ('ana', 'gis') AND t.table_type = 'BASE TABLE' AND c.data_type IN ('numeric', 'bigint')
  LOOP
    BEGIN
      IF r.data_type = 'numeric' THEN
        EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I TYPE double precision', r.table_schema, r.table_name, r.column_name);
      ELSE
        EXECUTE format('SELECT max(abs(%I)) FROM %I.%I', r.column_name, r.table_schema, r.table_name) INTO mx;
        IF coalesce(mx, 0) < 2147483647 THEN
          EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I TYPE integer', r.table_schema, r.table_name, r.column_name);
        END IF;
      END IF;
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'type harmonisation skipped %.%.% (%): %', r.table_schema, r.table_name, r.column_name, r.data_type, SQLERRM;
    END;
  END LOOP;
END $$;
DO $$
DECLARE r record; nonint bigint; mx double precision;
BEGIN
  FOR r IN SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
           WHERE c.table_schema IN ('ana', 'gis') AND t.table_type = 'BASE TABLE' AND c.data_type = 'double precision'
             AND c.column_name ~ '_n$' AND c.column_name !~ '(_estimated_n|_mean_n)$'
  LOOP
    BEGIN
      EXECUTE format('SELECT count(*) FILTER (WHERE %I <> round(%I)), max(abs(%I)) FROM %I.%I', r.column_name, r.column_name, r.column_name, r.table_schema, r.table_name) INTO nonint, mx;
      IF nonint = 0 AND coalesce(mx, 0) < 2147483647 THEN
        EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I TYPE integer USING round(%I)::integer', r.table_schema, r.table_name, r.column_name, r.column_name);
      END IF;
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'count harmonisation skipped %.%.%: %', r.table_schema, r.table_name, r.column_name, SQLERRM;
    END;
  END LOOP;
END $$;
{% else %}
SELECT 1  -- dbt test / compile / docs: nothing to harmonise
{% endif %}
{% endmacro %}
