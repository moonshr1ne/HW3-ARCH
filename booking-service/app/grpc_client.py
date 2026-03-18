import logging
import time
from datetime import datetime, timezone
from typing import Any
import grpc
from fastapi import HTTPException
from google.protobuf.timestamp_pb2 import Timestamp
from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.config import settings
import flight_pb2
import flight_pb2_grpc

logger = logging.getLogger(__name__)


class ApiKeyClientInterceptor(grpc.UnaryUnaryClientInterceptor):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def intercept_unary_unary(self, continuation, client_call_details, request):
        metadata = [] if client_call_details.metadata is None else list(client_call_details.metadata)
        metadata.append(("x-api-key", self.api_key))
        new_details = _ClientCallDetails(
            client_call_details.method,
            client_call_details.timeout,
            metadata,
            client_call_details.credentials,
            client_call_details.wait_for_ready,
            client_call_details.compression,
        )
        return continuation(new_details, request)


class _ClientCallDetails(grpc.ClientCallDetails):
    def __init__(self, method, timeout, metadata, credentials, wait_for_ready, compression):
        self.method = method
        self.timeout = timeout
        self.metadata = metadata
        self.credentials = credentials
        self.wait_for_ready = wait_for_ready
        self.compression = compression


class FlightGrpcClient:
    def __init__(self, breaker: CircuitBreaker):
        channel = grpc.insecure_channel(settings.grpc_target)
        self.channel = grpc.intercept_channel(channel, ApiKeyClientInterceptor(settings.grpc_api_key))
        self.stub = flight_pb2_grpc.FlightServiceStub(self.channel)
        self.breaker = breaker

    def _with_retry(self, func, request: Any, mutable: bool = False):
        delays = [0.1, 0.2, 0.4]
        last_exc = None
        for attempt in range(3):
            try:
                self.breaker.before_call()
                response = func(request, timeout=settings.grpc_timeout_seconds)
                self.breaker.on_success()
                return response
            except CircuitBreakerOpenError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except grpc.RpcError as exc:
                code = exc.code()
                last_exc = exc
                retriable = code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED)
                self.breaker.on_failure()
                if not retriable or attempt == 2:
                    break
                logger.warning("grpc retry attempt=%s code=%s", attempt + 1, code.name)
                time.sleep(delays[attempt])
        raise self._map_grpc_error(last_exc)

    @staticmethod
    def _map_grpc_error(exc: grpc.RpcError) -> HTTPException:
        mapping = {
            grpc.StatusCode.NOT_FOUND: 404,
            grpc.StatusCode.RESOURCE_EXHAUSTED: 409,
            grpc.StatusCode.INVALID_ARGUMENT: 400,
            grpc.StatusCode.UNAUTHENTICATED: 401,
            grpc.StatusCode.UNAVAILABLE: 503,
            grpc.StatusCode.DEADLINE_EXCEEDED: 504,
        }
        status_code = mapping.get(exc.code(), 500)
        return HTTPException(status_code=status_code, detail=exc.details())

    def get_flight(self, flight_id: str):
        return self._with_retry(self.stub.GetFlight, flight_pb2.GetFlightRequest(id=flight_id))

    def search_flights(self, origin: str, destination: str, date: str | None):
        ts = None
        if date:
            parsed = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
            ts = Timestamp()
            ts.FromDatetime(parsed)
        request = flight_pb2.SearchFlightsRequest(origin=origin, destination=destination)
        if ts is not None:
            request.date.CopyFrom(ts)
        return self._with_retry(self.stub.SearchFlights, request)

    def reserve_seats(self, booking_id: str, flight_id: str, seat_count: int):
        request = flight_pb2.ReserveSeatsRequest(booking_id=booking_id, flight_id=flight_id, seat_count=seat_count)
        return self._with_retry(self.stub.ReserveSeats, request, mutable=True)

    def release_reservation(self, booking_id: str):
        request = flight_pb2.ReleaseReservationRequest(booking_id=booking_id)
        return self._with_retry(self.stub.ReleaseReservation, request, mutable=True)
