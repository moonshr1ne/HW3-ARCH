import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("FLIGHT_DB_HOST", "localhost")
    db_port: int = _int("FLIGHT_DB_PORT", 5432)
    db_user: str = os.getenv("FLIGHT_DB_USER", "flight_user")
    db_password: str = os.getenv("FLIGHT_DB_PASSWORD", "flight_pass")
    db_name: str = os.getenv("FLIGHT_DB_NAME", "flight_db")
    grpc_port: int = _int("FLIGHT_GRPC_PORT", 50051)
    api_key: str = os.getenv("GRPC_API_KEY", "super-secret-key")
    redis_mode: str = os.getenv("REDIS_MODE", "standalone")
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = _int("REDIS_PORT", 6379)
    redis_db: int = _int("REDIS_DB", 0)
    redis_ttl_seconds: int = _int("REDIS_TTL_SECONDS", 300)
    redis_sentinel_host: str = os.getenv("REDIS_SENTINEL_HOST", "localhost")
    redis_sentinel_port: int = _int("REDIS_SENTINEL_PORT", 26379)
    redis_sentinel_master: str = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
