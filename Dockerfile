# Use lightweight Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install essential system packages including Poppler, Tesseract, and OpenCV dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (for better caching)
COPY backend/requirements.txt .

# Install Python dependencies with minimal cache
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend files
COPY backend/ .

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the app with gunicorn (minimal workers for free tier, increased timeout)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers=2", "--threads=2", "--worker-class=gthread", "--worker-tmp-dir=/dev/shm", "--max-requests=100", "--timeout=120", "app:app"]
