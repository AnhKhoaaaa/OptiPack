FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install curl for health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend code, calibration assets, and test fixtures
COPY backend /app/backend
COPY experiments /app/experiments
COPY tests/fixtures /app/tests/fixtures

# Expose default port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Render dynamically injects $PORT; uvicorn binds to 0.0.0.0:$PORT
CMD ["sh", "-c", "uvicorn backend.app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
