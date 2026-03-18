# Flight Booking: gRPC + Redis

Готовый каркас под 8 баллов:
- 2 микросервиса: Booking Service (REST) и Flight Service (gRPC)
- 2 PostgreSQL
- миграции при старте
- транзакции и `SELECT FOR UPDATE`
- gRPC API key auth через metadata
- Redis cache-aside с TTL и invalidation
- retry c exponential backoff (100ms, 200ms, 400ms)
- retry только для `UNAVAILABLE` и `DEADLINE_EXCEEDED`
- идемпотентный `ReserveSeats` по `booking_id`
- circuit breaker уже тоже оставлен в проекте, хотя для 8 баллов он не обязателен

## Run

```bash
docker compose up --build
```

## Services

- Booking REST API: http://localhost:8080
- Swagger UI: http://localhost:8080/docs
- Flight gRPC: localhost:50051
- Redis: localhost:6379

## Что уже закрывает по критериям

### 1-4 балла
- gRPC контракт Flight Service
- 2 отдельные БД
- REST + gRPC
- межсервисное взаимодействие при create/cancel booking

### 5-7 баллов
- транзакционная целостность
- аутентификация межсервисных вызовов
- Redis cache-aside

### 8 баллов
- retry с exponential backoff
- retry только для временных gRPC ошибок
- `ReserveSeats` идемпотентен: повторный вызов с тем же `booking_id` не создаёт дубликат

## Основные ручки

- `GET /flights?origin=SVO&destination=LED&date=2026-04-01`
- `GET /flights/{id}`
- `POST /bookings`
- `GET /bookings/{id}`
- `GET /bookings?user_id=user-1`
- `POST /bookings/{id}/cancel`

## Пример создания бронирования

```bash
curl -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-1",
    "flight_id": "11111111-1111-1111-1111-111111111111",
    "passenger_name": "Ivan Ivanov",
    "passenger_email": "ivan@example.com",
    "seat_count": 2
  }'
```

## Проверка бизнес-флоу

1. Найти рейс `SVO -> LED` на `2026-04-01`
2. Создать booking на 2 места
3. Повторно проверить рейс: `available_seats` станет `98`
4. Отменить booking
5. Ещё раз проверить рейс: `available_seats` снова станет `100`

## Для демонстрации 7-8 баллов

- транзакции: смотри `flight-service/app/service.py`
- auth interceptor: `flight-service/app/auth.py`
- retry: `booking-service/app/grpc_client.py`
- circuit breaker: `booking-service/app/circuit_breaker.py`
- Redis cache: `flight-service/app/cache.py`
