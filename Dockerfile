FROM python:3.11-slim

WORKDIR /app

# Create data directory for persistent volume
RUN mkdir -p /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python source files
COPY app.py .
COPY audit_service.py .
COPY encryption_service.py .
COPY passkey_auth.py .
COPY auth/ ./auth/
COPY billing/ ./billing/
COPY extension/ ./extension/

# Legacy SQLite file (kept for reference, not used in production)
COPY boswell_v2.db /data/boswell_v2.db

ENV BOSWELL_DB=/data/boswell_v2.db

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
