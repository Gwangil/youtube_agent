# YouTube Agent - Makefile
# GPU/CPU 모드 분리 구성을 위한 Make 명령어
# 최종 업데이트: 2025-09-23

.PHONY: help start start-gpu start-cpu stop clean logs status test

# 기본 명령어 (help 표시)
.DEFAULT_GOAL := help

# 색상 정의
YELLOW := \033[1;33m
GREEN := \033[1;32m
RED := \033[1;31m
BLUE := \033[1;34m
NC := \033[0m # No Color

help: ## 사용 가능한 명령어 표시
	@echo "${GREEN}YouTube Agent - Docker Compose Multi-Mode${NC}"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "사용법:\n  make ${YELLOW}<command>${NC}\n\n명령어:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  ${YELLOW}%-20s${NC} %s\n", $$1, $$2 } /^##@/ { printf "\n${BLUE}%s${NC}\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ 🚀 빠른 시작

start: ## 환경 자동 감지 후 최적 모드로 시작
	@echo "${GREEN}환경 감지 중...${NC}"
	@./start.sh

start-gpu: ## GPU 모드로 시작 (Whisper Large-v3)
	@echo "${GREEN}GPU 모드로 시작...${NC}"
	@./start_gpu.sh

start-cpu: ## CPU 모드로 시작 (OpenAI API)
	@echo "${GREEN}CPU/OpenAI API 모드로 시작...${NC}"
	@./start_cpu.sh

stop: ## 현재 실행 중인 모드 중지
	@echo "${YELLOW}서비스 중지 중...${NC}"
	@if [ -f .detected_mode ]; then \
		MODE=$$(cat .detected_mode); \
		echo "현재 모드: $$MODE"; \
		if [ "$$MODE" = "gpu" ]; then \
			docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans; \
		else \
			docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans; \
		fi; \
	else \
		echo "${RED}모드 감지 실패. 모든 서비스 중지...${NC}"; \
		docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans 2>/dev/null; \
		docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans 2>/dev/null; \
	fi
	@echo "${GREEN}서비스가 중지되었습니다.${NC}"

restart: stop start ## 서비스 재시작

##@ 🔄 모드 전환

switch-to-gpu: ## CPU → GPU 모드 전환
	@echo "${YELLOW}CPU 모드 중지 중...${NC}"
	@docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans
	@echo "${GREEN}GPU 모드로 전환 중...${NC}"
	@./start_gpu.sh

switch-to-cpu: ## GPU → CPU 모드 전환
	@echo "${YELLOW}GPU 모드 중지 중...${NC}"
	@docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans
	@echo "${GREEN}CPU 모드로 전환 중...${NC}"
	@./start_cpu.sh

##@ 📊 모니터링

status: ## 서비스 상태 확인
	@echo "${GREEN}=== 서비스 상태 ===${NC}"
	@if [ -f .detected_mode ]; then \
		echo "현재 모드: $$(cat .detected_mode)"; \
	fi
	@docker ps --filter "name=youtube" --format "table {{.Names}}\t{{.Status}}\t{{.State}}"

logs: ## 모든 서비스 로그 표시 (실시간)
	@if [ -f .detected_mode ]; then \
		MODE=$$(cat .detected_mode); \
		if [ "$$MODE" = "gpu" ]; then \
			docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml logs -f --tail=100; \
		else \
			docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml logs -f --tail=100; \
		fi; \
	else \
		docker-compose -f docker-compose.base.yml logs -f --tail=100; \
	fi

logs-agent: ## Agent Service 로그
	@docker logs -f youtube_agent_service --tail=100

logs-processor: ## Data Processor 로그
	@docker logs -f youtube_data_processor --tail=100

logs-collector: ## Data Collector 로그
	@docker logs -f youtube_data_collector --tail=100

logs-admin: ## Admin Dashboard 로그
	@docker logs -f youtube_admin_dashboard --tail=100

logs-cost: ## STT Cost API 로그
	@docker logs -f youtube_stt_cost_api --tail=100

logs-whisper: ## Whisper Server 로그 (GPU 모드)
	@docker logs -f youtube_whisper_server --tail=100 2>/dev/null || echo "Whisper server not running (CPU mode?)"

##@ 🌐 서비스 접속

open-ui: ## OpenWebUI 열기 (브라우저)
	@echo "${GREEN}Opening OpenWebUI...${NC}"
	@python3 -m webbrowser http://localhost:3000 2>/dev/null || echo "URL: http://localhost:3000"

open-admin: ## Admin Dashboard 열기
	@echo "${GREEN}Opening Admin Dashboard...${NC}"
	@python3 -m webbrowser http://localhost:8090 2>/dev/null || echo "URL: http://localhost:8090"

open-cost: ## Cost Management 열기
	@echo "${GREEN}Opening Cost Management...${NC}"
	@python3 -m webbrowser http://localhost:8084 2>/dev/null || echo "URL: http://localhost:8084"

open-api: ## API Docs 열기 (Swagger)
	@echo "${GREEN}Opening API Docs...${NC}"
	@python3 -m webbrowser http://localhost:8000/docs 2>/dev/null || echo "URL: http://localhost:8000/docs"

urls: ## 모든 서비스 URL 표시
	@echo "${GREEN}=== 서비스 URL ===${NC}"
	@echo "OpenWebUI:        http://localhost:3000"
	@echo "Admin Dashboard:  http://localhost:8090"
	@echo "API Docs:         http://localhost:8000/docs"
	@echo "Cost Management:  http://localhost:8084"
	@echo "Monitoring:       http://localhost:8081"
	@echo "Qdrant:          http://localhost:6333"

##@ 💾 데이터 관리

db-shell: ## PostgreSQL 쉘 접속
	@docker exec -it youtube_postgres psql -U youtube_user -d youtube_agent

db-backup: ## 데이터베이스 백업
	@mkdir -p backups
	@BACKUP_FILE="backups/backup_$$(date +%Y%m%d_%H%M%S).sql"; \
	docker exec youtube_postgres pg_dump -U youtube_user youtube_agent > $$BACKUP_FILE && \
	echo "${GREEN}백업 완료: $$BACKUP_FILE${NC}"

db-restore: ## 데이터베이스 복원 (사용: make db-restore FILE=backups/backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "${RED}오류: FILE 파라미터 필요. 예: make db-restore FILE=backups/backup.sql${NC}"; \
		exit 1; \
	fi
	@echo "${YELLOW}복원 중: $(FILE)${NC}"
	@docker exec -i youtube_postgres psql -U youtube_user youtube_agent < $(FILE)
	@echo "${GREEN}복원 완료!${NC}"

##@ 🧪 테스트

test-env: ## 환경 감지 테스트
	@./scripts/detect_environment.sh

test-gpu: ## GPU 사용 가능 여부 확인
	@echo "${GREEN}GPU 확인 중...${NC}"
	@nvidia-smi 2>/dev/null && echo "${GREEN}GPU 사용 가능${NC}" || echo "${YELLOW}GPU 사용 불가${NC}"

test-api: ## API 헬스체크
	@echo "${GREEN}API 상태 확인...${NC}"
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo "${RED}API 응답 없음${NC}"

##@ 🧹 정리

clean: ## 오래된 컨테이너 및 네트워크 정리
	@echo "${YELLOW}정리 시작...${NC}"
	@./scripts/cleanup_old_containers.sh

clean-logs: ## 로그 파일 정리
	@echo "${YELLOW}로그 정리 중...${NC}"
	@find /var/lib/docker/containers -name "*-json.log" -exec truncate -s 0 {} \; 2>/dev/null || \
		echo "${YELLOW}권한이 필요합니다. sudo로 실행하세요.${NC}"

clean-volumes: ## 미사용 볼륨 정리 (주의!)
	@echo "${RED}경고: 미사용 볼륨을 삭제합니다.${NC}"
	@read -p "계속하시겠습니까? (y/n): " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker volume prune -f; \
		echo "${GREEN}볼륨 정리 완료${NC}"; \
	fi

prune: ## Docker 시스템 정리 (전체)
	@echo "${YELLOW}Docker 시스템 정리...${NC}"
	@docker system prune -af --volumes
	@echo "${GREEN}정리 완료!${NC}"

##@ 🛠️ 유틸리티

check-env: ## .env 파일 확인
	@if [ -f .env ]; then \
		echo "${GREEN}.env 파일 확인:${NC}"; \
		grep -E "^[A-Z]" .env | sed 's/=.*/=***/' | head -10; \
		echo "..."; \
	else \
		echo "${RED}.env 파일이 없습니다!${NC}"; \
	fi

fix-network: ## 네트워크 문제 해결
	@echo "${YELLOW}네트워크 문제 해결 중...${NC}"
	@./scripts/fix_network.sh

install-deps: ## 시스템 의존성 설치 (Ubuntu/Debian)
	@echo "${GREEN}시스템 의존성 설치...${NC}"
	@sudo apt-get update
	@sudo apt-get install -y docker.io docker-compose
	@echo "${GREEN}설치 완료!${NC}"

##@ 📚 문서

docs: ## 문서 위치 안내
	@echo "${GREEN}=== 문서 위치 ===${NC}"
	@echo "README.md                  - 프로젝트 개요 (루트)"
	@echo "docs/ARCHITECTURE.md       - 아키텍처 설명"
	@echo "docs/CLAUDE.md            - 개발자 가이드"
	@echo "docs/TROUBLESHOOTING.md   - 문제 해결 가이드"
	@echo "PROJECT_STRUCTURE.md      - 프로젝트 구조"

# 버전 정보
version: ## 버전 정보 표시
	@echo "${GREEN}YouTube Agent${NC}"
	@echo "Docker Compose 구성: base + gpu/cpu"
	@echo "최종 업데이트: 2025-09-23"
	@if [ -f .detected_mode ]; then \
		echo "현재 모드: $$(cat .detected_mode)"; \
	fi