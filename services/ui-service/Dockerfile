FROM ghcr.io/open-webui/open-webui:latest

# Copy custom configuration if needed
# COPY config/open-webui.yaml /app/backend/data/

# Set environment variables for podcast agent integration
ENV OPENAI_API_BASE_URL=http://agent-service:8000/v1
ENV OPENAI_API_KEY=dummy-key

# Custom startup script
COPY services/ui-service/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]