FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
COPY services/agent-service/requirements.txt ./agent-requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r agent-requirements.txt

# Copy shared modules
COPY shared/ ./shared/

# Copy agent service
COPY services/agent-service/ ./

# Set environment variables
ENV PYTHONPATH=/app:/app/shared

# Expose port
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]