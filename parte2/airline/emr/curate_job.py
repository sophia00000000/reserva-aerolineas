"""Job PySpark (EMR): aplica C1-C5, escribe Parquet particionado por mes y la tabla de metricas.
Uso: spark-submit curate_job.py s3://B/raw/ s3://B/curated s3://B/metrics
AJUSTA los nombres de columna si el CSV de tu semilla es distinto (mira el header con `head`)."""
import sys
from pyspark.sql import SparkSession, Window, functions as F

raw, curated_out, metrics_out = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
spark = SparkSession.builder.appName("airline-curate").getOrCreate()


def clean_route(c):                       # C1: quitar TODO espacio y mayusculas
    return F.upper(F.regexp_replace(F.col(c), r"\s+", ""))


# ---------- vuelos (necesarios para el mes y la capacidad) ----------
flights = (spark.read.option("header", True).csv(f"{raw}/flights*")
           .select("flight_id",
                   clean_route("route").alias("f_route"),
                   F.to_date("flight_date").alias("flight_date"),
                   F.col("capacity").cast("long").alias("capacity"))
           .dropDuplicates(["flight_id"]))          # cada vuelo cuenta una sola vez

# ---------- reservas ----------
res = (spark.read.option("header", True).csv(f"{raw}/reservations*")
       .withColumn("_mid", F.monotonically_increasing_id()))   # orden de aparicion (para C5)
j = res.join(flights, "flight_id", "left")
route_col = (F.coalesce(clean_route("route"), F.col("f_route"))
             if "route" in res.columns else F.col("f_route"))

c = (j.withColumn("route", route_col)                                              # C1
      .withColumn("status", F.upper(F.regexp_replace(F.col("status"), r"^\s+|\s+$", "")))  # C2
      .filter(F.col("status").isin("CONFIRMED", "CANCELLED"))                      # C3
      .withColumn("price_cents", F.col("price_cents").cast("long"))
      .filter(F.col("price_cents").isNotNull() & (F.col("price_cents") > 0))       # C4
      .withColumn("_rn", F.row_number().over(
          Window.partitionBy("reservation_id").orderBy("_mid")))
      .filter(F.col("_rn") == 1)                                                   # C5
      .withColumn("month", F.date_format("flight_date", "yyyy-MM"))
      .filter(F.col("month").isNotNull()))

curated = c.select("reservation_id", "flight_id", "route", "fare_class",
                   "price_cents", "status", "month")
(curated.repartition("month").write.mode("overwrite")
        .partitionBy("month").parquet(curated_out))          # 24 carpetas month=YYYY-MM

# ---------- metricas ruta-mes ----------
cap = (flights.withColumn("month", F.date_format("flight_date", "yyyy-MM"))
       .groupBy(F.col("f_route").alias("route"), "month")
       .agg(F.sum("capacity").alias("seats_capacity")))
conf = F.col("status") == "CONFIRMED"
sold = (curated.groupBy("route", "month").agg(
        F.sum(F.when(conf, 1).otherwise(0)).alias("seats_sold"),
        F.sum(F.when(conf, F.col("price_cents")).otherwise(0)).alias("revenue_cents"),
        F.sum(F.when(~conf, 1).otherwise(0)).alias("cancellations")))
m = (cap.join(sold, ["route", "month"], "left").fillna(0, ["seats_sold", "revenue_cents", "cancellations"])
     .withColumn("bookings", F.col("seats_sold"))
     .withColumn("occupancy", F.col("seats_sold") / F.col("seats_capacity")))
m = m.select("route", "month",
             F.col("seats_capacity").cast("long"), F.col("seats_sold").cast("long"),
             F.col("occupancy").cast("double"), F.col("revenue_cents").cast("long"),
             F.col("bookings").cast("long"), F.col("cancellations").cast("long"))
m.coalesce(1).write.mode("overwrite").parquet(metrics_out)
spark.stop()
