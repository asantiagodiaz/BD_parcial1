# 5.1 Requisitos funcionales (FR)

> Formato: `ID | Descripción | Actor involucrado | Prioridad`.
> Prioridad: **Alta** (MVP, imprescindible) · **Media** (deseable en la entrega) · **Baja** (diseñado, no implementado en el MVP).
> Referencias: los actores están definidos en [00-contexto-supuestos.md §0.3](00-contexto-supuestos.md). Los supuestos `Sx` también.

## 5.1.1 Decisiones sobre las preguntas guía

| Pregunta guía del enunciado | Decisión del equipo | FR relacionados |
|---|---|---|
| ¿Quiénes son los actores? ¿Mismo sistema o interfaces distintas? | 4 actores (Pasajero, Agente de agencia, Personal de aeropuerto, Administrador) sobre **un mismo backend monolítico** con **interfaces distintas** por rol. | Todos |
| ¿Reserva multi-tramo = una reserva con varios vuelos, o varias reservas encadenadas? | **Una sola `Reservation`** que contiene un **`Itinerary`** con varios **segmentos** (`ItinerarySegment`), cada uno ligado a una instancia de vuelo. La creación es **atómica**: o se confirman todos los segmentos o ninguno. | FR-04, FR-05 |
| ¿Se permite reservar sin pagar (hold), o el pago es atómico? | Se permite **hold temporal de 15 min** (estado `HELD`), luego expira y libera inventario (S4). El pago confirma la reserva (`CONFIRMED`). | FR-06, FR-07, FR-08 |
| ¿Qué pasa si el pasajero cancela o cambia de fecha? | **Cancelar**: libera inventario y registra evento + política de reembolso. **Cambio de fecha** = cancelar + reservar de nuevo, con penalización configurable (S2). | FR-09, FR-10 |
| ¿Las agencias tienen flujo distinto (descuento, comisión) o el mismo? | **Mismo flujo de reserva**; se marca `channel = AGENCY`, se aplica descuento/comisión configurable y se registra la agencia (S3). Sin API B2B separada en el MVP. | FR-04, FR-11 |

## 5.1.2 Tabla de requisitos funcionales

### Búsqueda y catálogo

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-01 | El sistema permite buscar vuelos **directos** por origen, destino, fecha y número de pasajeros, mostrando horario, aeronave y tarifas disponibles por cabina. | Pasajero, Agente de agencia | Alta |
| FR-02 | El sistema permite buscar itinerarios **con escalas** (al menos 1 conexión), combinando instancias de vuelo cuyo tiempo de conexión sea válido (mínimo configurable). | Pasajero, Agente de agencia | Alta |
| FR-03 | El sistema muestra, para cada resultado, el **desglose de tarifa** aplicable según la antelación de compra y la cabina (economía / negocios), y el precio total del itinerario. | Pasajero, Agente de agencia | Alta |

### Reserva y pago

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-04 | El sistema permite **crear una reserva** para uno o varios pasajeros sobre un itinerario de **uno o varios segmentos**, en **una sola transacción atómica**: si algún segmento no tiene inventario suficiente, no se crea ninguna parte de la reserva. | Pasajero, Agente de agencia | Alta |
| FR-05 | Al crear la reserva, el sistema **descuenta el inventario** de asientos de cada segmento (contador por cabina, S7) garantizando que **nunca se vendan más asientos de los que tiene la aeronave**, incluso ante solicitudes simultáneas. | Pasajero, Agente de agencia | Alta |
| FR-06 | El sistema permite crear la reserva en estado **`HELD`** (hold temporal de 15 min) sin pago inmediato; el inventario queda retenido durante ese tiempo. | Pasajero, Agente de agencia | Alta |
| FR-07 | Si una reserva `HELD` no se paga antes de expirar, el sistema **libera automáticamente** el inventario retenido y marca la reserva como `EXPIRED`. | Sistema (job) | Alta |
| FR-08 | El sistema permite **pagar** una reserva `HELD` a través de una pasarela externa; al confirmarse el pago la reserva pasa a **`CONFIRMED`** y se emiten los billetes (`Ticket`) por pasajero y segmento. | Pasajero, Agente de agencia | Alta |
| FR-09 | El sistema permite **cancelar** una reserva `CONFIRMED` o `HELD`: libera el inventario, registra el evento y calcula el reembolso según la política vigente. | Pasajero, Agente de agencia | Alta |
| FR-10 | El sistema permite **cambiar la fecha** de un itinerario ya confirmado como una operación de *cancelar + reservar* atómica, aplicando la penalización configurada. | Pasajero, Agente de agencia | Media |

### Consulta

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-12 | El sistema permite **consultar una reserva** por su código, devolviendo estado, pasajeros, segmentos, tarifas, pagos e historial de cambios. | Pasajero, Agente de agencia, Personal de aeropuerto | Alta |
| FR-13 | El sistema mantiene un **historial append-only** de todos los cambios de estado de una reserva (`ReservationEvent`) para auditoría. | Sistema | Alta |

### Canal de agencias

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-11 | El sistema registra, para cada reserva hecha por una agencia, la **agencia**, el **descuento** aplicado y la **comisión** devengada, sin alterar la regla de inventario. | Agente de agencia | Media |

### Check-in

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-14 | El sistema permite, en el **check-in**, asignar un asiento nominal (`SeatAssignment`) a un pasajero sobre un segmento confirmado, dentro de la cabina comprada. | Personal de aeropuerto | Baja |

### Administración y analítica

| ID | Descripción | Actor | Prioridad |
|---|---|---|---|
| FR-15 | El sistema permite al administrador gestionar el **catálogo**: aeropuertos, rutas, aeronaves y configuraciones de cabina. | Administrador | Media |
| FR-16 | El sistema permite definir **vuelos programados** (`ScheduledFlight`: ruta, hora, días de la semana, aeronave) y **generar automáticamente** las instancias de vuelo (`FlightInstance`) con su inventario para un rango de fechas. | Administrador | Media |
| FR-17 | El sistema permite gestionar **tarifas** (`Fare`) por ruta, cabina y ventana de antelación. | Administrador | Media |
| FR-18 | El sistema entrega a la gerencia comercial reportes de **ocupación por ruta**, **ingresos por tarifa** y **patrones de cancelación**, servidos desde la **base de datos analítica** alimentada por el proceso ETL (ver [07-aws-etl-glue-costos.md](07-aws-etl-glue-costos.md)). | Administrador | Alta |

## 5.1.3 Alcance de la implementación (5.6)

De la tabla anterior, la **primera implementación del backend** (sección 5.6) expone
como mínimo: **FR-01/FR-02** (buscar vuelos), **FR-04/FR-05/FR-06** (crear reserva con
control de concurrencia) y **FR-12** (consultar reserva). El resto queda diseñado y,
según el tiempo, parcialmente implementado (FR-07, FR-08, FR-09 como operaciones de apoyo).
