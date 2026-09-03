# 5.3 Modelo entidad-relación

> Notación: **Crow's Foot** (consistente en todo el diagrama).
> Diagrama editable: [diagrams/03-modelo-entidad-relacion.drawio](diagrams/03-modelo-entidad-relacion.drawio) — organizado en 5 bandas verticales (catálogo → programación → inventario → reserva → pasajeros).
> Referencias: FR en [01-requisitos-funcionales.md](01-requisitos-funcionales.md), NFR en [02-requisitos-no-funcionales.md](02-requisitos-no-funcionales.md), supuestos `Sx` en [00-contexto-supuestos.md](00-contexto-supuestos.md).

## 5.3.1 Decisiones de modelado (preguntas guía del enunciado)

| Pregunta guía | Decisión | Justificación | Requisito que la origina |
|---|---|---|---|
| ¿Itinerario multi-tramo: una reserva con muchos vuelos, o el itinerario es entidad propia? | **`ITINERARIO` es entidad propia** entre `RESERVA` y `INSTANCIA_VUELO`. Una reserva tiene **un** itinerario; el itinerario tiene **N `SEGMENTO_ITINERARIO`** ordenados, cada uno apuntando a una `INSTANCIA_VUELO` y a una `TARIFA`. | Un viaje multi-tramo es una unidad de negocio (precio total, reglas de conexión, se cancela junto). Modelarlo como entidad permite validar tiempos de conexión y precio agregado sin duplicar lógica en la reserva. Reservas encadenadas se descartan: romperían la atomicidad de FR-04. | FR-04, FR-05, NFR-04 |
| ¿La asignación de asiento es parte de la reserva desde la compra, o es un proceso aparte (check-in)? | **Proceso aparte.** En la compra solo se descuenta un **contador de inventario por cabina** (`INVENTARIO_ASIENTOS`). El asiento nominal se asigna en el check-in vía `ASIGNACION_ASIENTO` (0..1 por pasajero-segmento). | El bloqueo pesimista se toma sobre **una fila** (`INVENTARIO_ASIENTOS` del vuelo+cabina), no sobre N filas de asiento → menor contención (NFR-08). Refleja la práctica de aerolíneas regionales (asiento en el check-in). (Supuesto S7.) | NFR-03, NFR-08, S7 |
| ¿Cómo se representa que el mismo vuelo se repite cada día? | **Dos entidades:** `VUELO_PROGRAMADO` (plantilla: ruta, hora de salida, días de la semana, aeronave, vigencia) y `INSTANCIA_VUELO` (ocurrencia en una **fecha concreta**, con estado y su inventario). | Separar plantilla de instancia evita repetir datos por cada día y permite que inventario, tarifas efectivas y reservas cuelguen de la **instancia**. Generar instancias es un proceso batch (FR-16). | FR-16, FR-01 |
| ¿Dónde vive el control de inventario para evitar sobreventa? | En **`INVENTARIO_ASIENTOS`**: una fila por (`INSTANCIA_VUELO`, `cabina`) con `asientos_totales`, `asientos_vendidos`, `asientos_retenidos`. La disponibilidad es `asientos_totales − asientos_vendidos − asientos_retenidos`. Es la fila que se bloquea con `SELECT ... FOR UPDATE`. | Aislar el inventario en su propia tabla minimiza el alcance del lock y el tiempo de transacción (NFR-08). `asientos_totales` se copia de `CONFIG_CABINA` al crear la instancia, de modo que un cambio de aeronave futuro no altera vuelos ya vendidos. | NFR-03, NFR-04, NFR-08 |
| ¿Qué nivel de normalización, dado que alimenta el OLTP y el pipeline de Big Data? | **OLTP en 3FN** con una única desnormalización controlada: los contadores de `INVENTARIO_ASIENTOS` (`asientos_vendidos`, `asientos_retenidos`) son valores derivados que se mantienen transaccionalmente en vez de contar `BILLETE`s en cada reserva. El **OLAP** (5.7) usa un **esquema estrella** distinto, poblado por ETL. | 3FN da integridad y evita anomalías en el transaccional (NFR-04, NFR-09). El contador derivado es la excepción justificada: contar billetes bajo lock en cada reserva escalaría mal (NFR-08). El análisis no se hace sobre el OLTP: se separa físicamente (5.7). | NFR-04, NFR-08, NFR-09, 5.7 |

## 5.3.2 Listado de entidades

| # | Entidad | Rol |
|---|---|---|
| E-01 | `AEROPUERTO` | Aeropuerto (código IATA, ciudad, país, zona horaria). |
| E-02 | `RUTA` | Par origen-destino operado por la aerolínea. |
| E-03 | `AERONAVE` | Aeronave física de la flota (matrícula, modelo). |
| E-04 | `CONFIG_CABINA` | Nº de asientos por cabina (ECONOMICA / EJECUTIVA) para una aeronave. |
| E-05 | `VUELO_PROGRAMADO` | Plantilla de vuelo recurrente (ruta, hora, días de semana, aeronave, vigencia). |
| E-06 | `INSTANCIA_VUELO` | Ocurrencia de un vuelo programado en una fecha concreta; tiene estado. |
| E-07 | `INVENTARIO_ASIENTOS` | Contador de inventario por (`INSTANCIA_VUELO`, cabina). **Punto de control de sobreventa.** |
| E-08 | `TARIFA` | Tarifa por ruta, cabina y ventana de antelación de compra; incluye reglas de cambio/reembolso. |
| E-09 | `PASAJERO` | Persona que viaja (documento, nombre, fecha de nacimiento, contacto). |
| E-10 | `CUENTA_USUARIO` | Credenciales de acceso; puede pertenecer a un pasajero o a un agente de agencia. |
| E-11 | `AGENCIA` | Agencia de viajes asociada (nombre, NIT, % comisión, % descuento). |
| E-12 | `RESERVA` | Reserva: código, canal (DIRECTO/AGENCIA), estado, importe total, agencia (si aplica). |
| E-13 | `RESERVA_PASAJERO` | Pasajeros incluidos en una reserva (N:M reserva-pasajero). |
| E-14 | `ITINERARIO` | Itinerario de la reserva (unidad de viaje); 1:1 con `RESERVA`. |
| E-15 | `SEGMENTO_ITINERARIO` | Tramo ordenado del itinerario: apunta a una `INSTANCIA_VUELO`, una `TARIFA` y una cabina. |
| E-16 | `BILLETE` | Billete emitido por (`RESERVA_PASAJERO`, `SEGMENTO_ITINERARIO`) tras el pago. |
| E-17 | `PAGO` | Intento/registro de pago de una reserva (proveedor externo, token, estado, importe). |
| E-18 | `ASIGNACION_ASIENTO` | Asiento nominal asignado a un pasajero en un segmento, durante el check-in (opcional). |
| E-19 | `EVENTO_RESERVA` | Bitácora **append-only** de cambios de estado de una reserva (auditoría). |

## 5.3.3 Relaciones principales

- `RUTA` **origen** → `AEROPUERTO` (N:1) · `RUTA` **destino** → `AEROPUERTO` (N:1).
- `AERONAVE` → `CONFIG_CABINA` (1:N) — configuración de cabinas de la aeronave.
- `VUELO_PROGRAMADO` → `RUTA` (N:1) · → `AERONAVE` (N:1).
- `INSTANCIA_VUELO` → `VUELO_PROGRAMADO` (N:1).
- `INSTANCIA_VUELO` → `INVENTARIO_ASIENTOS` (1:N, una por cabina).
- `TARIFA` → `RUTA` (N:1).
- `RESERVA` → `ITINERARIO` (1:1) · → `AGENCIA` (N:0..1) · → `PAGO` (1:N) · → `EVENTO_RESERVA` (1:N).
- `RESERVA` ↔ `PASAJERO` vía `RESERVA_PASAJERO` (N:M).
- `ITINERARIO` → `SEGMENTO_ITINERARIO` (1:N, ordenados por `secuencia`).
- `SEGMENTO_ITINERARIO` → `INSTANCIA_VUELO` (N:1) · → `TARIFA` (N:1).
- `BILLETE` → `RESERVA_PASAJERO` (N:1) · → `SEGMENTO_ITINERARIO` (N:1).
- `ASIGNACION_ASIENTO` → `RESERVA_PASAJERO` (N:1) · → `SEGMENTO_ITINERARIO` (N:1); 0..1 por par.
- `CUENTA_USUARIO` → `PASAJERO` (0..1) · → `AGENCIA` (0..1).

## 5.3.4 Diccionario de datos

> Tipos orientados a PostgreSQL. `PK` = clave primaria, `FK` = foránea, `NN` = obligatorio (not null), `UQ` = único.

### E-01 `AEROPUERTO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `codigo_iata` | CHAR(3) | PK | Código IATA (p. ej. BOG). |
| `nombre` | VARCHAR(120) | NN | Nombre del aeropuerto. |
| `ciudad` | VARCHAR(80) | NN | Ciudad. |
| `pais` | CHAR(2) | NN | ISO 3166-1 alfa-2. |
| `zona_horaria` | VARCHAR(40) | NN | Zona horaria IANA (para calcular conexiones). |

### E-02 `RUTA`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_ruta` | BIGSERIAL | PK | Identificador. |
| `iata_origen` | CHAR(3) | FK→AEROPUERTO, NN | Origen. |
| `iata_destino` | CHAR(3) | FK→AEROPUERTO, NN | Destino. |
| `distancia_km` | INTEGER | | Distancia (para reportes/combustible). |
| — | | UQ(`iata_origen`,`iata_destino`) | No se repite una ruta. |

### E-03 `AERONAVE`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_aeronave` | BIGSERIAL | PK | Identificador. |
| `matricula` | VARCHAR(10) | NN, UQ | Matrícula. |
| `modelo` | VARCHAR(40) | NN | Modelo (p. ej. ATR 72). |

### E-04 `CONFIG_CABINA`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_config_cabina` | BIGSERIAL | PK | Identificador. |
| `id_aeronave` | BIGINT | FK→AERONAVE, NN | Aeronave. |
| `cabina` | VARCHAR(10) | NN, CHECK in (ECONOMICA, EJECUTIVA) | Cabina. |
| `num_asientos` | SMALLINT | NN, CHECK > 0 | Nº de asientos de esa cabina. |
| — | | UQ(`id_aeronave`,`cabina`) | Una config por cabina y aeronave. |

### E-05 `VUELO_PROGRAMADO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_vuelo_programado` | BIGSERIAL | PK | Identificador. |
| `numero_vuelo` | VARCHAR(6) | NN | Nº de vuelo comercial (p. ej. RA123). |
| `id_ruta` | BIGINT | FK→RUTA, NN | Ruta operada. |
| `id_aeronave` | BIGINT | FK→AERONAVE, NN | Aeronave asignada por defecto. |
| `hora_salida_local` | TIME | NN | Hora de salida (local al origen). |
| `duracion_min` | SMALLINT | NN | Duración estimada. |
| `dias_semana` | SMALLINT[] | NN | Días en que opera (1=lun … 7=dom). |
| `vigente_desde` / `vigente_hasta` | DATE | NN | Vigencia de la programación. |

### E-06 `INSTANCIA_VUELO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_instancia_vuelo` | BIGSERIAL | PK | Identificador. |
| `id_vuelo_programado` | BIGINT | FK→VUELO_PROGRAMADO, NN | Plantilla de origen. |
| `fecha_salida` | DATE | NN | Fecha de salida (local al origen). |
| `salida_utc` / `llegada_utc` | TIMESTAMPTZ | NN | Instantes reales (para conexiones y reportes). |
| `estado` | VARCHAR(12) | NN, default PROGRAMADO | PROGRAMADO / DESPEGADO / ATERRIZADO / CANCELADO. |
| — | | UQ(`id_vuelo_programado`,`fecha_salida`) | Una instancia por fecha. |

### E-07 `INVENTARIO_ASIENTOS`  *(control de sobreventa — NFR-03)*
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_inventario_asientos` | BIGSERIAL | PK | Identificador. |
| `id_instancia_vuelo` | BIGINT | FK→INSTANCIA_VUELO, NN | Vuelo. |
| `cabina` | VARCHAR(10) | NN | Cabina. |
| `asientos_totales` | SMALLINT | NN, CHECK ≥ 0 | Capacidad (copiada de `CONFIG_CABINA` al crear la instancia). |
| `asientos_vendidos` | SMALLINT | NN, default 0, CHECK ≥ 0 | Asientos confirmados (pagados). |
| `asientos_retenidos` | SMALLINT | NN, default 0, CHECK ≥ 0 | Asientos en hold temporal. |
| `version` | INTEGER | NN, default 0 | Reservado por si se añade control optimista. |
| — | | UQ(`id_instancia_vuelo`,`cabina`) | Una fila por vuelo y cabina. |
| — | | CHECK (`asientos_vendidos` + `asientos_retenidos` ≤ `asientos_totales`) | **Invariante de no sobreventa a nivel de BD.** |

### E-08 `TARIFA`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_tarifa` | BIGSERIAL | PK | Identificador. |
| `id_ruta` | BIGINT | FK→RUTA, NN | Ruta. |
| `cabina` | VARCHAR(10) | NN | Cabina. |
| `clase_tarifa` | VARCHAR(20) | NN | Nombre comercial (p. ej. PROMO, FLEX). |
| `dias_anticipacion_min` / `dias_anticipacion_max` | SMALLINT | NN | Ventana de antelación de compra en que aplica. |
| `monto_precio` | NUMERIC(12,2) | NN, CHECK ≥ 0 | Precio. |
| `moneda` | CHAR(3) | NN, default 'COP' | Moneda (S5). |
| `es_reembolsable` | BOOLEAN | NN | Reembolsable. |
| `penalidad_cambio` | NUMERIC(12,2) | NN, default 0 | Penalización por cambio de fecha (FR-10). |

### E-09 `PASAJERO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_pasajero` | BIGSERIAL | PK | Identificador. |
| `tipo_documento` | VARCHAR(10) | NN | CC / PA / etc. |
| `numero_documento` | VARCHAR(30) | NN | Número de documento (dato personal — NFR-07). |
| `nombre_completo` | VARCHAR(160) | NN | Nombre completo. |
| `fecha_nacimiento` | DATE | | Fecha de nacimiento. |
| `correo` / `telefono` | VARCHAR(120) | | Contacto (dato personal). |
| — | | UQ(`tipo_documento`,`numero_documento`) | Documento único. |

### E-10 `CUENTA_USUARIO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_cuenta_usuario` | BIGSERIAL | PK | Identificador. |
| `correo` | VARCHAR(120) | NN, UQ | Login. |
| `hash_contrasena` | VARCHAR(255) | NN | Hash (nunca en claro — NFR-07). |
| `rol` | VARCHAR(20) | NN | PASAJERO / AGENTE_AGENCIA / PERSONAL_AEROPUERTO / ADMIN. |
| `id_pasajero` | BIGINT | FK→PASAJERO, NULL | Si es un pasajero registrado. |
| `id_agencia` | BIGINT | FK→AGENCIA, NULL | Si es un agente de agencia. |

### E-11 `AGENCIA`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_agencia` | BIGSERIAL | PK | Identificador. |
| `nombre` | VARCHAR(120) | NN | Razón social. |
| `nit` | VARCHAR(20) | NN, UQ | NIT. |
| `tasa_comision` | NUMERIC(5,4) | NN, default 0 | % comisión sobre la venta (FR-11). |
| `tasa_descuento` | NUMERIC(5,4) | NN, default 0 | % descuento aplicado al pasajero. |
| `esta_activa` | BOOLEAN | NN, default true | |

### E-12 `RESERVA`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_reserva` | BIGSERIAL | PK | Identificador interno. |
| `codigo_reserva` | CHAR(6) | NN, UQ | Localizador (PNR) para consulta (FR-12). |
| `canal` | VARCHAR(10) | NN, CHECK in (DIRECTO, AGENCIA) | Canal de venta. |
| `id_agencia` | BIGINT | FK→AGENCIA, NULL | Agencia (si `canal = AGENCIA`). |
| `estado` | VARCHAR(12) | NN | RETENIDA / CONFIRMADA / CANCELADA / EXPIRADA. |
| `retenida_hasta` | TIMESTAMPTZ | NULL | Expiración del hold (FR-07). |
| `monto_total` | NUMERIC(12,2) | NN | Importe total del itinerario. |
| `moneda` | CHAR(3) | NN, default 'COP' | |
| `monto_comision` | NUMERIC(12,2) | NN, default 0 | Comisión devengada (FR-11). |
| `creada_en` | TIMESTAMPTZ | NN, default now() | |

### E-13 `RESERVA_PASAJERO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_reserva` | BIGINT | PK, FK→RESERVA | |
| `id_pasajero` | BIGINT | PK, FK→PASAJERO | |
| `es_contacto_principal` | BOOLEAN | NN, default false | Titular de la reserva. |

### E-14 `ITINERARIO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_itinerario` | BIGSERIAL | PK | Identificador. |
| `id_reserva` | BIGINT | FK→RESERVA, NN, UQ | 1:1 con la reserva. |
| `iata_origen` / `iata_destino` | CHAR(3) | FK→AEROPUERTO, NN | Origen/destino del viaje completo. |

### E-15 `SEGMENTO_ITINERARIO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_segmento_itinerario` | BIGSERIAL | PK | Identificador. |
| `id_itinerario` | BIGINT | FK→ITINERARIO, NN | Itinerario padre. |
| `secuencia` | SMALLINT | NN | Orden del tramo (1, 2, …). |
| `id_instancia_vuelo` | BIGINT | FK→INSTANCIA_VUELO, NN | Vuelo del tramo. |
| `cabina` | VARCHAR(10) | NN | Cabina comprada. |
| `id_tarifa` | BIGINT | FK→TARIFA, NN | Tarifa aplicada. |
| `monto_segmento` | NUMERIC(12,2) | NN | Precio del tramo (× nº de pasajeros se agrega en la reserva). |
| — | | UQ(`id_itinerario`,`secuencia`) | Secuencia sin huecos ni repetición. |

### E-16 `BILLETE`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_billete` | BIGSERIAL | PK | Identificador. |
| `numero_billete` | VARCHAR(15) | NN, UQ | Nº de billete (emitido tras el pago). |
| `id_reserva` | BIGINT | FK, NN | Reserva. |
| `id_pasajero` | BIGINT | FK, NN | Pasajero. |
| `id_segmento_itinerario` | BIGINT | FK, NN | Tramo. |
| `estado` | VARCHAR(12) | NN | EMITIDO / ANULADO / USADO. |
| — | | UQ(`id_pasajero`,`id_segmento_itinerario`) | Un billete por pasajero y tramo. |

### E-17 `PAGO`
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_pago` | BIGSERIAL | PK | Identificador. |
| `id_reserva` | BIGINT | FK→RESERVA, NN | Reserva pagada. |
| `proveedor` | VARCHAR(30) | NN | Pasarela externa (S10). |
| `referencia_proveedor` | VARCHAR(80) | NN | Token/referencia del proveedor (**no** datos de tarjeta — NFR-06). |
| `monto` | NUMERIC(12,2) | NN | Importe. |
| `moneda` | CHAR(3) | NN | |
| `estado` | VARCHAR(12) | NN | PENDIENTE / APROBADO / RECHAZADO / REEMBOLSADO. |
| `creado_en` | TIMESTAMPTZ | NN, default now() | |

### E-18 `ASIGNACION_ASIENTO`  *(check-in — FR-14)*
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_asignacion_asiento` | BIGSERIAL | PK | Identificador. |
| `id_segmento_itinerario` | BIGINT | FK, NN | Tramo. |
| `id_pasajero` | BIGINT | FK, NN | Pasajero. |
| `etiqueta_asiento` | VARCHAR(4) | NN | Asiento (p. ej. 14C). |
| `asignado_en` | TIMESTAMPTZ | NN, default now() | |
| — | | UQ(`id_segmento_itinerario`,`etiqueta_asiento`) | Un asiento no se asigna dos veces. |
| — | | UQ(`id_segmento_itinerario`,`id_pasajero`) | Un asiento por pasajero y tramo. |

### E-19 `EVENTO_RESERVA`  *(auditoría append-only — NFR-09)*
| Atributo | Tipo | Restr. | Descripción |
|---|---|---|---|
| `id_evento_reserva` | BIGSERIAL | PK | Identificador. |
| `id_reserva` | BIGINT | FK→RESERVA, NN | Reserva. |
| `tipo_evento` | VARCHAR(24) | NN | CREADA / RETENIDA / PAGADA / CONFIRMADA / CANCELADA / EXPIRADA / CAMBIO_FECHA / ASIENTO_ASIGNADO. |
| `contenido` | JSONB | | Detalle del cambio (estado anterior/nuevo, importes). |
| `tipo_actor` | VARCHAR(20) | NN | PASAJERO / AGENTE_AGENCIA / PERSONAL_AEROPUERTO / SISTEMA. |
| `id_actor` | BIGINT | | `id_cuenta_usuario` si aplica. |
| `ocurrido_en` | TIMESTAMPTZ | NN, default now() | |
| — | | Sin UPDATE/DELETE (permisos de rol + trigger que rechaza modificación). | |

## 5.3.5 Índices relevantes (rendimiento y concurrencia)

| Índice | Motivo | NFR |
|---|---|---|
| `INSTANCIA_VUELO(id_vuelo_programado, fecha_salida)` (UQ) | Localizar instancias por fecha en la búsqueda. | NFR-01 |
| `INSTANCIA_VUELO(salida_utc)` | Filtrar por fecha/hora y calcular conexiones. | NFR-02 |
| `INVENTARIO_ASIENTOS(id_instancia_vuelo, cabina)` (UQ) | Fila exacta a bloquear con `SELECT ... FOR UPDATE`; lock puntual, no de tabla. | NFR-03, NFR-08 |
| `VUELO_PROGRAMADO(id_ruta)` | Unir ruta→vuelos en la búsqueda. | NFR-01 |
| `RESERVA(codigo_reserva)` (UQ) | Consulta por localizador. | FR-12 |
| `EVENTO_RESERVA(id_reserva, ocurrido_en)` | Reconstruir historial ordenado. | NFR-09 |

## 5.3.6 Cómo el modelo previene la sobreventa (resumen)

1. Cada `INSTANCIA_VUELO` tiene una fila `INVENTARIO_ASIENTOS` por cabina con `asientos_totales` fijado al crear la instancia.
2. La transacción de reserva (5.4/5.6) ejecuta `SELECT ... FOR UPDATE` sobre esa(s) fila(s) → **serializa** las reservas que compiten por el mismo vuelo+cabina.
3. Valida `asientos_totales − asientos_vendidos − asientos_retenidos ≥ nº_pasajeros`; si no, aborta con 409 (NFR-03).
4. Incrementa `asientos_retenidos` (hold) o `asientos_vendidos` (pago), y el `CHECK (asientos_vendidos + asientos_retenidos ≤ asientos_totales)` actúa como **última barrera** a nivel de motor.
5. El job de expiración (FR-07) decrementa `asientos_retenidos` de holds vencidos, también bajo lock.

## 5.3.7 Ajustes al modelo durante la implementación

> Se completará en la Fase 4. Todo cambio del modelo frente a este documento se
> registra aquí con su justificación (lo pide explícitamente la sección 5.6 del enunciado).
