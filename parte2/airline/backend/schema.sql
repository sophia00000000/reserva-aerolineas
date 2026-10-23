CREATE TABLE IF NOT EXISTS flights (
  flight_id   TEXT PRIMARY KEY,
  route       TEXT NOT NULL,
  flight_date DATE NOT NULL,
  capacity    INT  NOT NULL CHECK (capacity >= 0),
  seats_sold  INT  NOT NULL DEFAULT 0,
  price_cents BIGINT NOT NULL,
  CHECK (seats_sold <= capacity)          -- segunda barrera contra sobreventa
);
CREATE INDEX IF NOT EXISTS idx_flights_search ON flights (route, flight_date);

CREATE TABLE IF NOT EXISTS reservations (
  reservation_id TEXT PRIMARY KEY,
  flight_id      TEXT NOT NULL REFERENCES flights(flight_id),
  passenger_name TEXT NOT NULL,
  fare_class     TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'CONFIRMED',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
