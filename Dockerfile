# Use Python 3.10 slim image
FROM python:3.10.13-slim

# Set working directory
WORKDIR /app

# Copy backend files
COPY backend/ .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (Railway assigns PORT env var)
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=2)"

# Run the app with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
