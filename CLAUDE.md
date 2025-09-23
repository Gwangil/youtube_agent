# CLAUDE.md

이 파일은 Claude Code가 이 프로젝트를 작업할 때 참고할 수 있는 개발자 가이드입니다.

## 📋 프로젝트 개요

**YouTube Content Agent**는 YouTube 채널 콘텐츠를 자동으로 수집, 처리하여 RAG(Retrieval-Augmented Generation) 기반 AI 질의응답 서비스를 제공하는 지능형 콘텐츠 분석 플랫폼입니다.

### 핵심 기능
- YouTube 채널 자동 수집 및 STT 처리 (Whisper Large-v3 GPU + OpenAI API 폴백)
- 문장 기반 의미 청킹으로 정확한 컨텍스트 보존 (300-800자 단위)
- YouTube 타임스탬프 링크가 포함된 RAG 답변 제공
- OpenAI 호환 API로 OpenWebUI 연동 지원 (타임아웃 120초)
- LangGraph 기반 지능형 에이전트 워크플로우
- STT 비용 관리 시스템 (일일/월별 한도 설정)
- **자동 데이터 품질 관리 시스템** (정합성 체크, 작업 복구, 모니터링 알림)

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   데이터 수집    │ -> │   데이터 처리    │ -> │   RAG 에이전트   │
│  (YouTube)      │    │ (STT+벡터화)     │    │  (질의응답)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         v                        v                        v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  PostgreSQL     │    │     Qdrant      │    │   OpenWebUI     │
│ (메타데이터)     │    │  (벡터 DB)      │    │ (채팅 인터페이스) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🐳 Docker 서비스 구성

### 실행 방법 (모드별 분리 구성)
```bash
# 환경 자동 감지 후 실행
./start.sh

# GPU 모드 강제 실행
./start_gpu.sh
# 또는
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml up -d

# CPU 모드 강제 실행 (OpenAI API)
./start_cpu.sh
# 또는
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml up -d

# 개별 서비스 재시작
docker restart youtube_agent_service      # RAG 에이전트 (포트: 8000)
docker restart youtube_data_processor     # 데이터 처리
docker restart youtube_data_collector     # 데이터 수집
docker restart youtube_admin_dashboard    # 관리 대시보드 (포트: 8090)
```

### 서비스 구성 (모드에 따라 다름)
- **postgres**: 메타데이터 저장 (채널, 콘텐츠, 작업 큐, 트랜스크립트)
- **redis**: 작업 큐, 캐시, 비용 승인 대기열
- **qdrant**: 벡터 데이터베이스 (포트: 6333)
- **whisper-server**: Whisper Large-v3 GPU 서버 (포트: 8082)
- **embedding-server**: BGE-M3 임베딩 서버 (포트: 8083, 1024차원)
- **stt-cost-api**: STT 비용 관리 API (포트: 8084)
- **monitoring-dashboard**: 시스템 모니터링 (포트: 8081)
- **data-collector**: YouTube 채널 수집
- **data-processor**: STT/벡터화 오케스트레이터
- **stt-worker-1~3**: STT 처리 워커 (GPU → OpenAI API 폴백)
- **vectorize-worker-1~3**: 벡터화 워커 (Summary + Chunks)
- **agent-service**: RAG 에이전트 API (포트: 8000) + Swagger UI
- **admin-dashboard**: 통합 관리 대시보드 (포트: 8090)
- **ui-service**: OpenWebUI 채팅 인터페이스 (포트: 3000)

## 📁 프로젝트 구조

```
youtube_agent/
├── src/youtube_agent/              # 핵심 라이브러리
│   ├── youtube_extractor.py        # YouTube 데이터 추출
│   └── stt_processor.py            # Whisper STT 처리
├── services/                       # 마이크로서비스들
│   ├── data-collector/             # 데이터 수집 서비스
│   ├── data-processor/             # STT+벡터화 서비스
│   ├── agent-service/              # RAG 에이전트 서비스
│   └── ui-service/                 # OpenWebUI 서비스
├── shared/                         # 공통 모듈
│   ├── models/database.py          # 데이터베이스 모델
│   └── utils/spotify_client.py     # Spotify 클라이언트 (비활성)
├── docker-compose.base.yml        # 기본 서비스 구성
├── docker-compose.gpu.yml         # GPU 모드 구성
├── docker-compose.cpu.yml         # CPU 모드 구성
├── requirements.txt               # Python 의존성
├── README.md                      # 프로젝트 개요
├── CLAUDE.md                      # 이 파일
└── docs/                          # 상세 문서
    ├── ARCHITECTURE.md            # 시스템 아키텍처
    ├── ROADMAP.md                 # 개발 로드맵
    ├── PROJECT_STATUS.md          # 프로젝트 상태
    └── TROUBLESHOOTING.md         # 문제 해결
```

## 🔧 핵심 구현 세부사항

### 1. STT 처리 개선사항
**파일**: `src/youtube_agent/stt_processor.py`

```python
# Whisper 할루시네이션 방지 설정
result = self.model.transcribe(
    audio_file,
    language='ko',
    beam_size=1,  # 할루시네이션 방지
    best_of=1,
    temperature=(0.0, 0.2, 0.4, 0.6, 0.8),  # 온도 폴백
    condition_on_previous_text=False,
    initial_prompt=None  # 텍스트 오염 방지를 위해 제거
)

# 반복 텍스트 제거 함수들
def _clean_repetitive_text(self, text: str) -> str
def _remove_repetitive_segments(self, segments: List[Dict]) -> List[Dict]
```

### 2. 문장 기반 청킹
**파일**: `services/data-processor/app.py`

```python
def _create_semantic_chunks(self, transcripts):
    # 문장 끝 감지: (.!? + 한국어 어미)
    # 1-3문장 또는 300-800자 단위로 청킹
    # 시간 정보 보존 (start_time, end_time)
```

### 3. YouTube 타임스탬프 링크
**파일**: `services/data-processor/app.py`

```python
def _create_timestamp_url(self, original_url, start_time_seconds):
    # https://youtube.com/watch?v=ABC123
    # → https://youtube.com/watch?v=ABC123&t=120s
    return f"{url_without_timestamp}{separator}t={timestamp_seconds}s"
```

### 4. RAG 에이전트 (LangGraph)
**파일**: `services/agent-service/rag_agent.py`

```python
# 검색 → 생성 → 개선 워크플로우
workflow = StateGraph(AgentState)
workflow.add_node("search", self._search_node)
workflow.add_node("generate", self._generate_node)
workflow.add_node("refine", self._refine_node)
```

### 5. OpenAI API 폴백 시스템
**파일**: `services/data-processor/stt_worker.py`

```python
# GPU 서버 우선 시도
def _try_whisper_server(self, audio_file: str) -> Optional[dict]:
    try:
        response = requests.post(
            f"{whisper_server_url}/transcribe",
            files=files,
            timeout=300
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.warning(f"Whisper 서버 실패: {e}")
        return None

# OpenAI API 폴백 (CPU 대신)
def _process_locally(self, audio_file: str, language: str = "ko") -> dict:
    """OpenAI Whisper API 처리 (GPU 서버 실패시 폴백)"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    with open(audio_file, "rb") as audio:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio,
            language=language,
            response_format="verbose_json"
        )
    return response
```

**품질 보장**:
- GPU 서버 (Whisper Large-v3) → OpenAI API (Whisper) 순서로 시도
- CPU 폴백 완전 제거로 품질 저하 방지
- 모든 STT 워커에 OPENAI_API_KEY 환경변수 추가

## 🔄 데이터 처리 워크플로우

### 1. 채널 추가
```python
# 새 채널 추가 (YouTube만)
channels = [
    "https://www.youtube.com/@syukaworld",
    "https://www.youtube.com/@unrealtech"
]
```

### 2. 처리 파이프라인
```
YouTube URL → 비디오 목록 수집 → 오디오 다운로드 →
Whisper STT → 반복 텍스트 제거 → 문장 기반 청킹 →
OpenAI 임베딩 → Qdrant 저장 → RAG 검색 가능
```

### 3. 작업 모니터링
```bash
# 처리 상태 확인
docker exec youtube_data_processor python -c "
from shared.models.database import ProcessingJob, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

jobs = db.query(ProcessingJob).filter(
    ProcessingJob.status == 'pending'
).all()

print(f'대기 중인 작업: {len(jobs)}개')
for job in jobs:
    print(f'- {job.job_type}: Job {job.id}')
"
```

## 🧪 테스트 및 사용법

### 관리 대시보드 사용
```bash
# 관리 대시보드 접속
http://localhost:8090

# 주요 기능:
# - 채널 관리 (추가/활성화/비활성화)
# - 콘텐츠 관리 (개별/일괄 제어, 정렬, 필터링)
# - 시스템 모니터링 (실시간 처리 현황)
# - API 테스트 (Swagger UI)
```

### RAG 에이전트 테스트
```bash
# OpenWebUI 접속
http://localhost:3000

# Swagger UI 접속
http://localhost:8000/docs

# 또는 직접 API 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "youtube-agent",
    "messages": [{"role": "user", "content": "슈카월드에서 코스피 얘기한 부분 알려줘"}]
  }'
```

### 검색 기능 테스트
```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "코스피 3395",
    "limit": 5
  }'
```

## 🚨 문제 해결

### 자주 발생하는 이슈들

1. **STT 품질 문제**
   - 해결: Whisper Large 모델 + 반복 텍스트 제거 로직 적용됨
   - 파일: `src/youtube_agent/stt_processor.py`

2. **벡터 검색 정확도**
   - 해결: 문장 기반 의미 청킹으로 개선됨
   - 파일: `services/data-processor/app.py:357-403`

3. **OpenWebUI 연결 문제**
   - 해결: `/v1/models` 엔드포인트 추가로 해결됨
   - 파일: `services/agent-service/app.py:157-173`

### 디버깅 명령어
```bash
# 서비스 로그 확인
docker-compose logs agent-service
docker-compose logs data-processor

# 데이터베이스 직접 접속
docker exec -it youtube_postgres psql -U youtube_user -d youtube_agent

# Qdrant 상태 확인
curl http://localhost:6333/collections/youtube_content
```

## 🔧 설정 파일들

### 환경변수 (.env)
```bash
OPENAI_API_KEY=your_key_here
SPOTIFY_CLIENT_ID=disabled
SPOTIFY_CLIENT_SECRET=disabled
DATABASE_URL=postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent
REDIS_URL=redis://redis:6379
QDRANT_URL=http://qdrant:6333
```

### 의존성 관리
```bash
# 메인 의존성
pip install -r requirements.txt

# 개발 의존성 추가 시
pip install new_package
pip freeze > requirements.txt
```

## 📊 현재 상태 및 다음 단계

### ✅ 완료된 기능
- [x] YouTube 콘텐츠 수집 파이프라인
- [x] Whisper Large-v3 모델 STT 처리 (GPU 서버)
- [x] OpenAI Whisper API 폴백 시스템 (비용 관리 포함)
- [x] 반복 텍스트 제거 및 할루시네이션 방지
- [x] 문장 기반 의미 청킹 (300-800자 단위)
- [x] YouTube 타임스탬프 링크 자동 생성
- [x] LangGraph 기반 RAG 에이전트
- [x] OpenWebUI 연동 (타임아웃 120초 설정)
- [x] 통합 관리 대시보드 (포트 8090)
- [x] Swagger UI API 문서화 (포트 8000/docs)
- [x] STT 비용 관리 시스템 (일일/월별 한도)
- [x] BGE-M3 임베딩 서버 (1024차원)
- [x] 다층 벡터 저장 (summaries + content)
- [x] 데이터 정제 시스템 (불필요한 텍스트 자동 제거)
- [x] RAG 점수 임계값 최적화 (0.55)
- [x] **콘텐츠 Soft Delete 시스템** (2025-09-23)
- [x] **Vector DB 실시간 동기화** (2025-09-23)
- [x] **콘텐츠 관리 UI - 개별/일괄 제어** (2025-09-23)
- [x] **콘텐츠 정렬 및 필터링 기능** (2025-09-23)
- [x] **Whisper GPU 메모리 관리 - 오디오 청킹** (2025-09-23)
- [x] **자동 데이터 품질 관리 시스템** (2025-09-23)
  - 데이터 정합성 자동 체크 및 수정
  - 멈춘 작업 자동 복구 (retry 메커니즘)
  - 고아 데이터 자동 정리
  - 시스템 모니터링 및 알림
  - 웹 대시보드 통합 (포트 8090)

### 🔄 현재 운영 상태
- **수집된 콘텐츠**: 2개 YouTube 채널, 105개 콘텐츠
- **처리 상태**:
  - STT 완료: 10개
  - 벡터화 완료: 44개
  - 대기 중: 51개
- **벡터 DB 상태**:
  - youtube_content: 7,448 포인트 (활발히 사용)
  - youtube_summaries: 10 포인트 (활발히 사용)
  - ~~youtube_paragraphs~~: 삭제됨 (레거시)
  - ~~youtube_full_texts~~: 삭제됨 (레거시)
- **서비스 상태**: 18개 컨테이너 모두 정상 작동 중
- **데이터 품질**: 중복 데이터 정리 완료, Soft Delete 시스템 적용

### 💡 향후 개선 방향 (단기)
- [ ] 모니터링 시스템 고도화 (Prometheus + Grafana)
- [ ] 오류 복구 메커니즘 강화
- [ ] 화자 분리 (Speaker Diarization)
- [ ] 하이브리드 검색 구현
- [ ] 검색 결과 re-ranking

## 📞 주요 API 엔드포인트

### RAG 에이전트 (포트 8000)
```
GET  /                           # 서비스 상태
GET  /health                     # 헬스체크
GET  /docs                       # Swagger UI 문서
GET  /v1/models                  # OpenAI 호환 모델 목록
POST /v1/chat/completions        # OpenAI 호환 채팅
POST /search                     # 콘텐츠 검색
POST /ask                        # 질문 답변 (LangGraph)
```

### 관리 대시보드 (포트 8090)
```
GET  /                           # 대시보드 메인
GET  /channels                   # 채널 관리
GET  /contents                   # 콘텐츠 관리 (NEW)
GET  /monitoring                 # 시스템 모니터링
GET  /api-docs                   # API 문서
POST /channels/{id}/toggle       # 채널 활성화 토글 (NEW)
POST /contents/{id}/toggle       # 콘텐츠 활성화 토글 (NEW)
POST /contents/bulk-toggle       # 콘텐츠 일괄 토글 (NEW)
```

### STT 비용 관리 (포트 8084)
```
GET  /                           # 비용 대시보드
GET  /api/cost-summary           # 비용 요약
GET  /api/pending-approvals      # 승인 대기 목록
POST /api/approve/{approval_id}  # 비용 승인
POST /api/reject/{approval_id}   # 비용 거부
```

### 모니터링 (포트 8081)
```
GET  /api/status                 # 처리 상태
GET  /api/queue                  # 작업 큐 현황
```

---
## 💡 개발 팁

### 코드 수정 시 주의사항
1. 항상 기존 코드 스타일을 따르기
2. 타입 힌트 사용 권장
3. 에러 처리 및 로깅 필수
4. 단위 테스트 작성 권장

### 디버깅
```bash
# 특정 서비스 디버그 모드
docker-compose run --rm data-processor python -m pdb app.py

# 컨테이너 내부 접속
docker exec -it youtube_data_processor /bin/bash
```

### 성능 프로파일링
```bash
# cProfile 사용
docker exec youtube_data_processor python -m cProfile -o profile.stats app.py

# 메모리 프로파일링
docker exec youtube_data_processor python -m memory_profiler app.py
```

## 🛠️ 서비스 운영 가이드

### 서비스 제어 명령
```bash
# 일시 정지/재개 (메모리 유지)
make pause     # CPU 사용만 중단
make unpause   # 일시 정지 해제

# 정지/시작 (컨테이너 유지)
make stop      # 프로세스 종료
make start     # 프로세스 시작

# 안전한 정지/시작 (데이터 무결성)
make safe-stop   # 처리 중인 작업 대기 후 정지
make safe-start  # stuck 작업 정리 후 시작

# 완전 종료/시작 (컨테이너 재생성)
make down      # 컨테이너 제거
make up        # 컨테이너 생성
```

### 데이터 무결성 관리
```bash
# 정합성 확인
make check-data      # PostgreSQL-Qdrant 일관성 체크
make check-data-fix  # 문제 자동 수정

# 데이터 초기화
make reset-soft      # 채널 유지, 콘텐츠만 삭제
make reset-hard      # 모든 데이터 삭제

# 작업 관리
make reset-stuck-jobs  # 멈춘 작업 재설정
make clean-orphans     # 고아 벡터 정리

# 데이터 품질 관리 서비스
./scripts/manage_quality_services.sh start       # 품질 서비스 시작
./scripts/manage_quality_services.sh stop        # 품질 서비스 중지
./scripts/manage_quality_services.sh status      # 서비스 상태 확인
./scripts/manage_quality_services.sh check       # 전체 품질 체크 (1회)
./scripts/manage_quality_services.sh dashboard   # 품질 대시보드 표시

# 개별 품질 체크
./scripts/manage_quality_services.sh integrity   # 정합성 체크만 실행
./scripts/manage_quality_services.sh recovery    # 작업 복구만 실행
./scripts/manage_quality_services.sh alerts      # 알림 체크만 실행
```

## 🧪 테스트 전략

### 테스트 명령어
```bash
# 단위/통합 테스트
make test-unit           # 단위 테스트 실행
make test-integration    # 통합 테스트 실행
make test-coverage       # 커버리지 측정

# E2E 테스트
make test-pipeline       # 파이프라인 전체 테스트
make test-gpu-servers    # GPU 서버 동작 테스트
./test/e2e/test_new_channel.sh    # 채널 추가 E2E
./test/e2e/test_recovery.sh       # 복구 테스트
./test/e2e/test_gpu_fallback.sh   # GPU 폴백 테스트

# 배포 전 체크
make pre-deploy-check    # 배포 전 전체 검증
make test-security       # 보안 취약점 스캔
```

### 테스트 파일 구조
```
test/
├── e2e/                          # End-to-End 테스트
│   ├── test_new_channel.sh      # 채널 추가 및 처리
│   ├── test_recovery.sh         # 서비스 중단 복구
│   └── test_gpu_fallback.sh     # GPU→API 폴백
├── test_embeddings_benchmark.py  # 임베딩 성능 테스트
└── test_production_fixes.py      # 프로덕션 버그 수정 테스트
```

### 테스트 커버리지 목표
- 단위 테스트: 80% 이상
- 통합 테스트: 70% 이상
- E2E 테스트: 주요 시나리오 100%
- 성능 기준:
  - STT 처리: 실시간 대비 0.5x 이하
  - 검색 응답: 500ms 이내
  - RAG 응답: 3초 이내

## 🧪 테스트 전략 (New)

### 테스트 명령어
```bash
# 환경 검증
./detect_environment.sh

# GPU 서버 테스트 (GPU 모드)
docker exec youtube_whisper_server python -c "import torch; print(torch.cuda.is_available())"

# STT 처리 테스트
curl -X POST http://localhost:8082/transcribe \
  -F "audio=@test_audio.mp3" \
  -F "language=ko"

# RAG 검색 테스트
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "테스트 쿼리", "limit": 5}'

# 코스트 검증 (CPU/OpenAI API 모드)
curl http://localhost:8084/api/cost-summary
```

### 통합 테스트
```bash
# E2E 파이프라인 테스트
docker exec youtube_admin_dashboard python -m pytest tests/test_pipeline.py

# 성능 벤치마크
docker exec youtube_agent_service python tests/benchmark_rag.py
```

## 🔧 서비스 운영 가이드 (New)

### 모드 전환
```bash
# GPU → CPU 전환
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans
./start_cpu.sh

# CPU → GPU 전환
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans
./start_gpu.sh

# 이전 구성 정리
./cleanup_old_containers.sh
```

### 데이터 무결성 관리
```bash
# 정합성 확인
docker exec youtube_data_processor python scripts/check_data_integrity.py

# 데이터 초기화 (주의: 데이터 손실)
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "TRUNCATE TABLE processing_jobs CASCADE;"

# 작업 큐 클리어
docker exec youtube_redis redis-cli FLUSHDB
```

### 문제 해결
```bash
# 고아 컨테이너 정리
./cleanup_old_containers.sh

# 네트워크 문제 해결
./fix_network.sh

# .env 파일 검증
source .env && echo "API Key: ${OPENAI_API_KEY:0:10}..."

# 서비스 로그 확인
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml logs -f [service]
```

### 콘텐츠 관리 시스템 (NEW)
**파일**: `services/agent-service/app.py`, `services/admin-dashboard/templates/contents.html`

```python
# Soft Delete 구현
class Content(Base):
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime)

# Vector DB 동기화
if not content.is_active:
    qdrant_client.delete(
        collection_name=collection,
        points_selector={"filter": {"must": [{"key": "content_id", "match": {"value": content_id}}]}}
    )
```

---
**마지막 업데이트**: 2025-09-23
**최근 주요 개선사항**:
- **GPU/CPU 모드 분리**: 인프라별 docker-compose 파일 분리 (base/gpu/cpu)
- **자동 환경 감지**: detect_environment.sh로 GPU 유무 자동 판별
- **통합 실행 스크립트**: start.sh, start_gpu.sh, start_cpu.sh 제공
- **네트워크 문제 해결**: fix_network.sh 스크립트 추가
- **.env 파일 개선**: 인라인 주석 제거, source 방식 로드
- **OpenAI 전용 모드**: FORCE_OPENAI_API 환경변수로 강제 API 사용
- **임베딩 래퍼**: embedding_server_wrapper.py로 OpenAI/BGE-M3 선택
- **비용 관리 강화**: STT API 사용 시 자동 비용 제한 및 승인
- **문서 업데이트**: README.md, ARCHITECTURE.md, TROUBLESHOOTING.md 최신화
- **컨테이너 정리**: cleanup_old_containers.sh 스크립트 추가
- to memorize
- to memorize and update docs
- to memorize