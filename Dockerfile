# Production Dockerfile for Django + Playwright on Railway
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_HEADLESS=true \
    PORT=8080

WORKDIR /app

# Install system packages required for Playwright Chromium & psycopg2
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

# Install Playwright browser binaries and system dependencies
RUN playwright install --with-deps chromium

# Copy application source code
COPY . .

# Create results directory and ensure start.sh has execution permissions
RUN mkdir -p results && chmod +x /app/start.sh

# Collect static files for Swagger UI & Django Admin
RUN python manage.py collectstatic --noinput

# Expose port (Railway injects $PORT dynamically)
EXPOSE 8080

# Start server via startup script (runs migrations then starts Gunicorn)
CMD ["/app/start.sh"]
