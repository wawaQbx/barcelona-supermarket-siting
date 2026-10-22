-- dbt's default puts a model with +schema: ana into "<target schema>_ana" (here dbt_ana).
-- This project wants the schema name exactly as written: +schema: ana -> ana, +schema: dbt_int -> dbt_int; no +schema -> target schema (dbt).
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
