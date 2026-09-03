# 0. Contexto y supuestos

## 0.1 Escenario de negocio

Una aerolínea **regional** contrata al equipo para construir su sistema de reservas
de vuelos desde cero. Directrices del negocio (deliberadamente incompletas):

- Los pasajeros buscan vuelos, reservan y pagan billetes, y consultan o cancelan sus reservas.
- Venta **directa** (sitio web) y a través de **agencias de viajes asociadas**.
- **Tarifas** variables según antelación de compra y tipo de asiento (economía, negocios).
- Un vuelo puede tener **escalas**; un pasajero puede reservar un **itinerario multi-tramo en una sola transacción**.
- La gerencia comercial quiere analizar después: **ocupación por ruta**, **ingresos por tarifa**, **patrones de cancelación**.
- Regla dura: *"el sistema no debe vender más asientos de los que tiene la aeronave"*.
- *"Los picos de tráfico durante la temporada alta"* — sin cifras concretas.

## 0.2 Supuestos declarados

> *Un supuesto no declarado es una decisión arquitectónica implícita.* Todos los
> supuestos siguientes son decisiones del equipo, revisables, y cada uno indica qué
> parte del diseño se vería afectada si cambiara.

| # | Supuesto | Justificación | Impacto si cambia |
|---|---|---|---|
| S1 | **No hay programa de viajero frecuente** en el MVP. | Fuera del núcleo evaluado; añade entidades (cuenta de millas, niveles) sin afectar la regla de sobreventa. | Nuevas entidades `LoyaltyAccount`, `MileTransaction`; reglas de tarifa con redención. |
| S2 | **Se permiten cancelaciones.** El **cambio de fecha** se modela como *cancelar + volver a reservar* (con política de penalización configurable). | Evita lógica de reasignación de inventario entre instancias de vuelo; mantiene el flujo de reserva atómico y simple. | Nuevo caso de uso "modificar reserva" con transacción que libera un `SeatInventory` y toma otro atómicamente. |
| S3 | **Agencias asociadas: mismo flujo de reserva**, diferenciadas por `channel = AGENCY` y con **comisión** registrada por reserva. Sin API B2B separada en el MVP (se diseña, no se implementa). | La regla de sobreventa y el modelo de datos son idénticos; la diferencia es comercial (comisión, descuento), no transaccional. | Se añade una API B2B con su propia autenticación y contrato; el backend monolítico expone un router adicional. |
| S4 | **Reserva sin pago = *hold* temporal de 15 minutos** sobre el inventario (estado `HELD`); si no se paga, expira y libera los asientos. | El enunciado pregunta explícitamente si se permite reservar sin pagar. El hold protege al pasajero durante el pago sin bloquear inventario indefinidamente. | Cambiar a "pago atómico" elimina el estado `HELD` y el job de expiración; simplifica pero empeora UX en pagos lentos. |
| S5 | **Una sola moneda (COP) y un idioma (es-CO)** en el MVP. El diseño contempla i18n y multi-moneda (tarifas con `currency`, textos externalizados). | Reduce alcance sin comprometer el modelo (la columna `currency` ya existe). | Tabla de tipos de cambio, `Fare` por moneda, frontend con catálogo de idiomas. |
| S6 | **Objetivo de disponibilidad: 99.9% mensual** (≤ ~43 min de caída/mes) como traducción de *"no puede caerse en temporada alta"*. MVP en single-AZ; el documento declara el trade-off de costo hacia Multi-AZ. | Número verificable y defendible; Multi-AZ duplica el costo de RDS. | Multi-AZ en ambas RDS, réplicas de lectura para búsqueda, mayor costo (ver 5.7). |
| S7 | **Asignación de asiento nominal ocurre en el check-in**, no en la compra. En la compra solo se descuenta un **contador de inventario por cabina**. | Simplifica el bloqueo de concurrencia (un contador por cabina, no N filas de asiento); refleja la práctica real de aerolíneas regionales. | El inventario pasa a ser por asiento (`Seat` con estado); el lock afecta filas individuales; posible selección de asiento de pago. |
| S8 | **Equipaje fuera de alcance** en el MVP (se puede añadir como `AncillaryService`). | No afecta la reserva ni la sobreventa. | Nueva entidad de servicios adicionales y su cobro. |
| S9 | **Número de rutas: se asume del orden de 10–30 rutas** y crecimiento de +20/año (del enunciado). Volumen de reservas moderado (aerolínea regional). | Base para el dimensionamiento (instancias `db.t3.micro`) y la proyección de costos y del escenario ×10 en 5.7. | Re-dimensionar instancias, particionar `flight_instance`/`reservation` por fecha, revisar el cuello de botella del lock. |
| S10 | **Pago delegado a un proveedor externo** (pasarela). El sistema **no almacena datos de tarjeta**; guarda solo un token/referencia y el estado del pago. En el MVP el proveedor es un *stub* simulado. | Saca el alcance PCI-DSS del sistema; el diseño de pagos real queda documentado. | Integración real con pasarela (webhooks de confirmación, conciliación, reintentos). |

## 0.3 Actores del sistema

Todos operan sobre **el mismo backend** (un monolito modular), con **interfaces
distintas** según el rol.

| Actor | Descripción | Interfaz | Casos de uso principales |
|---|---|---|---|
| **Pasajero** | Cliente final que compra en el sitio web. | SPA pública | Buscar vuelos, reservar (incl. multi-tramo), pagar, consultar, cancelar. |
| **Agente de agencia asociada** | Empleado de una agencia de viajes que reserva a nombre de un pasajero. | SPA (vista de agente) / futura API B2B | Mismo flujo de reserva + registro de comisión y datos de la agencia. |
| **Personal de aeropuerto** | Realiza el check-in y la asignación de asiento. | Interfaz interna | Consultar reserva, asignar asiento (`SeatAssignment`), emitir tarjeta de embarque. |
| **Administrador comercial** | Gestiona el catálogo y consulta reportes. | Interfaz de administración | Alta/baja de rutas, vuelos programados, tarifas; consulta de reportes (ocupación, ingresos, cancelaciones) servidos desde la BD analítica. |

## 0.4 Trazabilidad

Cada requisito de este documento y de los siguientes lleva un identificador
(`FR-xx`, `NFR-xx`, entidad `E-xx`). Las decisiones de arquitectura (5.4, 5.5) y de
implementación (5.6, 5.7) **citan explícitamente** el identificador del requisito
que las origina, según exige la rúbrica de "Claridad y trazabilidad".
