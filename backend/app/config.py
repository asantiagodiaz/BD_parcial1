from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion cargada de variables de entorno / .env (ver .env.example)."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    oltp_database_url: str = (
        "postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_oltp"
    )
    olap_database_url: str = (
        "postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_olap"
    )

    # FR-06 / S4: duracion del hold temporal de asientos
    hold_minutes: int = 15

    # FR-02: ventana de tiempo de conexion valida para itinerarios con escala
    min_connection_minutes: int = 45
    max_connection_minutes: int = 360

    # 5.5: origenes permitidos para la SPA. Coma-separado en .env, p. ej.
    #   CORS_ORIGINS=http://localhost:5173,http://mi-bucket.s3-website-us-east-1.amazonaws.com
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
