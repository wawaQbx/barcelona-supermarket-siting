-- generic test: no two rows share the same combination of the given columns (composite primary key).
-- Usage in a yml file:  tests: [{unique_combination: {columns: "seccio_censal, brand_group"}}]
{% test unique_combination(model, columns) %}
SELECT {{ columns }}, count(*) AS n_rows
FROM {{ model }}
GROUP BY {{ columns }}
HAVING count(*) > 1
{% endtest %}
