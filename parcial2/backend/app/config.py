"""Configuracion por variables de entorno (sin credenciales en el codigo)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base transaccional (PostgreSQL). Formato SQLAlchemy + psycopg 3.
    database_url: str = "postgresql+psycopg://postgres@localhost:5433/airline2"
    # Pool dimensionado para 50 reservas simultaneas (R2) + busquedas (R1).
    db_pool_size: int = 20
    db_max_overflow: int = 40

    # Athena (R7). Las credenciales las toma boto3 del rol de la instancia / entorno.
    aws_region: str = "us-east-1"
    athena_workgroup: str = "primary"
    athena_database: str = "airline_analytics"
    athena_metrics_table: str = "route_month_metrics"
    athena_output: str = ""  # s3://bucket/athena-results/ (vacio si el workgroup ya tiene uno)
    athena_timeout_seconds: int = 9  # R7 exige respuesta en <= 10 s

    cors_origins: str = "*"


settings = Settings()
