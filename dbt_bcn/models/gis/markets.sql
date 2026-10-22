-- VISUALISATION LAYER (QGIS + dashboard): a curated copy of ana.market_supermarkets. Do NOT use for modelling.
-- One row per municipal market (43; food_market = 39): chain stores at the market, fresh-food shops around it 2016-2024, lon / lat for BI tools.
{{ config(post_hook=primary_key('nom_mercat'), indexes=[{'columns': ['geom'], 'type': 'gist'}]) }}
SELECT nom_mercat, nom_barri, nom_districte, food_market, codi_barri,
       chain_stores_50m_n, chain_stores_50m, chain_stores_100m_n, chain_stores_300m_n, nearest_chain_store_m, chain_openings_2016_2024_300m_n,
       fresh_shops_ring_100_400m_2016_n, fresh_shops_ring_100_400m_2019_n, fresh_shops_ring_100_400m_2022_n, fresh_shops_ring_100_400m_2024_n,
       ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat,
       geom
FROM {{ ref('market_supermarkets') }}
