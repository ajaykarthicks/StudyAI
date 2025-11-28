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

# Expose port (Hugging Face uses 7860 by default, Render uses 10000)
EXPOSE 7860

# Run the app with gunicorn
# Use shell form to allow variable expansion for $PORT
CMD gunicorn --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads 4 --worker-class=gthread --worker-tmp-dir=/dev/shm --max-requests=50 --timeout=120 app:app
