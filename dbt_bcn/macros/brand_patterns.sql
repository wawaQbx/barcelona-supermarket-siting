-- Regular expressions that recognise each chain in the sign name (nom_local) of a census premise, as a VALUES list (brand_group, pattern).
-- Shared by store_points (dating of stores not dated by census_panel.py) and store_list_validation.
{% macro brand_patterns() -%}
(VALUES ('Condis', 'condis'), ('Dia', '^(d[ií]a\M|d[ií]a %|d[ií]a market|supermercados d[ií]a|la plaza de d[ií]a)'), ('Caprabo', 'caprabo'), ('Mercadona', 'mercadona'),
        ('Consum_Charter', 'charter|\mconsum\M'), ('BonPreu_Esclat', 'bon ?preu|esclat'), ('Lidl', '\mlidl'), ('Aldi', '\maldi\M'),
        ('Carrefour', 'carrefour'), ('Alcampo', 'alcampo|simply|sabeco')) v(brand_group, pattern)
{%- endmacro %}
