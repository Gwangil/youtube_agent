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
- **이전**: `improved_stt_worker_with_cost.py` → 백업으로 이동

### 벡터화 처리
- **현재**: `services/data-processor/vectorize_worker.py`
- **이전**: `improved_vectorize_worker.py` → 백업으로 이동

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
3. **벡터화**: 텍스트 → vectorize_worker → Qdrant
4. **검색**: 질의 → agent-service → RAG 응답

## 포트 매핑

- 8000: RAG Agent API
- 8090: Admin Dashboard
- 6333: Qdrant Vector DB
- 5432: PostgreSQL
- 6379: Redis
- 3000: OpenWebUI (UI Service)

---
**업데이트**: 2025-09-22