from datetime import date
from typing import List, Optional
from pydantic import BaseModel

# Schemas for the API responses and requests
# These classes define the structure of the data that will be sent to and received from the API.

class VueloDisponible(BaseModel):
    id_instancia_vuelo: int
    numero_vuelo: str
    origen: str
    destino: str
    fecha_vuelo: date
    hora_salida_local: str
    clase_asiento: str
    id_tarifa: int
    precio: float
    asientos_disponibles: int

# Schemas for creating and returning reservations
class TramoInput(BaseModel):
    id_instancia_vuelo: int
    id_tarifa: int
    clase_asiento: str
    orden_tramo: int

# Schemas for creating and returning reservations
class ReservaCreate(BaseModel):
    id_pasajero: int
    tipo_origen: str  # 'directo' | 'agencia'
    id_agencia: Optional[int] = None
    metodo_pago: str
    tramos: List[TramoInput]

# Schemas for creating and returning reservations
class ReservaOut(BaseModel):
    id_reserva: int
    estado: str
    monto_total: float
    tramos: List[TramoInput]
