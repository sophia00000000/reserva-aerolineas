from datetime import date
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from database import engine
from schemas import ReservaCreate, ReservaOut, VueloDisponible

app = FastAPI(title="API Sistema de Reservas Aerolínea")


@app.get("/vuelos/buscar", response_model=List[VueloDisponible])
def buscar_vuelos(
    origen: str,
    destino: str,
    fecha: date,
    clase_asiento: Optional[str] = None,
):
    query = text("""
        SELECT
            iv.id_instancia_vuelo,
            vp.numero_vuelo,
            vp.codigo_aeropuerto_origen  AS origen,
            vp.codigo_aeropuerto_destino AS destino,
            iv.fecha_vuelo,
            vp.hora_salida_local::text   AS hora_salida_local,
            t.clase_asiento,
            t.id_tarifa,
            t.precio,
            (inv.asientos_totales - inv.asientos_vendidos) AS asientos_disponibles
        FROM instancia_vuelo iv
        JOIN vuelo_programado vp ON vp.id_vuelo_programado = iv.id_vuelo_programado
        JOIN tarifa t ON t.id_instancia_vuelo = iv.id_instancia_vuelo
        JOIN inventario_asientos inv
             ON inv.id_instancia_vuelo = iv.id_instancia_vuelo
            AND inv.clase_asiento = t.clase_asiento
        WHERE vp.codigo_aeropuerto_origen = :origen
          AND vp.codigo_aeropuerto_destino = :destino
          AND iv.fecha_vuelo = :fecha
          AND iv.estado = 'programado'
          AND (inv.asientos_totales - inv.asientos_vendidos) > 0
          AND (:clase_asiento IS NULL OR t.clase_asiento = :clase_asiento)
        ORDER BY t.precio ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {
            "origen": origen,
            "destino": destino,
            "fecha": fecha,
            "clase_asiento": clase_asiento,
        }).mappings().all()

    return [dict(r) for r in rows]


@app.post("/reservas", response_model=ReservaOut, status_code=201)
def crear_reserva(payload: ReservaCreate):
    if payload.tipo_origen not in ("directo", "agencia"):
        raise HTTPException(400, "tipo_origen debe ser 'directo' o 'agencia'")
    if payload.tipo_origen == "agencia" and not payload.id_agencia:
        raise HTTPException(400, "id_agencia es obligatorio cuando tipo_origen='agencia'")
    if not payload.tramos:
        raise HTTPException(400, "La reserva debe tener al menos un tramo")

    # engine.begin() = una sola transacción para TODO el bloque.
    # Si algo falla (incluida una HTTPException), hace rollback automático.
    with engine.begin() as conn:
        monto_total = 0.0
        precios_tramo = []

        # 1. Bloqueo optimista del inventario, tramo por tramo
        for tramo in payload.tramos:
            result = conn.execute(text("""
                UPDATE inventario_asientos
                SET asientos_vendidos = asientos_vendidos + 1,
                    version_bloqueo = version_bloqueo + 1
                WHERE id_instancia_vuelo = :instancia
                  AND clase_asiento = :clase
                  AND asientos_vendidos < asientos_totales
            """), {"instancia": tramo.id_instancia_vuelo, "clase": tramo.clase_asiento})

            if result.rowcount == 0:
                # rowcount 0 = ya no hay cupo (o alguien más lo tomó justo antes)
                raise HTTPException(
                    status_code=409,
                    detail=f"Sin cupo disponible en instancia_vuelo="
                           f"{tramo.id_instancia_vuelo}, clase={tramo.clase_asiento}",
                )

            precio_row = conn.execute(
                text("SELECT precio FROM tarifa WHERE id_tarifa = :id"),
                {"id": tramo.id_tarifa},
            ).one()
            precios_tramo.append(float(precio_row.precio))
            monto_total += float(precio_row.precio)

        # 2. Crear la reserva
        id_reserva = conn.execute(text("""
            INSERT INTO reserva (id_pasajero, tipo_origen, id_agencia, estado, fecha_creacion)
            VALUES (:pasajero, :tipo_origen, :agencia, 'confirmada', now())
            RETURNING id_reserva
        """), {
            "pasajero": payload.id_pasajero,
            "tipo_origen": payload.tipo_origen,
            "agencia": payload.id_agencia,
        }).scalar_one()

        # 3. Crear cada tramo_reserva
        for tramo, precio in zip(payload.tramos, precios_tramo):
            conn.execute(text("""
                INSERT INTO tramo_reserva
                    (id_reserva, id_instancia_vuelo, id_tarifa, clase_asiento, orden_tramo, precio_aplicado)
                VALUES (:reserva, :instancia, :tarifa, :clase, :orden, :precio)
            """), {
                "reserva": id_reserva,
                "instancia": tramo.id_instancia_vuelo,
                "tarifa": tramo.id_tarifa,
                "clase": tramo.clase_asiento,
                "orden": tramo.orden_tramo,
                "precio": precio,
            })

        # 4. Crear el pago (atómico junto con la reserva)
        conn.execute(text("""
            INSERT INTO pago (id_reserva, monto, moneda, metodo_pago, estado, fecha_pago)
            VALUES (:reserva, :monto, 'COP', :metodo, 'aprobado', now())
        """), {
            "reserva": id_reserva,
            "monto": monto_total,
            "metodo": payload.metodo_pago,
        })

        # 5. Historial de auditoría
        conn.execute(text("""
            INSERT INTO historial_estado_reserva
                (id_reserva, estado_anterior, estado_nuevo, fecha_cambio, tipo_actor, id_actor)
            VALUES (:reserva, NULL, 'confirmada', now(), :actor, :id_actor)
        """), {
            "reserva": id_reserva,
            "actor": "agencia" if payload.tipo_origen == "agencia" else "pasajero",
            "id_actor": payload.id_agencia or payload.id_pasajero,
        })

    return {
        "id_reserva": id_reserva,
        "estado": "confirmada",
        "monto_total": monto_total,
        "tramos": payload.tramos,
    }


@app.get("/reservas/{id_reserva}")
def consultar_reserva(id_reserva: int):
    with engine.connect() as conn:
        reserva = conn.execute(text("""
            SELECT id_reserva, id_pasajero, tipo_origen, id_agencia, estado, fecha_creacion
            FROM reserva WHERE id_reserva = :id
        """), {"id": id_reserva}).mappings().first()

        if not reserva:
            raise HTTPException(404, "Reserva no encontrada")

        tramos = conn.execute(text("""
            SELECT tr.id_tramo_reserva, tr.id_instancia_vuelo, tr.clase_asiento,
                   tr.orden_tramo, tr.precio_aplicado, vp.numero_vuelo, iv.fecha_vuelo
            FROM tramo_reserva tr
            JOIN instancia_vuelo iv ON iv.id_instancia_vuelo = tr.id_instancia_vuelo
            JOIN vuelo_programado vp ON vp.id_vuelo_programado = iv.id_vuelo_programado
            WHERE tr.id_reserva = :id
            ORDER BY tr.orden_tramo
        """), {"id": id_reserva}).mappings().all()

        pago = conn.execute(text("""
            SELECT monto, moneda, metodo_pago, estado, fecha_pago
            FROM pago WHERE id_reserva = :id
        """), {"id": id_reserva}).mappings().first()

    return {
        "reserva": dict(reserva),
        "tramos": [dict(t) for t in tramos],
        "pago": dict(pago) if pago else None,
    }
