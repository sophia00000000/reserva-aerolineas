"""
Prueba de concurrencia para 5.6.

Antes de correr esto:
  1. Deja SOLO 1 asiento disponible en un registro de inventario_asientos de prueba:
     UPDATE inventario_asientos
     SET asientos_totales = 1, asientos_vendidos = 0, version_bloqueo = 0
     WHERE id_inventario_asientos = 1;
  2. Ajusta el payload de abajo con datos reales que existan en tu base
     (id_pasajero, id_instancia_vuelo, id_tarifa, clase_asiento deben existir).

Ejecutar: python test_concurrencia.py
Resultado esperado: una respuesta 201 y una respuesta 409.
Toma captura de esta salida como evidencia del entregable 5.6.
"""

import threading
import httpx

BASE_URL = "http://localhost:8000"  # o http://<IP-publica-EC2>:8000 si pruebas desde otra máquina

payload = {
    "id_pasajero": 1,
    "tipo_origen": "directo",
    "id_agencia": None,
    "metodo_pago": "tarjeta_credito",
    "tramos": [
        {
            "id_instancia_vuelo": 1,
            "id_tarifa": 1,
            "clase_asiento": "economica",
            "orden_tramo": 1,
        }
    ],
}

resultados = []


def reservar(etiqueta):
    with httpx.Client() as client:
        r = client.post(f"{BASE_URL}/reservas", json=payload, timeout=10)
        resultados.append((etiqueta, r.status_code, r.json()))


t1 = threading.Thread(target=reservar, args=("hilo-1",))
t2 = threading.Thread(target=reservar, args=("hilo-2",))

t1.start()
t2.start()
t1.join()
t2.join()

print("\n=== RESULTADO DE LA PRUEBA DE CONCURRENCIA ===")
for etiqueta, status, body in resultados:
    print(f"{etiqueta}: HTTP {status} -> {body}")

codigos = sorted(r[1] for r in resultados)
if codigos == [201, 409]:
    print("\nCorrecto: una reserva se confirmó (201) y la otra fue rechazada (409). No hubo sobreventa.")
else:
    print(f"\nRevisar: se esperaban códigos [201, 409] y se obtuvieron {codigos}.")
