-- one row per chain store inside the city (cleaned view of ana.store_points, which is now itself a dbt model -> ref)
select store_id, brand_group, ensenya, store_type, first_seen_census_year, geom
from {{ ref('store_points') }}
where in_city
