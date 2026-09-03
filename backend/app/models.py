"""Modelos SQLAlchemy - implementan el modelo entidad-relacion de docs/03.

Nombres de tabla y columna en espanol, iguales al diccionario de datos de 5.3.
Cualquier desviacion frente a 5.3 se documenta en docs/03 seccion 5.3.7.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# --------------------------------------------------------------------------- #
# Catalogo / maestros
# --------------------------------------------------------------------------- #


class Aeropuerto(Base):
    __tablename__ = "aeropuerto"

    codigo_iata: Mapped[str] = mapped_column(String(3), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    ciudad: Mapped[str] = mapped_column(String(80), nullable=False)
    pais: Mapped[str] = mapped_column(String(2), nullable=False)
    zona_horaria: Mapped[str] = mapped_column(String(40), nullable=False)


class Ruta(Base):
    __tablename__ = "ruta"
    __table_args__ = (
        UniqueConstraint("iata_origen", "iata_destino", name="uq_ruta_origen_destino"),
    )

    id_ruta: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    iata_origen: Mapped[str] = mapped_column(ForeignKey("aeropuerto.codigo_iata"), nullable=False)
    iata_destino: Mapped[str] = mapped_column(ForeignKey("aeropuerto.codigo_iata"), nullable=False)
    distancia_km: Mapped[int | None] = mapped_column(Integer)


class Aeronave(Base):
    __tablename__ = "aeronave"

    id_aeronave: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    matricula: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    modelo: Mapped[str] = mapped_column(String(40), nullable=False)

    cabinas: Mapped[list[ConfigCabina]] = relationship(back_populates="aeronave")


class ConfigCabina(Base):
    __tablename__ = "config_cabina"
    __table_args__ = (
        UniqueConstraint("id_aeronave", "cabina", name="uq_config_cabina"),
        CheckConstraint("cabina in ('ECONOMICA','EJECUTIVA')", name="ck_config_cabina_valor"),
        CheckConstraint("num_asientos > 0", name="ck_config_cabina_asientos"),
    )

    id_config_cabina: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_aeronave: Mapped[int] = mapped_column(ForeignKey("aeronave.id_aeronave"), nullable=False)
    cabina: Mapped[str] = mapped_column(String(10), nullable=False)
    num_asientos: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    aeronave: Mapped[Aeronave] = relationship(back_populates="cabinas")


class Tarifa(Base):
    __tablename__ = "tarifa"
    __table_args__ = (CheckConstraint("monto_precio >= 0", name="ck_tarifa_precio"),)

    id_tarifa: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_ruta: Mapped[int] = mapped_column(ForeignKey("ruta.id_ruta"), nullable=False)
    cabina: Mapped[str] = mapped_column(String(10), nullable=False)
    clase_tarifa: Mapped[str] = mapped_column(String(20), nullable=False)
    dias_anticipacion_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dias_anticipacion_max: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    monto_precio: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, server_default="COP")
    es_reembolsable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    penalidad_cambio: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")


class Agencia(Base):
    __tablename__ = "agencia"

    id_agencia: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    nit: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    tasa_comision: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    tasa_descuento: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    esta_activa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Pasajero(Base):
    __tablename__ = "pasajero"
    __table_args__ = (
        UniqueConstraint("tipo_documento", "numero_documento", name="uq_pasajero_documento"),
    )

    id_pasajero: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo_documento: Mapped[str] = mapped_column(String(10), nullable=False)
    numero_documento: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(160), nullable=False)
    fecha_nacimiento: Mapped[dt.date | None] = mapped_column(Date)
    correo: Mapped[str | None] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(120))


class CuentaUsuario(Base):
    __tablename__ = "cuenta_usuario"

    id_cuenta_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correo: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    hash_contrasena: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    id_pasajero: Mapped[int | None] = mapped_column(ForeignKey("pasajero.id_pasajero"))
    id_agencia: Mapped[int | None] = mapped_column(ForeignKey("agencia.id_agencia"))


# --------------------------------------------------------------------------- #
# Programacion de vuelos
# --------------------------------------------------------------------------- #


class VueloProgramado(Base):
    __tablename__ = "vuelo_programado"

    id_vuelo_programado: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    numero_vuelo: Mapped[str] = mapped_column(String(6), nullable=False)
    id_ruta: Mapped[int] = mapped_column(ForeignKey("ruta.id_ruta"), nullable=False)
    id_aeronave: Mapped[int] = mapped_column(ForeignKey("aeronave.id_aeronave"), nullable=False)
    hora_salida_local: Mapped[dt.time] = mapped_column(Time, nullable=False)
    duracion_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dias_semana: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    vigente_desde: Mapped[dt.date] = mapped_column(Date, nullable=False)
    vigente_hasta: Mapped[dt.date] = mapped_column(Date, nullable=False)

    ruta: Mapped[Ruta] = relationship()
    aeronave: Mapped[Aeronave] = relationship()


class InstanciaVuelo(Base):
    __tablename__ = "instancia_vuelo"
    __table_args__ = (
        UniqueConstraint("id_vuelo_programado", "fecha_salida", name="uq_instancia_fecha"),
    )

    id_instancia_vuelo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_vuelo_programado: Mapped[int] = mapped_column(
        ForeignKey("vuelo_programado.id_vuelo_programado"), nullable=False
    )
    fecha_salida: Mapped[dt.date] = mapped_column(Date, nullable=False)
    salida_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    llegada_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PROGRAMADO")

    vuelo_programado: Mapped[VueloProgramado] = relationship()
    inventarios: Mapped[list[InventarioAsientos]] = relationship(back_populates="instancia_vuelo")


class InventarioAsientos(Base):
    """Punto UNICO de control de sobreventa (NFR-03).

    La transaccion de reserva bloquea la fila con SELECT ... FOR UPDATE
    (ver app/services/booking.py). El CHECK es la ultima barrera del motor.
    """

    __tablename__ = "inventario_asientos"
    __table_args__ = (
        UniqueConstraint("id_instancia_vuelo", "cabina", name="uq_inventario_vuelo_cabina"),
        CheckConstraint("asientos_vendidos >= 0", name="ck_inv_vendidos"),
        CheckConstraint("asientos_retenidos >= 0", name="ck_inv_retenidos"),
        CheckConstraint(
            "asientos_vendidos + asientos_retenidos <= asientos_totales",
            name="ck_inv_no_sobreventa",
        ),
    )

    id_inventario_asientos: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    id_instancia_vuelo: Mapped[int] = mapped_column(
        ForeignKey("instancia_vuelo.id_instancia_vuelo"), nullable=False
    )
    cabina: Mapped[str] = mapped_column(String(10), nullable=False)
    asientos_totales: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    asientos_vendidos: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    asientos_retenidos: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    instancia_vuelo: Mapped[InstanciaVuelo] = relationship(back_populates="inventarios")

    @property
    def disponibles(self) -> int:
        return self.asientos_totales - self.asientos_vendidos - self.asientos_retenidos


# --------------------------------------------------------------------------- #
# Nucleo de la reserva
# --------------------------------------------------------------------------- #


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (
        CheckConstraint("canal in ('DIRECTO','AGENCIA')", name="ck_reserva_canal"),
    )

    id_reserva: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo_reserva: Mapped[str] = mapped_column(String(6), nullable=False, unique=True)
    canal: Mapped[str] = mapped_column(String(10), nullable=False, server_default="DIRECTO")
    id_agencia: Mapped[int | None] = mapped_column(ForeignKey("agencia.id_agencia"))
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    retenida_hasta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    monto_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, server_default="COP")
    monto_comision: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    creada_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    itinerario: Mapped[Itinerario] = relationship(back_populates="reserva", uselist=False)
    pasajeros: Mapped[list[ReservaPasajero]] = relationship(back_populates="reserva")
    pagos: Mapped[list[Pago]] = relationship(back_populates="reserva")
    eventos: Mapped[list[EventoReserva]] = relationship(back_populates="reserva")


class ReservaPasajero(Base):
    __tablename__ = "reserva_pasajero"

    id_reserva: Mapped[int] = mapped_column(ForeignKey("reserva.id_reserva"), primary_key=True)
    id_pasajero: Mapped[int] = mapped_column(ForeignKey("pasajero.id_pasajero"), primary_key=True)
    es_contacto_principal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    reserva: Mapped[Reserva] = relationship(back_populates="pasajeros")
    pasajero: Mapped[Pasajero] = relationship()


class Itinerario(Base):
    __tablename__ = "itinerario"

    id_itinerario: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_reserva: Mapped[int] = mapped_column(
        ForeignKey("reserva.id_reserva"), nullable=False, unique=True
    )
    iata_origen: Mapped[str] = mapped_column(ForeignKey("aeropuerto.codigo_iata"), nullable=False)
    iata_destino: Mapped[str] = mapped_column(ForeignKey("aeropuerto.codigo_iata"), nullable=False)

    reserva: Mapped[Reserva] = relationship(back_populates="itinerario")
    segmentos: Mapped[list[SegmentoItinerario]] = relationship(
        back_populates="itinerario", order_by="SegmentoItinerario.secuencia"
    )


class SegmentoItinerario(Base):
    __tablename__ = "segmento_itinerario"
    __table_args__ = (
        UniqueConstraint("id_itinerario", "secuencia", name="uq_segmento_secuencia"),
    )

    id_segmento_itinerario: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    id_itinerario: Mapped[int] = mapped_column(ForeignKey("itinerario.id_itinerario"), nullable=False)
    secuencia: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    id_instancia_vuelo: Mapped[int] = mapped_column(
        ForeignKey("instancia_vuelo.id_instancia_vuelo"), nullable=False
    )
    cabina: Mapped[str] = mapped_column(String(10), nullable=False)
    id_tarifa: Mapped[int] = mapped_column(ForeignKey("tarifa.id_tarifa"), nullable=False)
    monto_segmento: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    itinerario: Mapped[Itinerario] = relationship(back_populates="segmentos")
    instancia_vuelo: Mapped[InstanciaVuelo] = relationship()
    tarifa: Mapped[Tarifa] = relationship()


class Billete(Base):
    __tablename__ = "billete"
    __table_args__ = (
        UniqueConstraint(
            "id_pasajero", "id_segmento_itinerario", name="uq_billete_pasajero_segmento"
        ),
    )

    id_billete: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    numero_billete: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
    id_reserva: Mapped[int] = mapped_column(ForeignKey("reserva.id_reserva"), nullable=False)
    id_pasajero: Mapped[int] = mapped_column(ForeignKey("pasajero.id_pasajero"), nullable=False)
    id_segmento_itinerario: Mapped[int] = mapped_column(
        ForeignKey("segmento_itinerario.id_segmento_itinerario"), nullable=False
    )
    estado: Mapped[str] = mapped_column(String(12), nullable=False, server_default="EMITIDO")


class Pago(Base):
    __tablename__ = "pago"

    id_pago: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_reserva: Mapped[int] = mapped_column(ForeignKey("reserva.id_reserva"), nullable=False)
    proveedor: Mapped[str] = mapped_column(String(30), nullable=False)
    referencia_proveedor: Mapped[str] = mapped_column(String(80), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, server_default="COP")
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    reserva: Mapped[Reserva] = relationship(back_populates="pagos")


class AsignacionAsiento(Base):
    __tablename__ = "asignacion_asiento"
    __table_args__ = (
        UniqueConstraint(
            "id_segmento_itinerario", "etiqueta_asiento", name="uq_asiento_segmento_etiqueta"
        ),
        UniqueConstraint(
            "id_segmento_itinerario", "id_pasajero", name="uq_asiento_segmento_pasajero"
        ),
    )

    id_asignacion_asiento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    id_segmento_itinerario: Mapped[int] = mapped_column(
        ForeignKey("segmento_itinerario.id_segmento_itinerario"), nullable=False
    )
    id_pasajero: Mapped[int] = mapped_column(ForeignKey("pasajero.id_pasajero"), nullable=False)
    etiqueta_asiento: Mapped[str] = mapped_column(String(4), nullable=False)
    asignado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EventoReserva(Base):
    """Bitacora append-only (NFR-09). No se hace UPDATE ni DELETE."""

    __tablename__ = "evento_reserva"

    id_evento_reserva: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_reserva: Mapped[int] = mapped_column(ForeignKey("reserva.id_reserva"), nullable=False)
    tipo_evento: Mapped[str] = mapped_column(String(24), nullable=False)
    contenido: Mapped[dict | None] = mapped_column(JSONB)
    tipo_actor: Mapped[str] = mapped_column(String(20), nullable=False)
    id_actor: Mapped[int | None] = mapped_column(BigInteger)
    ocurrido_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    reserva: Mapped[Reserva] = relationship(back_populates="eventos")
