FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
COPY services/data-collector/requirements.txt ./collector-requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r collector-requirements.txt

# Copy shared modules
COPY shared/ ./shared/

# Copy original YouTube extractor
COPY src/ ./src/

# Copy data collector service
COPY services/data-collector/ ./

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONPATH=/app:/app/shared:/app/src

CMD ["python", "app.py"]