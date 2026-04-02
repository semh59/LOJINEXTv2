FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini ./

RUN pip install --no-cache-dir .

CMD ["uvicorn", "driver_service.main:app", "--host", "0.0.0.0", "--port", "8104"]
