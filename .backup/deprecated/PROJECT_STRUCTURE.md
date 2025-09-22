# 프로젝트 구조 및 파일 관리

## 현재 활성 구조

```
youtube_agent/
├── src/youtube_agent/               # 핵심 라이브러리
│   ├── youtube_extractor.py         # YouTube 데이터 추출
│   └── stt_processor.py             # Whisper STT 처리
│
├── services/                         # 마이크로서비스
│   ├── data-collector/              # 데이터 수집 서비스
│   │   └── app.py
│   ├── data-processor/              # STT+벡터화 서비스
│   │   ├── app.py                  # 메인 처리 앱
│   │   ├── stt_worker.py            # STT 워커 (GPU/API 폴백)
│   │   ├── vectorize_worker.py     # 통합 벡터화 워커 (Summary+Chunks)
│   │   ├── stt_cost_manager.py     # 비용 관리
│   │   └── whisper_server.py       # Whisper 서버
│   ├── agent-service/               # RAG 에이전트 서비스
│   │   ├── app.py
│   │   └── rag_agent.py
│   └── admin-dashboard/             # 관리 대시보드
│       └── app.py
│
├── shared/                          # 공통 모듈
│   ├── models/
│   │   └── database.py              # DB 모델 정의
│   └── utils/
│       └── redis_client.py          # Redis 유틸
│
├── backup/                          # 백업 및 이전 버전
│   ├── docker/                      # Docker 설정 백업
│   ├── scripts/                     # 스크립트 백업
│   └── services/                    # 서비스 코드 백업
│
├── docker-compose.yml               # 메인 Docker 설정
├── requirements.txt                 # Python 의존성
├── CLAUDE.md                        # AI 개발 가이드
├── BACKUP_FILES.md                  # 백업 파일 목록
└── PROJECT_STRUCTURE.md            # 이 파일
```

## 주요 파일 매핑

### STT 처리
- **현재**: `services/data-processor/stt_worker.py`
  - GPU 서버 (Whisper Large-v3) 우선 사용
  - OpenAI API 폴백 (비용 관리 포함)
  - CPU 폴백 완전 제거

### 벡터화 처리
- **현재**: `services/data-processor/vectorize_worker.py`
  - Summary 생성 기능 통합 (OpenAI API)
  - 의미 기반 청킹 (300-800자)
  - YouTube 타임스탬프 URL 생성
  - BGE-M3 임베딩 서버 사용 (1024차원)

### Docker 설정
- **현재**: `docker-compose.yml`
- **백업**: `backup/docker/docker-compose.optimized.yml`

## 서비스 실행 명령

```bash
# 전체 서비스 시작
docker-compose up -d

# 개별 워커 재시작
docker restart youtube_stt_worker_1
docker restart youtube_stt_worker_2
docker restart youtube_vectorize_worker_1

# 로그 확인
docker-compose logs -f stt-worker-1
docker-compose logs -f vectorize-worker-1
```

## 환경 변수

필수 환경 변수 (`.env` 파일):
```bash
OPENAI_API_KEY=your_key_here
DATABASE_URL=postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent
REDIS_URL=redis://redis:6379
QDRANT_URL=http://qdrant:6333
WHISPER_SERVER_URL=http://whisper-server:8080
```

## 데이터 플로우

1. **수집**: YouTube URL → data-collector → PostgreSQL
2. **STT**: 오디오 파일 → stt_worker → 텍스트 + 타임스탬프
   - Whisper GPU 서버 (8082) → OpenAI API 폴백
   - 비용 관리 API (8084)로 승인 처리
3. **벡터화**: 텍스트 → vectorize_worker → Qdrant
   - Summary 생성: OpenAI GPT-4o-mini
   - 임베딩: BGE-M3 서버 (8083)
   - 저장: youtube_summaries + youtube_content
4. **검색**: 질의 → agent-service → RAG 응답
   - LangGraph 워크플로우
   - 점수 임계값: 0.55

## 포트 매핑

- 3000: OpenWebUI (채팅 인터페이스)
- 5432: PostgreSQL
- 6333: Qdrant Vector DB
- 6379: Redis
- 8000: RAG Agent API + Swagger UI
- 8081: Monitoring Dashboard
- 8082: Whisper Server (GPU)
- 8083: Embedding Server (BGE-M3)
- 8084: STT Cost Management API
- 8090: Admin Dashboard

## 현재 시스템 상태

### 데이터 현황
- **PostgreSQL**: 36,208개 트랜스크립트
- **Qdrant 컬렉션**:
  - youtube_content: 7,448 포인트 (활발히 사용)
  - youtube_summaries: 10 포인트 (활발히 사용)
  - youtube_paragraphs: 5,729 포인트 (레거시)
  - youtube_full_texts: 10 포인트 (레거시)

### 데이터 품질
- ✅ 모든 "한국어 팟캐스트" 오염 텍스트 제거 완료
- ✅ Whisper initial_prompt 제거로 향후 오염 방지

---
**업데이트**: 2025-09-22