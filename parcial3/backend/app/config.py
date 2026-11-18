"""Configuracion por variables de entorno (sin credenciales en el codigo)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base transaccional (PostgreSQL en la misma EC2). Formato SQLAlchemy + psycopg 3.
    database_url: str = "postgresql+psycopg://postgres@localhost:5433/airline3"
    db_pool_size: int = 20
    db_max_overflow: int = 40

    aws_region: str = "us-east-1"

    # Kinesis (R1-R3). Vacio = no se publica ni se consume (pruebas del backend sin AWS).
    kinesis_stream: str = ""
    # Busquedas: cola en memoria + hilo que envia por lotes (R2). Si la cola se llena se
    # descarta la busqueda: perder una busqueda es aceptable, frenar la API no.
    search_queue_max: int = 10000
    search_batch_max: int = 500        # limite de PutRecords
    search_linger_seconds: float = 0.2  # espera maxima para armar un lote
    # Vista en vivo (R3): el consumidor lee el shard cada `live_poll_seconds`.
    live_poll_seconds: float = 1.0
    live_max_window_minutes: int = 60

    # Modelo estrella (R5-R10): Athena + Glue.
    data_bucket: str = ""                  # bucket con raw/, ref/, star/, athena-results/
    raw_events_prefix: str = "raw/events/"  # landing zone (la llena Firehose)
    ref_prefix: str = "ref/"
    star_prefix: str = "star/"
    athena_workgroup: str = "airline-p3"
    athena_database: str = "airline_star"
    athena_output: str = ""  # s3://bucket/athena-results/ (vacio si el workgroup ya tiene uno)
    # Refresco periodico de la estrella (micro-lotes). 0 = solo bajo demanda.
    star_refresh_every_minutes: int = 10

    cors_origins: str = "*"


settings = Settings()
