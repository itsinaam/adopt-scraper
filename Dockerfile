# Production Dockerfile for Django + Playwright on Google Cloud Run / Compute Engine
FROM python:3.10-slim

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_HEADLESS=true \
    PORT=8080

WORKDIR /app

# Install system packages required for Playwright & psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries and system libraries
RUN playwright install --with-deps chromium

# Copy application source code
COPY . .

# Create results directory for local temp artifacts
RUN mkdir -p results

# Collect static files for Swagger & Admin UI
RUN python manage.py collectstatic --noinput || true

# Expose port (Cloud Run sets $PORT dynamically)
EXPOSE 8080

# Start production WSGI server via Gunicorn
CMD exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --timeout 300
