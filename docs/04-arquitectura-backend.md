# 5.4 Arquitectura del backend

> Diagrama editable: [diagrams/04-arquitectura-backend.drawio](diagrams/04-arquitectura-backend.drawio) (dos vistas: componentes y flujo de reserva con bloqueo).
> Cada decisión cita el requisito que la origina — FR en [01-requisitos-funcionales.md](01-requisitos-funcionales.md), NFR en [02-requisitos-no-funcionales.md](02-requisitos-no-funcionales.md), entidades en [03-modelo-entidad-relacion.md](03-modelo-entidad-relacion.md).

## 5.4.1 Estilo arquitectónico: monolito modular

**Decisión.** Un **único servicio** FastAPI (un despliegue, una base de datos
transaccional) organizado en **módulos internos** con fronteras claras:

| Módulo | Responsabilidad | FR que cubre |
|---|---|---|
| `catalog` | Aeropuertos, rutas, aeronaves, vuelos programados, generación de instancias, tarifas. | FR-15, FR-16, FR-17 |
| `search` | Búsqueda de vuelos directos y con escalas, cálculo de precio por tarifa. | FR-01, FR-02, FR-03 |
| `booking` | Creación de reserva (hold), confirmación, consulta, cancelación, cambio de fecha, comisión de agencia. **Dueño del control de concurrencia.** | FR-04 … FR-12, FR-11 |
| `payments` | Orquestación del pago contra la pasarela externa (stub en el MVP). | FR-08, FR-09 (reembolso) |
| `checkin` | Asignación de asiento nominal. | FR-14 |
| `audit` | Escritura de `EVENTO_RESERVA` (append-only) — invocado por `booking` y `checkin`. | FR-13, NFR-09 |
| `jobs` | Tarea periódica de expiración de holds. | FR-07 |

**Justificación (trazable a NFR).**

- **NFR-03 / NFR-04 (no sobreventa, atomicidad multi-tramo).** El invariante de
  inventario y la reserva multi-segmento se resuelven con **una transacción ACID
  local** (`SELECT ... FOR UPDATE` + `COMMIT`). Con microservicios separados
  (búsqueda / reservas / pagos con bases de datos propias) haría falta una **saga
  distribuida** con compensaciones para lograr lo mismo: más complejidad, más
  modos de fallo, y una ventana en la que el inventario puede quedar inconsistente.
  Para una aerolínea **regional** (S9: ~10–30 rutas) el monolito es suficiente y
  correcto.
- **NFR-08 (escalabilidad).** El primer cuello de botella identificado no es el
  número de rutas sino la **contención del lock sobre `INVENTARIO_ASIENTOS`** en
  vuelos concretos. Separar en servicios no elimina esa contención (el lock sigue
  siendo por fila de inventario); solo añade latencia de red. La mitigación real
  —lock por `(id_instancia_vuelo, cabina)`, transacción corta, índice dedicado—
  vive dentro del monolito.
- **Claridad y trazabilidad (rúbrica).** Módulos con fronteras explícitas permiten,
  si el negocio crece, extraer `search` o `payments` a un servicio propio sin
  reescribir el núcleo. La decisión es reversible.

**Alternativa considerada y descartada:** microservicios desde el inicio
(search-service, booking-service, payment-service). Descartada por el coste de la
saga para garantizar NFR-03/04 y por el presupuesto del Learner Lab (más
instancias, más red). Se documenta como camino de evolución.

## 5.4.2 Control de concurrencia contra la sobreventa

**Decisión: bloqueo pesimista en PostgreSQL** — `SELECT ... FOR UPDATE` sobre la(s)
fila(s) de `INVENTARIO_ASIENTOS` implicadas, dentro de la transacción de reserva.

### Flujo de `POST /reservations` (crea reserva en estado `RETENIDA`)

```
BEGIN;  -- isolation level READ COMMITTED (suficiente con FOR UPDATE)

-- 1. Bloquear el inventario de CADA segmento del itinerario, en orden
--    determinista (por id_instancia_vuelo asc) para evitar deadlocks.
SELECT id_inventario_asientos, asientos_totales, asientos_vendidos, asientos_retenidos
  FROM inventario_asientos
 WHERE id_instancia_vuelo = ANY(:ids) AND cabina = :cabina
 ORDER BY id_instancia_vuelo
   FOR UPDATE;                       -- <-- serializa a los competidores por esas filas

-- 2. Validar disponibilidad de cada fila
--    asientos_totales - asientos_vendidos - asientos_retenidos >= :num_pasajeros
--    Si alguna falla -> ROLLBACK y responder HTTP 409 (NFR-03).

-- 3. Aplicar el hold en cada fila
UPDATE inventario_asientos
   SET asientos_retenidos = asientos_retenidos + :num_pasajeros
 WHERE id_inventario_asientos = ANY(:locked_ids);
--    El CHECK (vendidos + retenidos <= totales) es la ultima barrera del motor.

-- 4. Crear RESERVA (estado=RETENIDA, retenida_hasta = now() + interval '15 min'),
--    ITINERARIO, SEGMENTO_ITINERARIO (x N), RESERVA_PASAJERO (x M).
-- 5. Insertar EVENTO_RESERVA (tipo_evento = 'CREADA' / 'RETENIDA').  (NFR-09)

COMMIT;   -- libera los locks
```

- **Orden determinista de bloqueo** (por `id_instancia_vuelo`): dos reservas
  multi-tramo que compartan dos vuelos en orden distinto no se bloquean mutuamente
  (previene deadlock).
- **Transacción corta**: entre `BEGIN` y `COMMIT` no hay llamadas externas (el pago
  es un paso posterior). Minimiza el tiempo de lock → menos contención (NFR-08).
- **Confirmación (`POST /reservations/{code}/pay`)**: al aprobar el pago,
  transacción que hace `FOR UPDATE` de las mismas filas, mueve
  `asientos_retenidos → asientos_vendidos`, pone `RESERVA.estado = CONFIRMADA`,
  emite `BILLETE` por pasajero-segmento y registra el evento.
- **Expiración (`jobs`, FR-07)**: cada minuto, por cada reserva `RETENIDA` con
  `retenida_hasta < now()`, transacción con `FOR UPDATE` que decrementa
  `asientos_retenidos` y marca `EXPIRED` + evento.

### Alternativas consideradas

| Mecanismo | Por qué NO se eligió |
|---|---|
| **Bloqueo optimista** (columna `version`, `UPDATE ... WHERE version = X`, reintento en conflicto) | Funciona, y la columna `version` ya existe en el modelo por si se necesita. Se descartó para el MVP porque **bajo alta contención** (el escenario del enunciado: todos peleando por el último asiento en temporada alta) degenera en muchos reintentos y retrasa la respuesta justo en el peor momento. El pesimista da un comportamiento más predecible y es **más fácil de demostrar** en la prueba de concurrencia de 5.6. |
| **Cola que serializa por vuelo** (SQS + worker, una reserva a la vez por `id_instancia_vuelo`) | Serializa correctamente, pero introduce **procesamiento asíncrono**: el usuario no obtiene respuesta inmediata de si su reserva se confirmó, hace falta polling o webhooks, y añade piezas de infraestructura (cola, worker, dead-letter) difíciles de justificar en el Learner Lab para un MVP. Es la evolución natural si el volumen crece mucho (NFR-08), y se documenta como tal. |

**Cómo se verifica (enlace a 5.6):** `backend/tests/test_concurrencia.py` lanza
N clientes concurrentes contra `POST /reservations` por el último asiento y
comprueba: 1 éxito, N−1 respuestas 409, e invariante
`asientos_vendidos + asientos_retenidos ≤ asientos_totales`.

## 5.4.3 Búsqueda de vuelos (FR-01, FR-02, NFR-01, NFR-02)

- **Directos (FR-01):** consulta sobre `INSTANCIA_VUELO ⨝ VUELO_PROGRAMADO ⨝ RUTA`
  filtrando por origen, destino y `fecha_salida`, con `LEFT JOIN` a
  `INVENTARIO_ASIENTOS` para mostrar disponibilidad y a `TARIFA` para el precio
  según `dias_anticipacion`. La disponibilidad mostrada es **orientativa** (no se
  toma lock en la búsqueda); el lock real ocurre al reservar.
- **Con escalas (FR-02):** el módulo `search` compone hasta **1 conexión**:
  busca tramo A→X y X→B tales que
  `salida_utc(X→B) − llegada_utc(A→X)` esté entre un mínimo y un máximo de
  conexión configurables. Se limita a 1 escala en el MVP (para una aerolínea
  regional cubre la mayoría de itinerarios) y se admite un presupuesto de latencia
  ~2× el de la búsqueda directa (NFR-02).
- **Índices que lo sostienen** (definidos en 5.3.5):
  `INSTANCIA_VUELO(id_vuelo_programado, fecha_salida)`,
  `INSTANCIA_VUELO(salida_utc)`, `VUELO_PROGRAMADO(id_ruta)`.
- **Evolución (NFR-01/08):** si la búsqueda se vuelve el cuello de botella, se
  añade una **réplica de lectura** de la BD transaccional y `search` la consulta a
  ella, dejando la primaria para las escrituras de `booking`.

## 5.4.4 Integración del pago (FR-08, NFR-06)

**Decisión: pago delegado a una pasarela externa.** El sistema **no procesa ni
almacena** datos de tarjeta (S10, NFR-06); solo guarda en `PAGO` el `proveedor`,
la `referencia_proveedor` (token) y el `estado`.

Flujo:
1. El frontend obtiene del proveedor un token de pago (fuera de nuestro backend).
2. `POST /reservations/{code}/pay` con `{ token }` → el backend llama a la API del
   proveedor para **capturar** el cobro por `RESERVA.monto_total`.
3. Según la respuesta: `APROBADO` → transacción de confirmación (5.4.2); `RECHAZADO`
   → `PAGO.estado = RECHAZADO`, la reserva sigue `RETENIDA` hasta expirar.
4. Cancelación con reembolso (FR-09): `payments` solicita el `REFUND` al proveedor
   y registra `PAGO.estado = REEMBOLSADO`.

- **MVP:** el proveedor es un **stub** (`payments/provider_stub.py`) que simula
  aprobado/rechazado de forma determinista para poder probar los flujos y la
  concurrencia sin depender de un tercero. El contrato de la interfaz
  (`PaymentProvider`) es el mismo que usaría una pasarela real → sustituible sin
  tocar `booking`.

## 5.4.5 Exposición a agencias asociadas (FR-11, S3)

**Decisión (MVP): misma API que el pasajero final**, diferenciada por el token de
autenticación:

- Una `CUENTA_USUARIO` con `rol = AGENTE_AGENCIA` y `id_agencia` asociado.
- `booking` detecta el rol: marca `RESERVA.canal = AGENCIA`, aplica
  `AGENCIA.tasa_descuento` al precio y calcula `RESERVA.monto_comision` con
  `AGENCIA.tasa_comision`. La **regla de inventario es idéntica** (mismo
  `FOR UPDATE`, misma validación).
- **API B2B separada:** se **diseña** (endpoints de tarifa negociada, facturación
  consolidada, límites por agencia) pero **no se implementa** en el MVP. Se expone
  como router aparte (`/b2b/...`) el día que exista, reutilizando el mismo módulo
  `booking`.

## 5.4.6 Relación con el pipeline de Big Data del curso (5.7)

La arquitectura transaccional **no ejecuta análisis**. La relación con el pipeline
es de **origen de datos**:

```
  [ OLTP PostgreSQL ]  --(vistas de extraccion)-->  [ AWS Glue Job / ETL ]  -->  [ OLAP PostgreSQL (estrella) ]
        (este doc)                                        (doc 5.7)                    (doc 5.7)
                                                              |
                                              ambos registrados en  [ AWS Glue Data Catalog ]
```

- El backend expone, además, endpoints de solo lectura para los **reportes**
  (FR-18) que consultan la **BD analítica**, no la transaccional → el análisis no
  compite por los locks del OLTP (NFR-08).
- El OLTP en 3FN (decisión de 5.3) es una **buena fuente** para el ETL: los datos
  están normalizados y sin duplicación; el ETL los transforma al esquema estrella.

## 5.4.7 Componentes de infraestructura (resumen; detalle y costos en 5.7)

| Componente | Rol | Requisito | Learner Lab |
|---|---|---|---|
| **API FastAPI** | Monolito modular | Todos los FR | EC2 `t3.micro` (o local contra RDS para la demo) |
| **RDS PostgreSQL (OLTP)** | BD transaccional, modelo 5.3 | NFR-03, NFR-04, NFR-07 | `db.t3.micro`, `StorageEncrypted=true`, single-AZ (trade-off NFR-05 documentado) |
| **RDS PostgreSQL (OLAP)** | BD analítica estrella | FR-18 | `db.t3.micro` |
| **AWS Glue Job** | ETL OLTP → OLAP | FR-18, 5.7 | on-demand / programado |
| **AWS Glue Data Catalog + crawlers** | Metadatos de ambas BD | 5.7 (requisito explícito) | crawlers JDBC |
| **`LabRole` / perfil de instancia** | Permisos | NFR-07 (sin llaves largas) | rol preexistente del Learner Lab |

## 5.4.8 Ajustes durante la implementación

> Se completará en la Fase 4. Toda diferencia entre este diseño y el código de 5.6
> se registra aquí con su justificación (lo exige la sección 5.6 del enunciado).
