FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
COPY services/data-processor/requirements.txt ./processor-requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r processor-requirements.txt

# Copy shared modules
COPY shared/ ./shared/

# Copy original modules
COPY src/ ./src/

# Copy data processor service
COPY services/data-processor/ ./

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONPATH=/app:/app/shared:/app/src

CMD ["python", "app.py"]