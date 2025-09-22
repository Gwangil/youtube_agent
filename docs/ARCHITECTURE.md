# YouTube Agent 아키텍처 가이드

## 📌 개요

YouTube Agent는 인프라 환경에 따라 **GPU 모드**와 **CPU 모드**를 선택적으로 운영할 수 있는 유연한 아키텍처를 제공합니다.

## 🏗️ 아키텍처 구조

### 분리된 Docker Compose 구성
```
docker-compose.base.yml  # 공통 인프라 (DB, Redis, Qdrant, UI)
docker-compose.gpu.yml   # GPU 전용 서비스 (Whisper Large-v3)
docker-compose.cpu.yml   # CPU 전용 서비스 (OpenAI API)
```

⚠️ **중요**: 이전 단일 `docker-compose.yml` 구성에서 마이그레이션한 경우,
`./scripts/cleanup_old_containers.sh` 스크립트를 실행하여 고아 컨테이너를 정리하세요.

### 서비스 구성도

```
┌─────────────────────────────────────────────────────────┐
│                    공통 인프라 (base)                      │
├─────────────────────────────────────────────────────────┤
│  • PostgreSQL    : 메타데이터 저장                         │
│  • Redis         : 작업 큐, 캐시                          │
│  • Qdrant        : 벡터 데이터베이스                       │
│  • Data Collector: YouTube 데이터 수집                     │
│  • STT Cost API  : 비용 관리                             │
│  • Monitoring    : 시스템 모니터링                         │
│  • Agent Service : RAG 에이전트                          │
│  • UI Service    : OpenWebUI                            │
│  • Admin Dashboard: 관리 대시보드                         │
└─────────────────────────────────────────────────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
    ┌───────────────────────┐ ┌───────────────────────┐
    │     GPU 모드           │ │     CPU 모드           │
    ├───────────────────────┤ ├───────────────────────┤
    │ • Whisper Server      │ │ • OpenAI STT Workers  │
    │   (Large-v3, GPU)     │ │   (5개 병렬 처리)      │
    │ • BGE-M3 Embedding    │ │ • OpenAI Embeddings   │
    │   (GPU 가속)          │ │   (API 호출)          │
    │ • STT Workers (3개)   │ │ • Vectorize Workers   │
    │ • Vectorize Workers   │ │   (3개)              │
    └───────────────────────┘ └───────────────────────┘
```

## 🚀 실행 방법

### 1. 자동 감지 및 시작
```bash
# 환경 자동 감지 후 적절한 모드로 시작
./start.sh
```

### 2. GPU 모드 강제 실행
```bash
# GPU가 있는 환경에서 Whisper Large-v3 사용
./start_gpu.sh

# 또는 수동 실행
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d
```

### 3. CPU 모드 강제 실행
```bash
# OpenAI API 사용 (GPU 없어도 가능)
./start_cpu.sh

# 또는 수동 실행
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d
```

### 4. 환경 감지만 수행
```bash
# 시스템 환경 확인
./scripts/detect_environment.sh
```

## 🔧 환경별 특징

### GPU 모드
- **요구사항**: NVIDIA GPU (VRAM 8GB 이상), CUDA 드라이버
- **모델**: Whisper Large-v3 (최고 품질)
- **임베딩**: BGE-M3 (1024차원, GPU 가속)
- **장점**:
  - 최고 품질의 STT 처리
  - API 비용 없음
  - 빠른 처리 속도
- **단점**:
  - GPU 하드웨어 필요
  - 높은 전력 소비

### CPU 모드
- **요구사항**: OpenAI API 키
- **모델**: OpenAI Whisper API
- **임베딩**: OpenAI Embeddings API
- **장점**:
  - GPU 불필요
  - 낮은 하드웨어 요구사항
  - 높은 병렬 처리 (5개 워커)
- **단점**:
  - API 비용 발생 ($0.006/분)
  - 네트워크 의존성

## 📊 비용 관리

### OpenAI API 비용 설정 (.env)
```bash
STT_DAILY_COST_LIMIT=10.0      # 일일 한도 $10
STT_MONTHLY_COST_LIMIT=100.0   # 월별 한도 $100
STT_SINGLE_VIDEO_LIMIT=2.0     # 단일 영상 $2
STT_AUTO_APPROVE_THRESHOLD=0.10 # $0.10 이하 자동승인
```

### 비용 관리 대시보드
- URL: http://localhost:8084
- 실시간 비용 모니터링
- 수동 승인/거부 기능

## 🔄 모드 전환

### GPU → CPU 전환
```bash
# 현재 서비스 중지 (고아 컨테이너 정리 포함)
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans

# CPU 모드 시작
./start_cpu.sh
```

### CPU → GPU 전환
```bash
# 현재 서비스 중지 (고아 컨테이너 정리 포함)
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans

# GPU 모드 시작
./start_gpu.sh
```

### 처음 설치 또는 구성 변경 후
```bash
# 이전 구성 완전 정리
./scripts/cleanup_old_containers.sh

# 환경 감지 및 자동 시작
./start.sh
```

## 📝 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| PostgreSQL | 5432 | 데이터베이스 |
| Redis | 6379 | 캐시/큐 |
| Qdrant | 6333 | 벡터 DB |
| Agent API | 8000 | RAG 에이전트 |
| Monitoring | 8081 | 모니터링 |
| Whisper Server | 8082 | GPU STT (GPU 모드) |
| Embedding Server | 8083 | 임베딩 서버 |
| STT Cost API | 8084 | 비용 관리 |
| Admin Dashboard | 8090 | 관리 대시보드 |
| OpenWebUI | 3000 | 채팅 인터페이스 |

## 🛠️ 문제 해결

### GPU 모드 실행 실패
```bash
# GPU 상태 확인
nvidia-smi

# Docker GPU 지원 확인
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# NVIDIA Container Toolkit 설치
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### CPU 모드 실행 실패
```bash
# OpenAI API 키 확인
echo $OPENAI_API_KEY

# .env 파일 확인
cat .env | grep OPENAI_API_KEY

# API 키 테스트
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 서비스 로그 확인
```bash
# GPU 모드
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml logs -f whisper-server

# CPU 모드
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml logs -f stt-worker-openai-1

# 공통
docker logs youtube_data_processor --tail 100
```

## 🔐 보안 고려사항

1. **API 키 관리**
   - `.env` 파일을 Git에 커밋하지 않기
   - 프로덕션 환경에서는 시크릿 관리 도구 사용

2. **네트워크 격리**
   - 내부 서비스는 Docker 네트워크 내에서만 통신
   - 필요한 포트만 외부 노출

3. **비용 제한**
   - OpenAI API 사용 시 반드시 비용 한도 설정
   - 정기적인 비용 모니터링

## 📈 성능 최적화

### GPU 모드
- Whisper 모델 크기 조정 (large-v3 → medium)
- 배치 처리 크기 최적화
- GPU 메모리 사용량 모니터링

### CPU 모드
- 워커 수 조정 (기본 5개)
- API 요청 속도 제한 고려
- 청킹 크기 최적화

## 🔄 업데이트 방법

```bash
# 코드 업데이트
git pull

# 현재 서비스 중지 (모드에 따라 선택)
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml down --remove-orphans

# 이미지 재빌드
docker-compose -f docker-compose.base.yml build
docker-compose -f docker-compose.gpu.yml build  # GPU 모드
docker-compose -f docker-compose.cpu.yml build  # CPU 모드

# 서비스 재시작
./start.sh
```

### 클린 설치 방법
```bash
# 모든 컨테이너와 볼륨 제거 (데이터 손실 주의!)
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down -v
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down -v

# 오래된 컨테이너 정리
./scripts/cleanup_old_containers.sh

# 새로 시작
./start.sh
```

---

## 📚 참고 문서

- [CLAUDE.md](./CLAUDE.md) - 프로젝트 전체 개요
- [README.md](../README.md) - 빠른 시작 가이드
- [API 문서](http://localhost:8000/docs) - Swagger UI

## 🔧 운영 및 유지보수

### 필수 점검 항목
```bash
# 서비스 상태 확인
docker ps --filter "name=youtube"

# 디스크 사용량
docker system df

# 로그 크기 확인
du -sh /var/lib/docker/containers/*/*-json.log

# 데이터베이스 상태
docker exec youtube_postgres pg_isready

# Qdrant 컴렉션 상태
curl http://localhost:6333/collections
```

### 정기 유지보수
```bash
# Docker 시스템 정리 (주 1회)
docker system prune -af --volumes

# 로그 로테이션 (월 1회)
find /var/lib/docker/containers -name "*-json.log" -exec truncate -s 0 {} \;

# 데이터베이스 백업 (일 1회)
docker exec youtube_postgres pg_dump -U youtube_user youtube_agent > backup_$(date +%Y%m%d).sql
```

마지막 업데이트: 2025-09-23