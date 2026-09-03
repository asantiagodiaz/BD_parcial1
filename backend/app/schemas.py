"""Esquemas Pydantic - contratos de entrada/salida de la API."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Busqueda de vuelos (FR-01, FR-02, FR-03)
# --------------------------------------------------------------------------- #


class TarifaOut(BaseModel):
    id_tarifa: int
    clase_tarifa: str
    cabina: str
    monto_precio: float
    moneda: str
    es_reembolsable: bool


class TramoOut(BaseModel):
    id_instancia_vuelo: int
    numero_vuelo: str
    iata_origen: str
    iata_destino: str
    salida_utc: dt.datetime
    llegada_utc: dt.datetime
    cabina: str
    asientos_disponibles: int
    tarifa: TarifaOut


class OpcionVueloOut(BaseModel):
    """Un itinerario ofrecido: directo (1 tramo) o con escala (2 tramos)."""

    tramos: list[TramoOut]
    escalas: int
    precio_total: float
    moneda: str


class BusquedaResultado(BaseModel):
    opciones: list[OpcionVueloOut]


# --------------------------------------------------------------------------- #
# Creacion de reserva (FR-04, FR-05, FR-06)
# --------------------------------------------------------------------------- #


class PasajeroIn(BaseModel):
    tipo_documento: str
    numero_documento: str
    nombre_completo: str
    fecha_nacimiento: dt.date | None = None
    correo: str | None = None
    telefono: str | None = None
    es_contacto_principal: bool = False


class SegmentoIn(BaseModel):
    id_instancia_vuelo: int
    cabina: str
    id_tarifa: int


class ReservaIn(BaseModel):
    segmentos: list[SegmentoIn] = Field(min_length=1)
    pasajeros: list[PasajeroIn] = Field(min_length=1)
    canal: str = "DIRECTO"
    id_agencia: int | None = None


# --------------------------------------------------------------------------- #
# Salida de reserva (FR-12)
# --------------------------------------------------------------------------- #


class SegmentoOut(BaseModel):
    secuencia: int
    id_instancia_vuelo: int
    numero_vuelo: str
    iata_origen: str
    iata_destino: str
    salida_utc: dt.datetime
    llegada_utc: dt.datetime
    cabina: str
    monto_segmento: float


class PasajeroOut(BaseModel):
    nombre_completo: str
    tipo_documento: str
    numero_documento: str
    es_contacto_principal: bool


class PagoOut(BaseModel):
    proveedor: str
    estado: str
    monto: float
    moneda: str
    creado_en: dt.datetime


class EventoOut(BaseModel):
    tipo_evento: str
    tipo_actor: str
    ocurrido_en: dt.datetime
    contenido: dict | None = None


class ReservaOut(BaseModel):
    codigo_reserva: str
    canal: str
    estado: str
    retenida_hasta: dt.datetime | None
    monto_total: float
    moneda: str
    monto_comision: float
    creada_en: dt.datetime
    iata_origen: str
    iata_destino: str
    segmentos: list[SegmentoOut]
    pasajeros: list[PasajeroOut]
    pagos: list[PagoOut]
    historial: list[EventoOut]


class ReservaCreada(BaseModel):
    codigo_reserva: str
    estado: str
    retenida_hasta: dt.datetime | None
    monto_total: float
    moneda: str


class DisponibilidadOut(BaseModel):
    id_instancia_vuelo: int
    cabina: str
    asientos_disponibles: int
