#!/bin/bash

# Wait for agent service to be ready
echo "Waiting for agent service to be ready..."
while ! curl -f http://agent-service:8000/health > /dev/null 2>&1; do
    echo "Agent service not ready, waiting..."
    sleep 5
done

echo "Agent service is ready. Starting OpenWebUI..."

# Start the original OpenWebUI using the default command
cd /app/backend
exec bash start.sh