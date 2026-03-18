import logging
import uuid
from contextlib import asynccontextmanager
from typing import List
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.circuit_breaker import CircuitBreaker
from app.db import get_db
from app.grpc_client import FlightGrpcClient
from app.migrations import run_migrations
from app.models import Booking, BookingStatus
from app.schemas import BookingResponse, CreateBookingRequest, FlightResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

breaker = CircuitBreaker(
    failure_threshold=settings.cb_failure_threshold,
    reset_timeout=settings.cb_reset_timeout,
    window_seconds=settings.cb_window_seconds,
)
flight_client = FlightGrpcClient(breaker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Booking Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/flights", response_model=List[FlightResponse])
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str | None = None,
):
    response = flight_client.search_flights(origin.upper(), destination.upper(), date)
    return [
        FlightResponse(
            id=f.id,
            flight_number=f.flight_number,
            airline=f.airline,
            origin=f.origin,
            destination=f.destination,
            departure_time=f.departure_time.ToDatetime(),
            arrival_time=f.arrival_time.ToDatetime(),
            total_seats=f.total_seats,
            available_seats=f.available_seats,
            price=f.price,
            status=flight_status_name(f.status),
        )
        for f in response.flights
    ]


@app.get("/flights/{flight_id}", response_model=FlightResponse)
def get_flight(flight_id: str):
    f = flight_client.get_flight(flight_id)
    return FlightResponse(
        id=f.id,
        flight_number=f.flight_number,
        airline=f.airline,
        origin=f.origin,
        destination=f.destination,
        departure_time=f.departure_time.ToDatetime(),
        arrival_time=f.arrival_time.ToDatetime(),
        total_seats=f.total_seats,
        available_seats=f.available_seats,
        price=f.price,
        status=flight_status_name(f.status),
    )


@app.post("/bookings", response_model=BookingResponse, status_code=201)
def create_booking(payload: CreateBookingRequest, db: Session = Depends(get_db)):
    booking_id = uuid.uuid4()
    flight = flight_client.get_flight(str(payload.flight_id))
    flight_client.reserve_seats(str(booking_id), str(payload.flight_id), payload.seat_count)
    booking = Booking(
        id=booking_id,
        user_id=payload.user_id,
        flight_id=payload.flight_id,
        passenger_name=payload.passenger_name,
        passenger_email=payload.passenger_email,
        seat_count=payload.seat_count,
        total_price=payload.seat_count * flight.price,
        status=BookingStatus.CONFIRMED,
    )
    try:
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    except Exception:
        db.rollback()
        try:
            flight_client.release_reservation(str(booking_id))
        except Exception:
            logger.exception("failed to compensate reservation after booking db error")
        raise


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid booking id")
    booking = db.get(Booking, booking_uuid)
    if not booking:
        raise HTTPException(status_code=404, detail="booking not found")
    return booking


@app.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(booking_id: str, db: Session = Depends(get_db)):
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid booking id")
    booking = db.get(Booking, booking_uuid)
    if not booking:
        raise HTTPException(status_code=404, detail="booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="booking already cancelled")
    flight_client.release_reservation(str(booking.id))
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking


@app.get("/bookings", response_model=List[BookingResponse])
def list_bookings(user_id: str, db: Session = Depends(get_db)):
    result = db.execute(select(Booking).where(Booking.user_id == user_id).order_by(Booking.created_at.desc()))
    return list(result.scalars())


def flight_status_name(value: int) -> str:
    mapping = {1: "SCHEDULED", 2: "DEPARTED", 3: "CANCELLED", 4: "COMPLETED"}
    return mapping.get(value, "UNKNOWN")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port)
