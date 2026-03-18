import logging
from concurrent import futures
import grpc
from app.auth import ApiKeyServerInterceptor
from app.config import settings
from app.migrations import run_migrations
from app.service import FlightService
import flight_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def serve():
    run_migrations()
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[ApiKeyServerInterceptor()],
    )
    flight_pb2_grpc.add_FlightServiceServicer_to_server(FlightService(), server)
    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    server.start()
    logger.info("flight service started on port %s", settings.grpc_port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
