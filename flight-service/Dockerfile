FROM python:3.12-slim
WORKDIR /app
COPY flight-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY proto /app/proto
RUN mkdir -p /app/generated && python -m grpc_tools.protoc -I/app/proto --python_out=/app/generated --grpc_python_out=/app/generated /app/proto/flight.proto && touch /app/generated/__init__.py
COPY flight-service /app/flight_service
ENV PYTHONPATH=/app:/app/generated:/app/flight_service
CMD ["python", "/app/flight_service/app/main.py"]
