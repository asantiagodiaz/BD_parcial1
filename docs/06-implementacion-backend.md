# 5.6 Primera implementación del backend

> Código: [`backend/`](../backend/) · Guía de ejecución: [`backend/README.md`](../backend/README.md)
> Referencias: modelo en [03-modelo-entidad-relacion.md](03-modelo-entidad-relacion.md), arquitectura en [04-arquitectura-backend.md](04-arquitectura-backend.md), NFR en [02-requisitos-no-funcionales.md](02-requisitos-no-funcionales.md).

## 5.6.1 Alcance implementado

| Operación | Endpoint | FR | Estado |
|---|---|---|---|
| Buscar vuelos disponibles (directos + 1 escala) | `GET /flights/search` | FR-01, FR-02, FR-03 | ✅ |
| Crear reserva (multi-tramo, hold) con control de concurrencia | `POST /reservations` | FR-04, FR-05, FR-06 | ✅ |
| Consultar reserva existente (con historial) | `GET /reservations/{codigo}` | FR-12, FR-13 | ✅ |
| Disponibilidad puntual (polling del frontend) | `GET /flights/{id}/availability` | NFR-03 (best-effort) | ✅ |
| Salud del servicio | `GET /health` | NFR-05 | ✅ |

**Stack:** FastAPI + SQLAlchemy 2.0 + Alembic sobre **PostgreSQL 16**. Un solo
servicio (monolito modular, 5.4.1). Módulos implementados: `search`, `booking`
(dueño de la concurrencia), `db`, `config`, `models`, `schemas`.

**Base de datos:** implementa el modelo ER de 5.3 con **19 tablas**, en **3FN**,
con los `CHECK`, `UNIQUE` y FKs del diccionario de datos. Nivel de normalización y
motor son los definidos y justificados por el equipo en 5.3.

## 5.6.2 Mecanismo de concurrencia y cómo se probó

**Mecanismo (fiel a 5.4.2): bloqueo pesimista** — `SELECT ... FOR UPDATE` sobre las
filas de `inventario_asientos` de cada segmento, dentro de la transacción de
reserva, con orden determinista por `id_instancia_vuelo` (previene deadlock).
Código: [`backend/app/services/booking.py`](../backend/app/services/booking.py),
función `crear_reserva`.

**Barreras (defensa en profundidad):**
1. Validación en `booking`: `disponibles < num_pax` → **HTTP 409** (NFR-03).
2. `CHECK (asientos_vendidos + asientos_retenidos <= asientos_totales)` a nivel de
   motor (migración `0001`) — última barrera si algo se escapa de la lógica.
3. Trigger `evento_reserva_append_only` — rechaza `UPDATE`/`DELETE` sobre la
   bitácora de auditoría (NFR-09).

### Prueba automatizada 1 — capa de servicio, N hilos concurrentes

[`backend/tests/test_concurrencia.py`](../backend/tests/test_concurrencia.py).
20 hilos, **cada uno con su propia conexión/transacción a PostgreSQL** (como N
procesos web reales), intentan reservar el último asiento a la vez.

Evidencia — [`docs/evidencia/prueba-concurrencia.txt`](evidencia/prueba-concurrencia.txt):

```
================================================================
PRUEBA DE CONCURRENCIA  -  20 clientes por 1 asiento
================================================================
  reservas OK (hold)     : 1   ['OK:MXMVZ3']
  rechazos HTTP 409      : 19
  otros errores          : 0   []
  inventario final       : vendidos=59 retenidos=1 totales=60
  invariante (v+r <= t)  : 60 <= 60  -> OK
================================================================
2 passed
```

### Prueba automatizada 2 — API HTTP en vivo

[`backend/tests/concurrencia_http.py`](../backend/tests/concurrencia_http.py).
20 `POST /reservations` HTTP **simultáneos** contra el servidor uvicorn.

Evidencia — [`docs/evidencia/prueba-concurrencia-http.txt`](evidencia/prueba-concurrencia-http.txt):

```
============================================================
POST /reservations x20 simultaneos por 1 asiento
  201 Created : 1   ['201 CCXZRV']
  409 Conflict: 19
  otros       : 0   []
============================================================
OK: exactamente 1 reserva, sin sobreventa
```

**Conclusión:** en ambas pruebas se cumple el NFR-03 — exactamente **1** reserva
se lleva el asiento, las otras 19 reciben **409**, y el invariante
`vendidos + retenidos ≤ totales` se mantiene: **cero sobreventa**.

## 5.6.3 Decisiones de implementación y desviaciones frente a 5.3 / 5.4

> La sección 5.6 del enunciado pide declarar explícitamente toda desviación.

| # | Punto | ¿Desviación? | Detalle y justificación |
|---|---|---|---|
| D1 | **`SELECT ... FOR UPDATE` sin filtrar por `cabina` en el lock** | Ajuste menor | En `booking.crear_reserva` el `FOR UPDATE` bloquea **todas** las filas de inventario de las instancias implicadas (todas las cabinas), no solo la cabina pedida. Motivo: simplicidad y correctitud (bloquea de más, nunca de menos); el número de cabinas por vuelo es 2. Si en el futuro hubiera muchas cabinas se añadiría `AND cabina = :c` al `WHERE ... FOR UPDATE`. No afecta a 5.3 ni a la garantía de NFR-03. |
| D2 | **Precio del segmento = `tarifa.monto_precio * num_pasajeros`** | Precisión del diseño | 5.3 define `segmento_itinerario.monto_segmento` sin especificar si es por pasajero o total. Se implementó como **total del tramo** (precio × nº pax). `reserva.monto_total` = suma de segmentos, con descuento de agencia aplicado. Se documenta aquí; no cambia el modelo. |
| D3 | **Estados en español** | Coherencia | El código usa `RETENIDA / CONFIRMADA / CANCELADA / EXPIRADA` (5.3) y cabinas `ECONOMICA / EJECUTIVA`. Sin cambio de diseño. |
| D4 | **`asientos_totales` como columna, no derivada de `config_cabina`** | Ya previsto en 5.3 | Confirmado en implementación: `seed` copia `num_asientos` de `config_cabina` a `inventario_asientos.asientos_totales` al crear la instancia. Un cambio futuro de aeronave no altera vuelos ya vendidos (decisión de 5.3.1). |
| D5 | **Búsqueda con escala limitada a 1 conexión y ventana `[45, 360]` min** | Ya previsto en 5.4.3 | Parámetros en `config.py` (`MIN/MAX_CONNECTION_MINUTES`). Implementado tal cual el diseño. |
| D6 | **`pago`, `cancelar`, `checkin`, `jobs` no implementados en el MVP** | Alcance declarado | 5.6 exige buscar / crear / consultar. El resto está **diseñado** (5.4) y modelado (5.3, tablas `pago`, `billete`, `asignacion_asiento` ya creadas) pero fuera del alcance de esta entrega. El hold **no expira automáticamente** todavía (falta el job `FR-07`); `retenida_hasta` se calcula y guarda. |

**Ningún cambio obligó a modificar el modelo ER de 5.3** — todas las tablas y
restricciones del diccionario de datos se implementaron sin alteración. La
sección [5.3.7](03-modelo-entidad-relacion.md) queda sin entradas de corrección.

## 5.6.4 Entregables de esta subsección

- **Código fuente:** [`backend/`](../backend/) (se subirá a GitHub).
- **Esquema de BD:** migración Alembic [`0001_esquema_inicial.py`](../backend/alembic/versions/0001_esquema_inicial.py) (`alembic upgrade head` lo crea).
- **Guía de ejecución:** [`backend/README.md`](../backend/README.md).
- **Evidencia de la prueba de concurrencia:** [`docs/evidencia/`](evidencia/) (salidas de ambas pruebas) + los propios tests reproducibles.
