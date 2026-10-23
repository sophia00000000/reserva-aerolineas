-- Ejecutar en la consola de Athena, UNA sentencia a la vez. Reemplaza BUCKET.
-- Tus datos van de 2023-01 a 2024-12 (24 meses), por eso el rango de abajo.

CREATE DATABASE IF NOT EXISTS airline_analytics;

CREATE EXTERNAL TABLE IF NOT EXISTS airline_analytics.reservations_curated (
  reservation_id string,
  flight_id string,
  route string,
  fare_class string,
  price_cents bigint,
  status string
)
PARTITIONED BY (month string)
STORED AS PARQUET
LOCATION 's3://aeronaves20/parcial2/curated/'
TBLPROPERTIES (
  'projection.enabled'='true',
  'projection.month.type'='date',
  'projection.month.format'='yyyy-MM',
  'projection.month.range'='2023-01,2024-12',
  'projection.month.interval'='1',
  'projection.month.interval.unit'='MONTHS',
  'storage.location.template'='s3://aeronaves20/parcial2/curated/month=${month}'
);

CREATE EXTERNAL TABLE IF NOT EXISTS airline_analytics.route_month_metrics (
  route string,
  month string,
  seats_capacity bigint,
  seats_sold bigint,
  occupancy double,
  revenue_cents bigint,
  bookings bigint,
  cancellations bigint
)
STORED AS PARQUET
LOCATION 's3://aeronaves20/parcial2/metrics/';

-- Verificacion: top-10 rutas por ocupacion (global)
SELECT route, SUM(seats_sold)*1.0/SUM(seats_capacity) AS occupancy
FROM airline_analytics.route_month_metrics GROUP BY route ORDER BY occupancy DESC LIMIT 10;
