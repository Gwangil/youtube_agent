#!/bin/bash

# Set timeout configurations
export AIOHTTP_CLIENT_TIMEOUT=${AIOHTTP_CLIENT_TIMEOUT:-120}
export REQUEST_TIMEOUT=${REQUEST_TIMEOUT:-120}
export OPENAI_API_REQUEST_TIMEOUT=${OPENAI_API_REQUEST_TIMEOUT:-120}

# Wait for agent service to be ready
echo "Waiting for agent service to be ready..."
while ! curl -f http://agent-service:8000/health > /dev/null 2>&1; do
    echo "Agent service not ready, waiting..."
    sleep 5
done

echo "Agent service is ready. Starting OpenWebUI..."
echo "Timeout settings: AIOHTTP_CLIENT_TIMEOUT=$AIOHTTP_CLIENT_TIMEOUT, REQUEST_TIMEOUT=$REQUEST_TIMEOUT"

# Start the original OpenWebUI using the default command
cd /app/backend
exec bash start.sh