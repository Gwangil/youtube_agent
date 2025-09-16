# Makefile for Podcast Agent

.PHONY: help build up down logs clean test

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

setup:  ## Initial setup - copy env file and build images
	cp .env.example .env
	@echo "Please edit .env file with your API keys"
	@echo "Then run 'make build' to build the images"

build:  ## Build all Docker images
	docker-compose build

up:  ## Start all services
	docker-compose up -d

down:  ## Stop all services
	docker-compose down

restart:  ## Restart all services
	docker-compose restart

logs:  ## Show logs for all services
	docker-compose logs -f

logs-collector:  ## Show logs for data collector
	docker-compose logs -f data-collector

logs-processor:  ## Show logs for data processor
	docker-compose logs -f data-processor

logs-agent:  ## Show logs for agent service
	docker-compose logs -f agent-service

logs-ui:  ## Show logs for UI service
	docker-compose logs -f ui-service

##@ Maintenance

clean:  ## Clean up containers and volumes
	docker-compose down -v
	docker system prune -f

clean-all:  ## Clean up everything including images
	docker-compose down -v --rmi all
	docker system prune -af

clean-volumes:  ## Clean up only volumes (data will be lost!)
	docker-compose down
	docker volume rm podcast_agent_postgres_data podcast_agent_redis_data podcast_agent_qdrant_data podcast_agent_openwebui_data 2>/dev/null || true

ps:  ## Show running containers
	docker-compose ps

stats:  ## Show container stats
	docker stats

##@ Database

db-shell:  ## Connect to PostgreSQL shell
	docker-compose exec postgres psql -U podcast_user -d podcast_agent

db-backup:  ## Backup database
	docker-compose exec postgres pg_dump -U podcast_user podcast_agent > backup_$(shell date +%Y%m%d_%H%M%S).sql

db-restore:  ## Restore database (usage: make db-restore FILE=backup.sql)
	cat $(FILE) | docker-compose exec -T postgres psql -U podcast_user -d podcast_agent

##@ API Testing

test-health:  ## Test service health
	curl -s http://localhost:8000/health | jq

test-search:  ## Test content search
	curl -s -X POST "http://localhost:8000/search" \
		-H "Content-Type: application/json" \
		-d '{"query": "test", "limit": 5}' | jq

test-ask:  ## Test ask endpoint
	curl -s -X POST "http://localhost:8000/ask" \
		-H "Content-Type: application/json" \
		-d '{"query": "안녕하세요"}' | jq

test-stats:  ## Get service statistics
	curl -s http://localhost:8000/stats | jq

##@ Monitoring

monitor:  ## Start monitoring dashboard
	@echo "Opening monitoring URLs..."
	@echo "Agent API: http://localhost:8000/docs"
	@echo "OpenWebUI: http://localhost:3000"
	@echo "Qdrant: http://localhost:6333/dashboard"

tail-logs:  ## Tail logs for all services
	docker-compose logs -f --tail=50