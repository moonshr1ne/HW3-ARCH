# Flight Booking System (gRPC + Redis)

## Overview

This project implements a distributed flight booking system using a microservices architecture.

The system consists of two services:

- Booking Service (REST API) — handles bookings and client requests
- Flight Service (gRPC API) — manages flights and seat availability

The services communicate via gRPC, and each service has its own PostgreSQL database.
Redis is used for caching in the Flight Service.

## Architecture

Client → Booking Service (REST) → Flight Service (gRPC)
                     ↓                          ↓
                PostgreSQL               PostgreSQL + Redis

## Features

### Core (1–4 points)
- Microservices architecture (2 services)
- Separate PostgreSQL databases
- REST API (Booking Service)
- gRPC API (Flight Service)
- Flight search, booking, cancellation
- Proper business logic and error handling

### Intermediate (5–7 points)
- Transactional consistency
- Row-level locking using SELECT FOR UPDATE
- gRPC authentication via API key (metadata)
- Redis cache (Cache-Aside strategy)
- TTL for all cache entries
- Cache invalidation after mutations
- Cache hit/miss logging

### Advanced (8 points)
- Retry mechanism with exponential backoff
  (100ms → 200ms → 400ms)
- Retry only for UNAVAILABLE and DEADLINE_EXCEEDED
- Idempotent ReserveSeats using booking_id
- No duplicate reservations on retry

## Tech Stack

- Python (FastAPI + gRPC)
- PostgreSQL
- Redis
- Docker / Docker Compose

## How to Run

docker compose up --build

## API Access

Swagger UI:
http://localhost:8080/docs

## Example Flow

1. Search flights:
GET /flights?origin=SVO&destination=LED&date=2026-04-01

2. Create booking:
POST /bookings

{
  "user_id": "user-1",
  "flight_id": "11111111-1111-1111-1111-111111111111",
  "passenger_name": "Ivan Ivanov",
  "passenger_email": "ivan@example.com",
  "seat_count": 2
}

3. Cancel booking:
POST /bookings/{id}/cancel

## Consistency & Transactions

- Seat reservation is atomic
- Uses SELECT FOR UPDATE to prevent race conditions
- No partial updates

## Caching (Redis)

- Cache-Aside strategy
- flight:{id}
- search:{origin}:{destination}:{date}
- TTL: 5–10 minutes
- Cache invalidation after ReserveSeats and ReleaseReservation

## Fault Tolerance

- Retry with exponential backoff
- Idempotent operations prevent duplicate reservations

## gRPC Authentication

- API key via metadata
- Unauthorized requests return UNAUTHENTICATED

## Project Structure

booking-service/
flight-service/
proto/
docker-compose.yml

## Author

Student project for Distributed Systems / SOA course
