-- post_hook that adds a primary key to the table a model has just built.
-- Runs AFTER the commit (after_commit): by then dbt has dropped the previous version of the table, whose index already uses the name <table>_pkey.
-- Usage in a model:  {{ config(post_hook=primary_key('seccio_censal, brand_group')) }}
{% macro primary_key(columns) -%}
    {{ return(after_commit('ALTER TABLE {{ this }} ADD PRIMARY KEY (' ~ columns ~ ')')) }}
{%- endmacro %}

-- post_hook that refreshes the planner statistics of a helper table (spatial joins on it are planned badly without them)
{% macro analyze_this() -%}
    {{ return(after_commit('ANALYZE {{ this }}')) }}
{%- endmacro %}
