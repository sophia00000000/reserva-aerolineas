# Guía v2 — Parcial 2 (Panel gerencial de ocupación)

**Qué quedó probado y qué no.** Probé en mi entorno, con tu harness real: R1, R2 y R3 pasan contra este backend (50 peticiones simultáneas, exactamente 1 o K reservas), y el job de PySpark reproduce **exactamente** la respuesta del generador (filas, ingresos por mes y métricas por ruta). **No pude probar** lo que depende de tu cuenta AWS (script de la EC2, clúster EMR, Athena/Glue) ni el navegador (R8/R9). Si algo falla ahí, pégame el error.

**Dónde se hace cada cosa**
- **Tu PC:** generar los datos, subirlos a S3 y correr `pytest` (el harness abre un navegador real y necesita ~2 GB de RAM para calcular las respuestas correctas).
- **La EC2 (una sola):** solo corre el backend, el frontend y PostgreSQL. No generes datos ahí ni crees una segunda EC2: el harness estima el costo con **todas** las EC2 encendidas y una segunda te hace fallar R12.
- **AWS (consola o CLI):** S3, EMR, Glue y Athena.

## 1. Preparar tu PC
Verifica (abre una terminal: *Símbolo del sistema/PowerShell* en Windows, *Terminal* en Mac/Linux):
```
python --version      # necesitas 3.10 o superior (en Mac/Linux puede ser python3)
aws --version
```
Si falta algo: **Python** desde python.org/downloads (en Windows marca "Add Python to PATH"); **AWS CLI v2** desde aws.amazon.com/cli (instalador para tu sistema).

Descomprime `parcial2-harness-estudiantes.zip`, entra a la carpeta `parcial2-harness` desde la terminal y ejecuta:
```
pip install -r requirements.txt
playwright install chromium
```

## 2. Credenciales del Learner Lab en tu PC
1. Start Lab → cuando el punto esté verde, **AWS Details → AWS CLI → Show**.
2. Pega ese bloque completo (`[default]`, access key, secret y session token) en el archivo `.aws/credentials` de tu carpeta de usuario (créalo si no existe).
3. Ejecuta `aws configure set region us-east-1` y comprueba con `aws sts get-caller-identity`.
Estas credenciales **caducan** cuando termina la sesión del lab: repite el paso 2 cada vez.

## 3. Generar los datos y subirlos a tu bucket
Dentro de `parcial2-harness` (reemplaza TU_SEED y TU_BUCKET):
```
python -m airline_data.generate --seed TU_SEED --rows 2000000 --out raw/
aws s3 sync raw/ s3://TU_BUCKET/raw/
aws s3 ls s3://TU_BUCKET/raw/
```
Debes ver `flights.csv` y `reservations.csv`. Ya confirmé sus columnas: `flights(flight_id, route, flight_date, capacity)` y `reservations(reservation_id, flight_id, fare_class, price_cents, status, days_before_departure)`. Tus datos cubren **2023-01 a 2024-12**.

## 4. La EC2 (backend + frontend + base de datos)
1. [Consola] EC2 → **Launch instance**: nombre `airline-server`; **Amazon Linux 2023**; **t3.small**; *Proceed without a key pair*; en Network settings activa **SSH desde My IP** y **HTTP desde Internet**; almacenamiento **10 GiB gp3**; en Advanced details → **IAM instance profile = LabInstanceProfile**.
2. EC2 → **Elastic IPs → Allocate → Associate** con tu instancia (así la IP no cambia al reiniciar).
3. [PC] Sube el código a tu bucket: en la consola de S3 entra a tu bucket, crea la carpeta `code` y sube `airline_parcial2.zip`.
4. [Consola] Instances → selecciona la instancia → **Connect → EC2 Instance Connect → Connect** (terminal en el navegador) y ejecuta:
```
sudo dnf install -y unzip
aws s3 cp s3://TU_BUCKET/code/airline_parcial2.zip . && unzip -o airline_parcial2.zip
sed -i 's#BUCKET#TU_BUCKET#' ~/airline/deploy/airline.service
bash ~/airline/deploy/setup_ec2.sh
```
Debe terminar con `{"status":"ok"} <- backend arriba`. Si falla: `sudo journalctl -u airline -n 50`.
5. Prueba en tu navegador: `http://TU_IP/` (pantalla de reservas) y `http://TU_IP/manager`.

## 5. EMR (limpieza con PySpark)
Desde **CloudShell** (icono `>_` en la consola) o tu PC. Sube a CloudShell la carpeta `airline` (o clónala desde S3 con `aws s3 cp` + `unzip`) y ejecuta:
```
cd airline && BUCKET=TU_BUCKET bash deploy/run_emr.sh
```
Crea 1 master + 1 core `m4.large`, corre el job y **se apaga solo**. Tarda 10–20 min. Verifica:
```
aws s3 ls s3://TU_BUCKET/curated/        # 24 carpetas month=YYYY-MM
aws s3 ls s3://TU_BUCKET/metrics/
aws emr list-clusters --active           # debe salir vacío
```
Si `--use-default-roles` falla, busca en IAM → Roles los de EMR y usa `--service-role` y `--ec2-attributes InstanceProfile=...`. Logs en `s3://TU_BUCKET/emr-logs/`.

## 6. Glue + Athena
1. [Consola] Athena → Query editor → **Settings → Manage** → *Query result location* = `s3://TU_BUCKET/athena-results/`. Usa el workgroup **primary**.
2. Abre `athena/ddl.sql`, reemplaza `BUCKET` por tu bucket y ejecútalo **una sentencia a la vez**. Crea la base `airline_analytics` y las dos tablas (el rango 2023-01..2024-12 ya está ajustado).
3. Comprueba: `SELECT count(*) FROM airline_analytics.reservations_curated;` y revisa **Glue → Data Catalog → Tables**.
4. Corrige el servicio si hace falta: `ATHENA_OUTPUT` en `/etc/systemd/system/airline.service` debe ser `s3://TU_BUCKET/athena-results/` (después `sudo systemctl daemon-reload && sudo systemctl restart airline`).
5. Prueba: `http://TU_IP/analytics/occupancy?route=BOG-MDE&month=2023-05` (usa una ruta de tu seed: míralas en `metrics` o en Athena). **No pongas caché**: R7 exige ver consultas en el historial de Athena.

## 7. Correr el harness (desde tu PC)
```
copy config.example.yaml config.yaml      # en Mac/Linux: cp
```
Edita `config.yaml` así (todo en el puerto 80, sin `:8000` ni `:3000`):
```yaml
team_id: "TU_EQUIPO"
seed: TU_SEED
backend:  {base_url: "http://TU_IP"}
frontend: {base_url: "http://TU_IP"}
aws:
  region: us-east-1
  athena_workgroup: primary
  athena_database: airline_analytics
  athena_output: "s3://TU_BUCKET/athena-results/"
  tables: {detail: reservations_curated, metrics: route_month_metrics}
cost_projection_file: cost_projection.yaml
```
Copia `cost_projection.yaml` a esa carpeta y ejecuta `pytest`. Se generan `report.md` y `report.json`. Al terminar: `aws emr list-clusters --active` vacío y **EC2 → Stop instance**.

## Notas útiles
- **Costo (R12):** el harness estima ~US$15.3/mes (1 EC2 t3.small + horas EMR) y tolera ±US$5.8 sobre el total declarado. Tu `cost_projection.yaml` suma 20.35, dentro del margen. Si cambias el tipo de EC2 o agregas recursos, recalcula.
- **Inconsistencia del profesor:** `contract/DATA.md` dice que `bookings` cuenta solo CONFIRMED, pero su `oracle.py` lo calcula con todas las reservas. Ningún test lo compara (solo `seats_sold` y `seats_capacity`); este proyecto sigue el contrato. Vale la pena mencionarlo en el documento.
- **R6:** el test de partición usa la tabla `reservations_curated`; la de métricas no necesita partición.
- **Pagos y auditoría del parcial 1** no están en este contrato; declara el modelo operativo simplificado como desviación.

## 8. Borrador de la Sección 5 (documento)

| Servicio | Alternativa | Requisito | Pilar(es) |
|---|---|---|---|
| EC2 t3.small (API + frontend + Postgres) | Elastic Beanstalk / ECS / RDS | R1, R2, R3, R8, R11, R12 | Optimización de costos, Excelencia operativa |
| PostgreSQL (en la EC2) | RDS, DynamoDB | R2 (UPDATE atómico) | Fiabilidad, Costos |
| S3 | HDFS/EBS | R4 | Fiabilidad, Costos, Sostenibilidad |
| EMR (2 × m4.large, auto-terminate) | Glue job, Athena CTAS | R4, R10 | Costos, Rendimiento |
| Glue Data Catalog | Crawler, Hive metastore | R5 | Excelencia operativa, Costos |
| Athena | Redshift, RDS | R6, R7 | Costos (pago por byte), Sostenibilidad |

Párrafos a desarrollar (1 por decisión, citando R y pilar):
- **Hosting**: una EC2 pequeña con todo; cumple R1/R2 porque la carga es baja y el cuello de botella es una sola fila de Postgres; se evita RDS/ALB/NAT por costo (R11/R12). Trade-off: menos disponibilidad (Fiabilidad) — aceptable en un MVP académico.
- **No-sobreventa (R2)**: `UPDATE ... WHERE seats_sold < capacity` atómico + `CHECK (seats_sold <= capacity)`. Es la evolución simplificada del *optimistic locking* del parcial 1: no necesita reintentos porque la condición se evalúa dentro del bloqueo de fila; 409 explícito, nunca 5xx.
- **Por qué EMR**: aplica C1–C5 sobre 2 M de filas, deduplica, une con vuelos, escribe Parquet por mes y precalcula métricas. Athena sola podría con CTAS, pero el curso exige EMR; Glue job sería equivalente (se descartó por requisito). Clúster (no Serverless) porque R11 fija m4.large; se apaga con `--auto-terminate` y se verifica con `list-clusters --active` (R10).
- **Layout**: Parquet columnar + compresión → Athena lee solo columnas usadas; partición por mes → una consulta mensual lee ~1/24 (R6); sin ella escanea todo, ×24 en costo/tiempo.
- **Panel**: el endpoint consulta Athena (latencia ~1–3 s, ~US$0.00005 por consulta con mínimo 10 MB, frescura = última corrida EMR). Caché no justificada: R7 exige consultas reales y el volumen es bajo.
- **Separación de cargas**: Postgres solo OLTP; analítica en S3/Athena, alimentada por EMR; el backend no ejecuta consultas pesadas.
- **Costo ×10**: datos ×10 → S3/EMR crecen casi lineal (centavos); consultas ×10 → Athena sigue siendo centavos gracias a Parquet+partición; EC2 no cambia. Sostenibilidad: clúster efímero y menos bytes escaneados = menos energía.
- Menciona en el documento: pagos y tabla de auditoría del parcial 1 quedan fuera de este contrato; el LabRole impide ver algunos recursos (marcados "not verified").

## 9. Preguntas típicas de la defensa
¿Por qué el UPDATE condicional no sobrevende? ¿Qué cambia si C3 acepta también `PENDING` (qué archivos/tablas/tests)? ¿Por qué `month` es partición y qué pasa sin ella? ¿Por qué no caché? ¿Cómo garantizas que EMR no queda vivo? ¿Qué pasa con la ocupación si cambia la definición a "no contar cancelaciones en capacidad"?
