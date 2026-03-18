import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from app.cache import clear_search_cache, delete_key, get_json, set_json
from app.db import SessionLocal
from app.models import Flight, FlightStatus, ReservationStatus, SeatReservation
import flight_pb2
import flight_pb2_grpc

logger = logging.getLogger(__name__)


def to_timestamp(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc))
    return ts


def flight_to_proto(flight: Flight) -> flight_pb2.Flight:
    status_map = {
        FlightStatus.SCHEDULED: flight_pb2.SCHEDULED,
        FlightStatus.DEPARTED: flight_pb2.DEPARTED,
        FlightStatus.CANCELLED: flight_pb2.CANCELLED,
        FlightStatus.COMPLETED: flight_pb2.COMPLETED,
    }
    return flight_pb2.Flight(
        id=str(flight.id),
        flight_number=flight.flight_number,
        airline=flight.airline,
        origin=flight.origin,
        destination=flight.destination,
        departure_time=to_timestamp(flight.departure_time),
        arrival_time=to_timestamp(flight.arrival_time),
        total_seats=flight.total_seats,
        available_seats=flight.available_seats,
        price=float(flight.price),
        status=status_map[flight.status],
        created_at=to_timestamp(flight.created_at),
        updated_at=to_timestamp(flight.updated_at),
    )


class FlightService(flight_pb2_grpc.FlightServiceServicer):
    def SearchFlights(self, request, context):
        origin = request.origin.strip().upper()
        destination = request.destination.strip().upper()
        if not origin or not destination:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "origin and destination are required")
        date_str = ""
        requested_date = None
        if request.HasField("date"):
            requested_date = request.date.ToDatetime().date()
            date_str = requested_date.isoformat()
        cache_key = f"search:{origin}:{destination}:{date_str or 'all'}"
        cached = get_json(cache_key)
        if cached is not None:
            return flight_pb2.SearchFlightsResponse(
                flights=[_dict_to_proto(item) for item in cached]
            )
        with SessionLocal() as db:
            stmt = select(Flight).where(
                and_(
                    Flight.origin == origin,
                    Flight.destination == destination,
                    Flight.status == FlightStatus.SCHEDULED,
                )
            ).order_by(Flight.departure_time.asc())
            flights = list(db.execute(stmt).scalars())
            if requested_date:
                flights = [f for f in flights if f.departure_time.date() == requested_date]
            payload = [_flight_to_dict(f) for f in flights]
            set_json(cache_key, payload)
            return flight_pb2.SearchFlightsResponse(flights=[flight_to_proto(f) for f in flights])

    def GetFlight(self, request, context):
        try:
            flight_id = uuid.UUID(request.id)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid flight id")
        cache_key = f"flight:{flight_id}"
        cached = get_json(cache_key)
        if cached is not None:
            return _dict_to_proto(cached)
        with SessionLocal() as db:
            flight = db.get(Flight, flight_id)
            if not flight:
                context.abort(grpc.StatusCode.NOT_FOUND, "flight not found")
            set_json(cache_key, _flight_to_dict(flight))
            return flight_to_proto(flight)

    def ReserveSeats(self, request, context):
        if request.seat_count <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "seat_count must be positive")
        try:
            booking_id = uuid.UUID(request.booking_id)
            flight_id = uuid.UUID(request.flight_id)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid uuid")
        with SessionLocal() as db:
            try:
                existing = db.execute(select(SeatReservation).where(SeatReservation.booking_id == booking_id)).scalar_one_or_none()
                if existing:
                    if existing.status == ReservationStatus.ACTIVE:
                        return flight_pb2.ReserveSeatsResponse(
                            reservation_id=str(existing.id),
                            status=flight_pb2.ACTIVE,
                        )
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION, "reservation already exists in non-active state")
                flight = db.execute(
                    select(Flight).where(Flight.id == flight_id).with_for_update()
                ).scalar_one_or_none()
                if not flight:
                    context.abort(grpc.StatusCode.NOT_FOUND, "flight not found")
                if flight.status != FlightStatus.SCHEDULED:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION, "flight not available for booking")
                if flight.available_seats < request.seat_count:
                    context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "not enough seats")
                flight.available_seats -= request.seat_count
                reservation = SeatReservation(
                    booking_id=booking_id,
                    flight_id=flight_id,
                    seat_count=request.seat_count,
                    status=ReservationStatus.ACTIVE,
                )
                db.add(reservation)
                db.commit()
                db.refresh(reservation)
                db.refresh(flight)
                delete_key(f"flight:{flight_id}")
                clear_search_cache()
                return flight_pb2.ReserveSeatsResponse(
                    reservation_id=str(reservation.id),
                    status=flight_pb2.ACTIVE,
                )
            except grpc.RpcError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                logger.exception("reserve seats failed")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))

    def ReleaseReservation(self, request, context):
        try:
            booking_id = uuid.UUID(request.booking_id)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid booking id")
        with SessionLocal() as db:
            try:
                reservation = db.execute(
                    select(SeatReservation).where(SeatReservation.booking_id == booking_id).with_for_update()
                ).scalar_one_or_none()
                if not reservation:
                    context.abort(grpc.StatusCode.NOT_FOUND, "reservation not found")
                if reservation.status == ReservationStatus.RELEASED:
                    return Empty()
                if reservation.status != ReservationStatus.ACTIVE:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION, "reservation is not active")
                flight = db.execute(select(Flight).where(Flight.id == reservation.flight_id).with_for_update()).scalar_one()
                flight.available_seats += reservation.seat_count
                reservation.status = ReservationStatus.RELEASED
                db.commit()
                delete_key(f"flight:{flight.id}")
                clear_search_cache()
                return Empty()
            except grpc.RpcError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                logger.exception("release reservation failed")
                context.abort(grpc.StatusCode.INTERNAL, str(exc))


def _flight_to_dict(flight: Flight) -> dict:
    return {
        "id": str(flight.id),
        "flight_number": flight.flight_number,
        "airline": flight.airline,
        "origin": flight.origin,
        "destination": flight.destination,
        "departure_time": flight.departure_time.isoformat(),
        "arrival_time": flight.arrival_time.isoformat(),
        "total_seats": flight.total_seats,
        "available_seats": flight.available_seats,
        "price": float(flight.price),
        "status": flight.status.value,
        "created_at": flight.created_at.isoformat(),
        "updated_at": flight.updated_at.isoformat(),
    }


def _dict_to_proto(item: dict) -> flight_pb2.Flight:
    status_map = {
        "SCHEDULED": flight_pb2.SCHEDULED,
        "DEPARTED": flight_pb2.DEPARTED,
        "CANCELLED": flight_pb2.CANCELLED,
        "COMPLETED": flight_pb2.COMPLETED,
    }
    dep = Timestamp(); dep.FromDatetime(datetime.fromisoformat(item["departure_time"]).astimezone(timezone.utc))
    arr = Timestamp(); arr.FromDatetime(datetime.fromisoformat(item["arrival_time"]).astimezone(timezone.utc))
    created = Timestamp(); created.FromDatetime(datetime.fromisoformat(item["created_at"]).astimezone(timezone.utc))
    updated = Timestamp(); updated.FromDatetime(datetime.fromisoformat(item["updated_at"]).astimezone(timezone.utc))
    return flight_pb2.Flight(
        id=item["id"],
        flight_number=item["flight_number"],
        airline=item["airline"],
        origin=item["origin"],
        destination=item["destination"],
        departure_time=dep,
        arrival_time=arr,
        total_seats=item["total_seats"],
        available_seats=item["available_seats"],
        price=float(item["price"]),
        status=status_map[item["status"]],
        created_at=created,
        updated_at=updated,
    )
