FROM python:3.11-slim

WORKDIR /app

COPY . .

ENV PYTHONPATH=/app/src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src /app/src
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "aetherflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
