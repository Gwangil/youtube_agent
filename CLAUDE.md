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

### 실행 중인 서비스들
```bash
# 전체 서비스 시작
docker-compose up -d

# 개별 서비스 재시작
docker restart youtube_agent_service      # RAG 에이전트 (포트: 8000)
docker restart youtube_data_processor     # 데이터 처리
docker restart youtube_data_collector     # 데이터 수집
docker restart youtube_admin_dashboard    # 관리 대시보드 (포트: 8090)
```

### 서비스별 역할 (18개 컨테이너)
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
├── docker-compose.yml             # 서비스 orchestration
├── requirements.txt               # Python 의존성
└── CLAUDE.md                      # 이 파일
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

### 관리 대시보드 사용 🆕
```bash
# 관리 대시보드 접속
http://localhost:8090

# 주요 기능:
# - 채널 관리 (추가/수정/삭제)
# - 시스템 모니터링
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

### 🔄 현재 운영 상태
- **수집된 콘텐츠**: 10개 YouTube 채널, 36,208개 트랜스크립트
- **벡터 DB 상태**:
  - youtube_content: 7,448 포인트 (활발히 사용)
  - youtube_summaries: 10 포인트 (활발히 사용)
  - youtube_paragraphs: 5,729 포인트 (레거시, 미사용)
  - youtube_full_texts: 10 포인트 (레거시, 미사용)
- **서비스 상태**: 18개 컨테이너 모두 정상 작동 중
- **데이터 품질**: 모든 "한국어 팟캐스트" 관련 오염 텍스트 제거 완료

### 💡 향후 개선 방향
- [ ] 레거시 컬렉션 정리 (paragraphs, full_texts)
- [ ] 주제 기반 클러스터링 알고리즘
- [ ] 다국어 지원 확장 (현재 한국어 특화)
- [ ] 실시간 콘텐츠 모니터링 및 자동 업데이트
- [ ] 멀티모달 분석 (비디오 썸네일, 자막)
- [ ] 더 큰 컨텍스트 윈도우 지원 (현재 800자)

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
GET  /stats                      # 시스템 통계
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

---
**마지막 업데이트**: 2025-09-22
**최근 주요 개선사항**:
- OpenWebUI 타임아웃 120초로 증가 (LLM 응답 시간 고려)
- RAG 점수 임계값 0.8→0.55 하향 (더 많은 관련 콘텐츠 포함)
- 모든 데이터에서 "한국어 팟캐스트" 오염 텍스트 제거 완료
- vectorize_worker.py에 Summary 생성 기능 통합
- enhanced_vectorizer.py 기능을 vectorize_worker.py로 통합
- docker-compose.yml 볼륨 매핑 수정 (stt-cost-api)
- STT 비용 관리자 import 오류 수정 (List, HTMLResponse)
- 4개 Qdrant 컬렉션 전체 데이터 정제 완료
- to memorize
- to memorize