import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("BOOKING_DB_HOST", "localhost")
    db_port: int = _int("BOOKING_DB_PORT", 5432)
    db_user: str = os.getenv("BOOKING_DB_USER", "booking_user")
    db_password: str = os.getenv("BOOKING_DB_PASSWORD", "booking_pass")
    db_name: str = os.getenv("BOOKING_DB_NAME", "booking_db")
    http_port: int = _int("BOOKING_HTTP_PORT", 8080)
    grpc_target: str = os.getenv("FLIGHT_GRPC_TARGET", "localhost:50051")
    grpc_api_key: str = os.getenv("GRPC_API_KEY", "super-secret-key")
    grpc_timeout_seconds: float = _float("GRPC_TIMEOUT_SECONDS", 3.0)
    cb_failure_threshold: int = _int("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
    cb_reset_timeout: int = _int("CIRCUIT_BREAKER_RESET_TIMEOUT", 15)
    cb_window_seconds: int = _int("CIRCUIT_BREAKER_WINDOW_SECONDS", 30)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
