# YouTube Content Agent - Makefile
# 프로젝트 빌드, 배포, 관리를 위한 Make 명령어 모음

.PHONY: help build up down logs clean test dev prod

# 기본 명령어 (help 표시)
.DEFAULT_GOAL := help

# 색상 정의
YELLOW := \033[1;33m
GREEN := \033[1;32m
RED := \033[1;31m
NC := \033[0m # No Color

help:  ## 사용 가능한 명령어 표시
	@echo "${GREEN}YouTube Content Agent - 명령어 목록${NC}"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "사용법:\n  make ${YELLOW}<target>${NC}\n\n대상:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  ${YELLOW}%-20s${NC} %s\n", $$1, $$2 } /^##@/ { printf "\n${GREEN}%s${NC}\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ 🚀 빠른 시작

init:  ## 초기 설정 (환경 파일 생성, 디렉토리 확인)
	@echo "${GREEN}초기 환경 설정 중...${NC}"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "${YELLOW}.env 파일이 생성되었습니다. OpenAI API Key를 설정해주세요.${NC}"; \
	else \
		echo "${GREEN}.env 파일이 이미 존재합니다.${NC}"; \
	fi
	@mkdir -p logs models data
	@echo "${GREEN}초기 설정 완료!${NC}"

quickstart: init build up  ## 빠른 시작 (초기 설정 + 빌드 + 시작)
	@echo "${GREEN}YouTube Content Agent가 시작되었습니다!${NC}"
	@echo "OpenWebUI: http://localhost:3000"
	@echo "API Docs: http://localhost:8000/docs"

##@ 🏗️ Docker 관리

build:  ## Docker 이미지 빌드
	@echo "${GREEN}Docker 이미지 빌드 중...${NC}"
	docker-compose build

build-no-cache:  ## 캐시 없이 Docker 이미지 빌드
	@echo "${GREEN}캐시 없이 Docker 이미지 빌드 중...${NC}"
	docker-compose build --no-cache

up:  ## 모든 서비스 시작 (백그라운드)
	@echo "${GREEN}서비스 시작 중...${NC}"
	docker-compose up -d
	@echo "${GREEN}모든 서비스가 시작되었습니다!${NC}"

down:  ## 모든 서비스 중지
	@echo "${YELLOW}서비스 중지 중...${NC}"
	docker-compose down

restart:  ## 모든 서비스 재시작
	@echo "${YELLOW}서비스 재시작 중...${NC}"
	docker-compose restart

pause:  ## 모든 서비스 일시 정지 (메모리 유지)
	@echo "${YELLOW}서비스 일시 정지 중...${NC}"
	docker-compose pause
	@echo "${GREEN}서비스가 일시 정지되었습니다. 'make unpause'로 재개할 수 있습니다.${NC}"

unpause:  ## 일시 정지된 서비스 재개
	@echo "${GREEN}서비스 재개 중...${NC}"
	docker-compose unpause
	@echo "${GREEN}서비스가 재개되었습니다!${NC}"

stop:  ## 모든 서비스 정지 (컨테이너 유지)
	@echo "${YELLOW}서비스 정지 중...${NC}"
	docker-compose stop
	@echo "${GREEN}서비스가 정지되었습니다. 'make start'로 시작할 수 있습니다.${NC}"

start:  ## 정지된 서비스 시작
	@echo "${GREEN}서비스 시작 중...${NC}"
	docker-compose start
	@echo "${GREEN}서비스가 시작되었습니다!${NC}"

safe-stop:  ## 안전한 서비스 정지 (작업 완료 대기)
	@echo "${YELLOW}안전한 서비스 정지 시작...${NC}"
	@docker exec youtube_data_processor python /app/scripts/graceful_shutdown.py --mode stop --grace 30
	@docker-compose stop
	@echo "${GREEN}서비스가 안전하게 정지되었습니다.${NC}"

safe-start:  ## 안전한 서비스 시작 (stuck 작업 정리)
	@echo "${GREEN}안전한 서비스 시작...${NC}"
	@docker-compose start
	@sleep 5
	@docker exec youtube_data_processor python /app/scripts/graceful_shutdown.py --mode start
	@echo "${GREEN}서비스가 안전하게 시작되었습니다!${NC}"

status: ps  ## 서비스 상태 확인 (ps와 동일)

ps:  ## 실행 중인 컨테이너 표시
	@docker-compose ps

##@ 📊 로그 및 모니터링

logs:  ## 모든 서비스 로그 표시 (실시간)
	docker-compose logs -f --tail=100

logs-collector:  ## Data Collector 서비스 로그
	docker-compose logs -f data-collector --tail=100

logs-processor:  ## Data Processor 서비스 로그
	docker-compose logs -f data-processor --tail=100

logs-agent:  ## Agent Service 로그
	docker-compose logs -f agent-service --tail=100

logs-ui:  ## UI Service (OpenWebUI) 로그
	docker-compose logs -f ui-service --tail=100

logs-error:  ## 에러 로그만 표시
	@docker-compose logs --tail=1000 | grep -E "ERROR|CRITICAL|FATAL" || echo "${GREEN}에러 로그가 없습니다.${NC}"

monitor:  ## 시스템 모니터링 대시보드 열기
	@echo "${GREEN}모니터링 URL:${NC}"
	@echo "  Agent API: http://localhost:8000/docs"
	@echo "  OpenWebUI: http://localhost:3000"
	@echo "  Qdrant: http://localhost:6333/dashboard"

stats:  ## Docker 컨테이너 리소스 사용량
	docker stats

##@ 💾 데이터베이스 관리

db-shell:  ## PostgreSQL 쉘 접속
	docker-compose exec postgres psql -U youtube_user -d youtube_agent

db-backup:  ## 데이터베이스 백업 생성
	@echo "${GREEN}데이터베이스 백업 중...${NC}"
	@mkdir -p backups
	docker-compose exec postgres pg_dump -U youtube_user youtube_agent > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "${GREEN}백업 완료: backups/backup_$(shell date +%Y%m%d_%H%M%S).sql${NC}"

db-restore:  ## 데이터베이스 복원 (사용법: make db-restore FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "${RED}오류: FILE 파라미터가 필요합니다. 예: make db-restore FILE=backup.sql${NC}"; \
		exit 1; \
	fi
	@echo "${YELLOW}데이터베이스 복원 중: $(FILE)${NC}"
	cat $(FILE) | docker-compose exec -T postgres psql -U youtube_user -d youtube_agent
	@echo "${GREEN}복원 완료!${NC}"

db-reset:  ## 데이터베이스 초기화 (주의: 모든 데이터 삭제!)
	@echo "${RED}경고: 모든 데이터가 삭제됩니다!${NC}"
	@read -p "계속하시겠습니까? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	docker-compose exec postgres psql -U youtube_user -d youtube_agent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "${GREEN}데이터베이스가 초기화되었습니다.${NC}"

##@ 🔍 데이터 정합성 및 초기화

check-data:  ## 데이터 정합성 체크 (PostgreSQL과 Qdrant 동기화 확인)
	@echo "${GREEN}데이터 정합성 체크 시작...${NC}"
	@docker exec youtube_data_processor python /app/scripts/data_integrity_check.py

check-data-fix:  ## 데이터 정합성 체크 및 자동 수정
	@echo "${GREEN}데이터 정합성 체크 및 수정 시작...${NC}"
	@docker exec youtube_data_processor python /app/scripts/data_integrity_check.py --fix

reset-soft:  ## 소프트 리셋 (채널 정보 보존, 콘텐츠만 삭제)
	@echo "${YELLOW}소프트 리셋: 콘텐츠 데이터만 삭제됩니다 (채널 정보는 보존)${NC}"
	@echo "${YELLOW}이 작업은 되돌릴 수 없습니다!${NC}"
	@read -p "계속하시겠습니까? (yes/no): " confirm && [ "$$confirm" = "yes" ] || exit 1
	@docker exec youtube_data_processor python /app/scripts/data_reset.py --mode soft --force

reset-hard:  ## 하드 리셋 (모든 데이터 완전 삭제)
	@echo "${RED}하드 리셋: 모든 데이터가 완전히 삭제됩니다!${NC}"
	@echo "${RED}채널 정보를 포함한 모든 데이터가 영구 삭제됩니다!${NC}"
	@read -p "정말로 계속하시겠습니까? (type 'DELETE ALL' to confirm): " confirm && [ "$$confirm" = "DELETE ALL" ] || exit 1
	@docker exec youtube_data_processor python /app/scripts/data_reset.py --mode hard --force

reset-stuck-jobs:  ## 멈춘 작업만 초기화
	@echo "${GREEN}멈춘 작업 초기화 중...${NC}"
	@docker exec youtube_data_processor python -c "\
	from scripts.data_integrity_check import DataIntegrityChecker; \
	checker = DataIntegrityChecker(); \
	checker.reset_stuck_jobs()"

clean-orphans:  ## 고아 데이터 정리 (Qdrant의 불일치 벡터 삭제)
	@echo "${GREEN}고아 벡터 정리 중...${NC}"
	@docker exec youtube_data_processor python -c "\
	from scripts.data_integrity_check import DataIntegrityChecker; \
	checker = DataIntegrityChecker(); \
	checker.fix_orphaned_vectors()"

##@ 🧪 테스트 및 검증

test-health:  ## API 헬스체크
	@echo "${GREEN}헬스체크 실행 중...${NC}"
	@curl -s http://localhost:8000/health | python -m json.tool || echo "${RED}API 서버가 응답하지 않습니다.${NC}"

test-search:  ## 검색 API 테스트
	@echo "${GREEN}검색 API 테스트...${NC}"
	@curl -s -X POST "http://localhost:8000/search" \
		-H "Content-Type: application/json" \
		-d '{"query": "경제", "limit": 3}' | python -m json.tool

test-chat:  ## 채팅 API 테스트
	@echo "${GREEN}채팅 API 테스트...${NC}"
	@curl -s -X POST "http://localhost:8000/v1/chat/completions" \
		-H "Content-Type: application/json" \
		-d '{"model": "youtube-agent", "messages": [{"role": "user", "content": "안녕하세요"}]}' | python -m json.tool

test-all: test-health test-search test-chat  ## 모든 API 테스트 실행

validate:  ## 설정 파일 검증
	@echo "${GREEN}설정 파일 검증 중...${NC}"
	@docker-compose config > /dev/null && echo "${GREEN}docker-compose.yml: OK${NC}" || echo "${RED}docker-compose.yml: 오류${NC}"
	@[ -f .env ] && echo "${GREEN}.env 파일: OK${NC}" || echo "${RED}.env 파일: 없음${NC}"
	@[ -f requirements.txt ] && echo "${GREEN}requirements.txt: OK${NC}" || echo "${RED}requirements.txt: 없음${NC}"

##@ 🧹 정리 및 유지보수

clean:  ## 중지된 컨테이너와 볼륨 정리
	@echo "${YELLOW}정리 중...${NC}"
	docker-compose down -v
	docker system prune -f
	@echo "${GREEN}정리 완료!${NC}"

clean-all:  ## 모든 것 정리 (이미지 포함, 주의!)
	@echo "${RED}경고: 모든 Docker 이미지와 볼륨이 삭제됩니다!${NC}"
	@read -p "계속하시겠습니까? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	docker-compose down -v --rmi all
	docker system prune -af --volumes
	@echo "${GREEN}모든 정리 완료!${NC}"

clean-logs:  ## 로그 파일 정리
	@echo "${YELLOW}로그 파일 정리 중...${NC}"
	@rm -rf logs/*.log logs/*.txt
	@echo "${GREEN}로그 정리 완료!${NC}"

##@ 🔧 개발 도구

dev:  ## 개발 모드로 시작 (로그 표시)
	docker-compose up

shell-processor:  ## Data Processor 컨테이너 쉘 접속
	docker exec -it youtube_data_processor /bin/bash

shell-agent:  ## Agent Service 컨테이너 쉘 접속
	docker exec -it youtube_agent_service /bin/bash

shell-collector:  ## Data Collector 컨테이너 쉘 접속
	docker exec -it youtube_data_collector /bin/bash

python-shell:  ## Python 대화형 쉘 (Agent Service)
	docker exec -it youtube_agent_service python

check-jobs:  ## 처리 작업 상태 확인
	@docker exec youtube_data_processor python -c "\
	from shared.models.database import ProcessingJob, get_database_url; \
	from sqlalchemy import create_engine, func; \
	from sqlalchemy.orm import sessionmaker; \
	engine = create_engine(get_database_url()); \
	SessionLocal = sessionmaker(bind=engine); \
	db = SessionLocal(); \
	stats = db.query(ProcessingJob.status, func.count(ProcessingJob.id)).group_by(ProcessingJob.status).all(); \
	print('작업 상태:'); \
	for status, count in stats: print(f'  {status}: {count}개')"

##@ 📦 백업 및 복구

backup-all:  ## 전체 시스템 백업 (DB + 설정)
	@echo "${GREEN}전체 백업 시작...${NC}"
	@mkdir -p backups
	@make db-backup
	@cp .env backups/.env.backup
	@cp docker-compose.yml backups/docker-compose.yml.backup
	@tar -czf backups/full_backup_$(shell date +%Y%m%d_%H%M%S).tar.gz backups/*.sql backups/*.backup
	@echo "${GREEN}전체 백업 완료!${NC}"

##@ 🚀 프로덕션

prod-deploy:  ## 프로덕션 배포
	@echo "${GREEN}프로덕션 배포 시작...${NC}"
	@make validate
	@make build
	@make up
	@sleep 5
	@make test-health
	@echo "${GREEN}프로덕션 배포 완료!${NC}"

prod-update:  ## 프로덕션 업데이트 (무중단)
	@echo "${GREEN}무중단 업데이트 시작...${NC}"
	@docker-compose pull
	@docker-compose up -d --no-deps --build agent-service
	@sleep 5
	@make test-health
	@echo "${GREEN}업데이트 완료!${NC}"

##@ ℹ️ 정보

version:  ## 버전 정보 표시
	@echo "${GREEN}YouTube Content Agent${NC}"
	@echo "Version: 1.0.0"
	@echo "Docker: $(shell docker --version | cut -d' ' -f3 | cut -d',' -f1)"
	@echo "Docker Compose: $(shell docker-compose --version | cut -d' ' -f4 | cut -d',' -f1)"

info:  ## 시스템 정보 표시
	@echo "${GREEN}시스템 정보${NC}"
	@echo "OS: $(shell uname -s)"
	@echo "Architecture: $(shell uname -m)"
	@echo "CPU Cores: $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 'N/A')"
	@echo "Memory: $(shell free -h 2>/dev/null | grep Mem | awk '{print $$2}' || echo 'N/A')"
	@echo ""
	@make version

# 개발자용 숨겨진 명령어
debug:  ## [숨김] 디버그 정보 출력
	@echo "Environment Variables:"
	@cat .env | grep -v "^#" | grep -v "^$$"
	@echo ""
	@echo "Running Containers:"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Makefile 자체 검증
check-makefile:  ## [숨김] Makefile 문법 검증
	@echo "Checking Makefile syntax..."
	@make -n help > /dev/null 2>&1 && echo "✓ Makefile is valid" || echo "✗ Makefile has errors"