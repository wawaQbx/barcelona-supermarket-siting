-- stores per district and chain; depends on stg_city_stores (dbt runs it first because of ref())
select d.nom_districte, s.brand_group, count(*) as stores_n
from {{ ref('stg_city_stores') }} s
join {{ source('raw', 'adm_units_polygons') }} u on u.tipus_ua = 'SEC_CENS' and ST_Intersects(u.geom, s.geom)
join {{ source('ana', 'dim_district') }} d on d.codi_districte = u.codi_districte
group by 1, 2
