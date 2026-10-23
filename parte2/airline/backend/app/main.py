import os, re, time, uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import boto3
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DSN = os.getenv("DATABASE_URL", "postgresql://airline:airline@127.0.0.1:5432/airline")
ATHENA_DB = os.getenv("ATHENA_DB", "airline_analytics")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT", "")          # s3://BUCKET/athena-results/
REGION = os.getenv("AWS_REGION", "us-east-1")
FRONT = Path(__file__).resolve().parents[2] / "frontend"

pool = ConnectionPool(DSN, min_size=4, max_size=15, timeout=30, open=False,
                      kwargs={"row_factory": dict_row})
athena = boto3.client("athena", region_name=REGION)


@asynccontextmanager
async def lifespan(app):
    pool.open()
    yield
    pool.close()


app = FastAPI(lifespan=lifespan)


def norm_route(s: str) -> str:               # regla C1 tambien en la API
    return re.sub(r"\s+", "", s).upper()


class FlightIn(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    capacity: int = Field(ge=0)
    price_cents: int


class ReservationIn(BaseModel):
    flight_id: str
    passenger_name: str
    fare_class: str = "ECONOMY"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/flights", status_code=201)
def create_flight(f: FlightIn):
    route = norm_route(f.route)
    with pool.connection() as c:
        row = c.execute(
            "INSERT INTO flights(flight_id,route,flight_date,capacity,price_cents) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING flight_id",
            (f.flight_id, route, f.flight_date, f.capacity, f.price_cents)).fetchone()
    if row is None:
        raise HTTPException(409, "flight already exists")
    return {"flight_id": f.flight_id, "route": route}


@app.get("/flights/search")
def search(origin: str, destination: str, date_: date = Query(alias="date")):
    route = norm_route(f"{origin}-{destination}")
    with pool.connection() as c:
        return c.execute(
            "SELECT flight_id, route, flight_date, capacity - seats_sold AS seats_available, price_cents "
            "FROM flights WHERE route=%s AND flight_date=%s AND seats_sold < capacity "
            "ORDER BY price_cents LIMIT 50", (route, date_)).fetchall()


@app.post("/reservations", status_code=201)
def reserve(r: ReservationIn):
    rid = str(uuid.uuid4())
    with pool.connection() as c:               # una sola transaccion
        # UPDATE condicional atomico: Postgres bloquea la fila, serializa a los
        # competidores y re-evalua "seats_sold < capacity" -> nunca sobrevende.
        got = c.execute(
            "UPDATE flights SET seats_sold = seats_sold + 1 "
            "WHERE flight_id=%s AND seats_sold < capacity RETURNING flight_id",
            (r.flight_id,)).fetchone()
        if got is None:
            exists = c.execute("SELECT 1 FROM flights WHERE flight_id=%s", (r.flight_id,)).fetchone()
            raise HTTPException(409 if exists else 404, "no seats" if exists else "unknown flight")
        c.execute("INSERT INTO reservations(reservation_id,flight_id,passenger_name,fare_class) "
                  "VALUES (%s,%s,%s,%s)", (rid, r.flight_id, r.passenger_name, r.fare_class))
    return {"reservation_id": rid, "flight_id": r.flight_id, "status": "CONFIRMED",
            "passenger_name": r.passenger_name}


@app.get("/reservations/{rid}")
def get_reservation(rid: str):
    with pool.connection() as c:
        row = c.execute("SELECT reservation_id, flight_id, status, passenger_name "
                        "FROM reservations WHERE reservation_id=%s", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@app.get("/analytics/occupancy")
def occupancy(route: str, month: str):
    route = norm_route(route)
    if not re.fullmatch(r"[A-Z0-9-]{3,20}", route) or not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(400, "bad route or month")       # evita inyeccion SQL
    sql = (f"SELECT seats_capacity, seats_sold, occupancy FROM {ATHENA_DB}.route_month_metrics "
           f"WHERE route='{route}' AND month='{month}' LIMIT 1")
    qid = athena.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": ATHENA_DB}, WorkGroup="primary",
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT})["QueryExecutionId"]
    state = "RUNNING"
    for _ in range(100):                                      # max ~40 s
        state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.4)
    if state != "SUCCEEDED":
        raise HTTPException(502, f"athena {state}")
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"][1:]
    if not rows:
        raise HTTPException(404, "no data")
    v = [d.get("VarCharValue") for d in rows[0]["Data"]]
    return {"route": route, "month": month, "occupancy": float(v[2]),
            "seats_sold": int(v[1]), "seats_capacity": int(v[0])}


@app.get("/")
def page_customer():
    return FileResponse(FRONT / "index.html")


@app.get("/manager")
def page_manager():
    return FileResponse(FRONT / "manager.html")
