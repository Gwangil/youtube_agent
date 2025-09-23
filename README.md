# YouTube Agent 🤖

YouTube 채널 콘텐츠를 자동으로 수집하고 AI 기반 질의응답을 제공하는 지능형 콘텐츠 분석 플랫폼

## ✨ 주요 기능

- 🎥 **YouTube 콘텐츠 자동 수집** - 채널별 영상 자동 다운로드 및 처리
- 🎙️ **고품질 STT 처리** - GPU(Whisper Large-v3) 또는 OpenAI API 선택 가능
- 🔍 **RAG 기반 검색** - 타임스탬프 링크 포함 정확한 답변
- 💰 **비용 관리 시스템** - OpenAI API 사용 시 자동 비용 제한
- 🖥️ **유연한 인프라** - GPU/CPU 환경 자동 감지 및 최적 모드 실행
- 📊 **콘텐츠 관리 시스템** - Soft Delete 및 개별/일괄 활성화 제어
- 🔄 **Vector DB 동기화** - 실시간 콘텐츠 상태 반영

## 🚀 빠른 시작

### 1. 자동 실행 (권장)
```bash
# 환경 자동 감지 후 최적 모드로 실행
./start.sh
```

### 2. 수동 실행
```bash
# GPU 환경 (Whisper Large-v3)
./start_gpu.sh

# CPU 환경 (OpenAI API)
./start_cpu.sh
```

## 📋 요구사항

### 공통
- Docker & Docker Compose
- 8GB+ RAM
- OpenAI API Key (필수)

### GPU 모드 추가 요구사항
- NVIDIA GPU (VRAM 8GB+)
- NVIDIA Driver & CUDA
- nvidia-docker

## 🔧 설정

### 1. 환경 변수 설정
`.env` 파일 생성:
```bash
# OpenAI API Key (필수)
OPENAI_API_KEY=sk-your-api-key-here

# STT 비용 제한 (OpenAI API 사용 시)
# 일일 한도 (USD)
STT_DAILY_COST_LIMIT=10.0
# 월별 한도 (USD)
STT_MONTHLY_COST_LIMIT=100.0
# 단일 영상 한도 (USD)
STT_SINGLE_VIDEO_LIMIT=2.0
# 자동 승인 임계값 (USD)
STT_AUTO_APPROVE_THRESHOLD=0.10
```

### 2. 환경 확인
```bash
# 시스템 환경 감지
./scripts/detect_environment.sh
```

## 🏗️ 아키텍처

### 모드별 구성
```
📦 기본 인프라 (docker-compose.base.yml)
├── PostgreSQL - 메타데이터
├── Redis - 작업 큐
├── Qdrant - 벡터 DB
└── 관리/모니터링 서비스

🎮 GPU 모드 (docker-compose.gpu.yml)
├── Whisper Large-v3 서버
├── BGE-M3 임베딩 (GPU 가속)
└── 3개 STT 워커

☁️ CPU 모드 (docker-compose.cpu.yml)
├── OpenAI Whisper API
├── OpenAI Embeddings
└── 5개 STT 워커 (병렬 처리)
```

## 📊 서비스 접속

| 서비스 | URL | 설명 |
|--------|-----|------|
| OpenWebUI | http://localhost:3000 | 채팅 인터페이스 |
| Admin Dashboard | http://localhost:8090 | 통합 관리 |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Monitoring | http://localhost:8081 | 시스템 모니터링 |
| Cost Management | http://localhost:8084 | STT 비용 관리 |

## 🔄 데이터 처리 흐름

```
YouTube URL 입력
    ↓
영상 다운로드
    ↓
STT 처리 (GPU/API)
    ↓
문장 기반 청킹 (300-800자)
    ↓
벡터 임베딩
    ↓
Qdrant 저장
    ↓
RAG 검색 가능
```

## 🛠️ 관리 명령어

### 안전한 서비스 관리
```bash
# === 안전한 종료 (처리 중인 작업 완료 대기) ===
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml stop
# 또는
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml stop

# === 서비스 재시작 ===
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml restart

# === 완전 종료 ===
# 컨테이너만 제거 (데이터 유지)
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down

# 컨테이너와 데이터 모두 제거 (초기화)
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down -v

# 고아 컨테이너 정리
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans
```

### 개별 서비스 제어
```bash
# 주요 서비스 재시작
docker restart youtube_agent_service      # RAG 에이전트
docker restart youtube_data_processor     # 데이터 처리
docker restart youtube_whisper_server     # GPU STT 서버
docker restart youtube_admin_dashboard    # 관리 대시보드

# 로그 확인
docker logs [container_name] --tail 50 -f

# 실시간 상태 모니터링
docker stats --no-stream

# 오래된 컨테이너 정리
./scripts/cleanup_old_containers.sh
```

### 데이터 백업 및 복구
```bash
# === PostgreSQL 백업 ===
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent > backup_$(date +%Y%m%d).sql

# === PostgreSQL 복구 ===
docker exec -i youtube_postgres psql -U youtube_user -d youtube_agent < backup_20250923.sql

# === Qdrant 백업 ===
docker exec youtube_qdrant tar -czf /tmp/qdrant_backup.tar.gz /qdrant/storage
docker cp youtube_qdrant:/tmp/qdrant_backup.tar.gz ./qdrant_backup_$(date +%Y%m%d).tar.gz

# === 전체 볼륨 백업 ===
docker run --rm -v youtube_agent_postgres_data:/data -v $(pwd):/backup alpine tar -czf /backup/postgres_data_$(date +%Y%m%d).tar.gz -C /data .
docker run --rm -v youtube_agent_qdrant_data:/data -v $(pwd):/backup alpine tar -czf /backup/qdrant_data_$(date +%Y%m%d).tar.gz -C /data .

# 고아 컨테이너 정리
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml down --remove-orphans
```

### 데이터 관리
```bash
# 채널 관리 (추가/활성화/비활성화)
http://localhost:8090/channels

# 콘텐츠 관리 (개별/일괄 제어, 정렬, 필터링)
http://localhost:8090/contents

# 처리 상태 모니터링
http://localhost:8081

# 비용 승인 (OpenAI API 모드)
http://localhost:8084

# 데이터베이스 백업
docker exec youtube_postgres pg_dump -U youtube_user youtube_agent > backup.sql

# 데이터베이스 복구
docker exec -i youtube_postgres psql -U youtube_user youtube_agent < backup.sql
```

---

## 📚 프로젝트 문서

### 핵심 문서
- [README.md](./README.md) - 프로젝트 개요 (이 문서)
- [CLAUDE.md](./CLAUDE.md) - 개발자 가이드

### 상세 문서 (docs 폴더)
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) - 시스템 아키텍처
- [ROADMAP.md](./docs/ROADMAP.md) - 개발 로드맵
- [PROJECT_STATUS.md](./docs/PROJECT_STATUS.md) - 현재 프로젝트 상태
- [TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md) - 문제 해결 가이드
- [PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md) - 프로젝트 구조

## 🚨 문제 해결

### Docker 네트워크 오류
```bash
# 네트워크 재생성
./scripts/fix_network.sh

# 오래된 컨테이너 경고 해결
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml down --remove-orphans
```

### GPU 인식 실패
```bash
# GPU 상태 확인
nvidia-smi

# Docker GPU 지원 확인
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# CPU 모드로 전환
./start_cpu.sh
```

### OpenAI API 오류
```bash
# API 키 확인
echo $OPENAI_API_KEY

# 비용 한도 확인
http://localhost:8084

# 비용 한도 조정 (.env)
STT_DAILY_COST_LIMIT=20.0
STT_AUTO_APPROVE_THRESHOLD=0.50
```

### .env 파일 오류
```bash
# 인라인 주석 제거 필요
# 잘못된 예: KEY=value # comment
# 올바른 예:
# comment
KEY=value

# 환경변수 재로드
source .env
```

## 📈 성능 최적화

### GPU 모드
- Whisper Large-v3: 실시간 대비 0.3x 처리 속도
- BGE-M3 임베딩: 1024차원 고품질 벡터
- VRAM 사용량: 6-8GB

### CPU 모드 (OpenAI API)
- 병렬 처리: 5개 워커 동시 실행
- API 비용 최적화: 자동 청킹 및 캐싱
- 폴백 메커니즘: GPU 실패 시 자동 전환

## 🧪 테스트

```bash
# 환경 감지 테스트
./scripts/detect_environment.sh

# STT 처리 테스트
curl -X POST http://localhost:8082/transcribe \
  -F "audio=@test.mp3" \
  -F "language=ko"

# RAG 검색 테스트
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "테스트 쿼리", "limit": 5}'
```

## 📚 추가 문서

- [PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md) - 프로젝트 구조
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) - 상세 아키텍처 설명
- [CLAUDE.md](./docs/CLAUDE.md) - 개발자 가이드
- [TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md) - 문제 해결 가이드

## 🤝 기여

Issues와 Pull Requests를 환영합니다!

## 📄 라이선스

MIT License

---
🤖 Powered by Claude & OpenAI