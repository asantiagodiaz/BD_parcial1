# 5.2 Requisitos no funcionales (NFR)

> Cada NFR tiene: **métrica o condición verificable**, el **riesgo de negocio** que
> mitiga, y **cómo se verifica**. No se admiten formulaciones tipo "debe ser rápido".
> Referencias a FR en [01-requisitos-funcionales.md](01-requisitos-funcionales.md); supuestos `Sx` en [00-contexto-supuestos.md](00-contexto-supuestos.md).

## 5.2.1 Rendimiento

| ID | Requisito | Métrica verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-01 | Búsqueda de vuelos **directos** rápida. | Tiempo de respuesta **p95 < 800 ms** y p99 < 1.5 s, con la BD cargada con 30 rutas y 90 días de instancias de vuelo, hasta 50 búsquedas concurrentes. | Búsqueda lenta → abandono de la compra → pérdida de ingresos, sobre todo en temporada alta. | Prueba de carga (`locust`/`k6`) contra `GET /flights/search`; se registran percentiles. |
| NFR-02 | Búsqueda de itinerarios **con escalas** aceptablemente rápida pese al mayor costo de cómputo. | **p95 < 1.5 s** para itinerarios de hasta 1 conexión (el enunciado pregunta si cambia con escalas: **sí**, se admite ~2× el presupuesto de la búsqueda directa). | Igual que NFR-01; además, timeouts en conexiones hacen que el usuario no vea rutas válidas. | Misma prueba de carga con parámetro de conexiones; índices sobre `(route_id, departure_date)` y sobre aeropuertos de conexión. |

**Relación con la arquitectura:** NFR-01/02 sustentan la elección de **SPA** (render en cliente, llamadas asíncronas a la API) y de índices específicos en la BD transaccional (ver 5.4/5.5).

## 5.2.2 Consistencia / Concurrencia — *núcleo de la evaluación*

| ID | Requisito | Métrica / condición verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-03 | **No sobreventa.** Si *N* solicitudes intentan reservar simultáneamente el/los último(s) asiento(s) de un segmento, el sistema confirma **exactamente** las que caben y **rechaza el resto con HTTP 409**; nunca `seats_sold > capacidad`. | Invariante tras cualquier ejecución concurrente: `seats_sold + seats_held ≤ capacity` para todo `SeatInventory`. Con *N* = 20 hilos compitiendo por 1 asiento → **1 confirmación, 19 rechazos, 0 sobreventa**. | Vender un asiento inexistente obliga a *denied boarding*: compensación económica al pasajero, coste de reacomodo y daño reputacional. Es la regla dura del enunciado. | `backend/tests/test_concurrencia.py`: lanza *N* clientes en paralelo contra `POST /reservations`; asserta 1 éxito, *N*−1 → 409, y consulta `SeatInventory` para verificar el invariante. Evidencia (log + captura) en [06-implementacion-backend.md](06-implementacion-backend.md). |
| NFR-04 | **Atomicidad de la reserva multi-tramo (FR-04).** Una reserva de varios segmentos se confirma completa o no deja rastro. | Tras un fallo inyectado en el 2.º segmento, `Reservation`, `Itinerary`, `Ticket` y los descuentos de inventario del 1.er segmento **no existen** (rollback total). | Cobrar/retener inventario de un tramo sin el resto del viaje = pasajero varado, reembolsos manuales. | Test de integración con fallo simulado; se verifica el rollback en las 3 tablas y en el inventario. |

**Mecanismo elegido:** **bloqueo pesimista** en PostgreSQL — dentro de la transacción de reserva se hace `SELECT ... FOR UPDATE` sobre la(s) fila(s) de `SeatInventory` de cada segmento, se valida la disponibilidad y se actualiza el contador antes del `COMMIT`. Justificación completa y alternativas descartadas (optimista, cola) en [04-arquitectura-backend.md](04-arquitectura-backend.md).

## 5.2.3 Disponibilidad

| ID | Requisito | Métrica verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-05 | El sistema traduce *"no puede caerse en temporada alta"* como **99.9% de disponibilidad mensual** del servicio de reservas (≤ ~43 min de indisponibilidad al mes). | Uptime medido sobre el endpoint de salud durante un mes ≥ 99.9%. Implica: RDS con backups automáticos, y **camino a Multi-AZ** (RTO ≈ minutos) documentado como trade-off de costo. | Una caída durante un pico de ventas de temporada alta = ingresos perdidos irrecuperables (los asientos de esa fecha no se revenden luego). | En el MVP (Learner Lab) se despliega **single-AZ** por costo y se documenta explícitamente qué cuesta y qué implica pasar a Multi-AZ (ver proyección en 5.7). Se mide el uptime del endpoint de salud durante la demo. |

99% (≈ 7.2 h/mes) se descarta: 7 horas de caída incluyen posibles picos completos. 99.99% (≈ 4 min/mes) exige multi-región y automatización de failover: sobredimensionado y fuera del presupuesto del Learner Lab. **99.9% es el punto de equilibrio** costo/complejidad para una aerolínea regional.

## 5.2.4 Seguridad

| ID | Requisito | Métrica / condición verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-06 | **Datos de pago fuera del sistema.** El sistema **no almacena PAN ni CVV**; solo guarda un token/referencia del proveedor y el estado del pago (S10). | Revisión del esquema: ninguna columna almacena datos de tarjeta. El flujo de pago se delega a la pasarela. | Almacenar datos de tarjeta implica cumplimiento **PCI-DSS** completo (auditorías, segmentación) y multas ante brecha. | Inspección del modelo de datos (5.3) y del código de pagos (5.6); prueba de que `POST /reservations/{code}/pay` solo maneja un token. |
| NFR-07 | **Protección de datos personales (PII) de pasajeros.** Cifrado **en reposo** (RDS storage encryption / KMS) y **en tránsito** (TLS 1.2+ en la API). Acceso a PII restringido por rol. | RDS con `StorageEncrypted = true`; la API solo acepta HTTPS; los endpoints de consulta exigen el código de reserva + apellido (no listables). | Fuga de datos personales → sanción bajo la Ley 1581 de 2012 (habeas data, Colombia) y pérdida de confianza. | Verificación de la configuración de RDS y del certificado TLS; prueba de que no existe endpoint que liste reservas o pasajeros sin credenciales. |

## 5.2.5 Escalabilidad

| ID | Requisito | Métrica / condición verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-08 | El sistema soporta el crecimiento de **+20 rutas/año** (S9) sin rediseño. Se identifica que el **primer cuello de botella** es la **contención del bloqueo pesimista sobre `SeatInventory`** en vuelos muy demandados, no el número de rutas. | Con el doble de rutas y de tráfico, el p95 de `POST /reservations` se mantiene < 1.5 s. El lock se toma **por `flight_instance` + cabina** (fila específica), nunca global, de modo que reservas de vuelos distintos no se serializan entre sí. | Si toda reserva se serializara, en temporada alta se formaría una cola creciente → timeouts → ventas perdidas justo cuando más importa. | Prueba de carga con reservas repartidas entre muchos vuelos (contención baja) y concentradas en uno (contención alta); se comparan percentiles. Mitigaciones documentadas en 5.4: índice sobre `SeatInventory(flight_instance_id, cabin)`, transacción corta, y (a futuro) réplicas de lectura para la búsqueda. |

## 5.2.6 Auditabilidad

| ID | Requisito | Métrica / condición verificable | Riesgo de negocio | Verificación |
|---|---|---|---|---|
| NFR-09 | Se puede **reconstruir el historial completo** de cambios de cualquier reserva (creación, hold, pago, cancelación, cambio de fecha, asignación de asiento) con marca de tiempo y actor. | Tabla `ReservationEvent` **append-only** (sin `UPDATE`/`DELETE`); para toda reserva, la secuencia de eventos explica su estado actual. `GET /reservations/{code}` incluye el historial (FR-13). | Disputas con pasajeros o agencias ("yo sí pagué", "nunca cancelé"), y necesidad de auditar las comisiones de agencia. Sin historial, cada disputa es palabra contra palabra. | Test que ejecuta un ciclo de vida completo de una reserva y verifica que cada transición generó su evento; intento de `UPDATE` sobre `ReservationEvent` debe fallar (permisos / trigger). |

## 5.2.7 Resumen de trazabilidad NFR → decisión de arquitectura

| NFR | Decisión que lo implementa | Documento |
|---|---|---|
| NFR-01, NFR-02 | SPA + índices de búsqueda + (futuro) réplica de lectura | 5.4, 5.5 |
| NFR-03, NFR-04 | Monolito con transacción ACID + `SELECT FOR UPDATE` sobre `SeatInventory` | 5.4, 5.6 |
| NFR-05 | RDS con backups; trade-off single-AZ vs Multi-AZ documentado con costo | 5.7 |
| NFR-06, NFR-07 | Pago delegado (sin datos de tarjeta) + RDS encryption + TLS + endpoints no listables | 5.3, 5.4, 5.6 |
| NFR-08 | Lock por fila `flight_instance`+cabina, transacción corta, índice dedicado | 5.4 |
| NFR-09 | `ReservationEvent` append-only | 5.3, 5.6 |
