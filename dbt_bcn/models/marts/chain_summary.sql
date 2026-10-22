-- per chain: city stores, stores with an opening date, average first census year
select brand_group,
       count(*)                                         as stores_n,
       count(first_seen_census_year)                    as stores_dated_n,
       round(avg(first_seen_census_year))::integer      as avg_first_seen_year
from {{ ref('stg_city_stores') }}
group by brand_group
order by stores_n desc