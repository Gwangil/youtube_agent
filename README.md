# YouTube Content Agent - 마이크로서비스 아키텍처

YouTube 채널에서 콘텐츠를 수집하고, RAG 기반 AI 에이전트로 질의응답 서비스를 제공하는 통합 플랫폼입니다.

## 🏗️ 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Collector │    │  Data Processor │    │  Agent Service  │
│                 │    │                 │    │                 │
│ • YouTube       │    │ • Transcript    │    │ • LangGraph     │
│ • Scheduling    │    │ • STT (Whisper) │    │ • RAG           │
│                 │    │ • Vectorization │    │ • FastAPI       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   PostgreSQL    │    │     Qdrant      │    │   OpenWebUI     │
    │                 │    │                 │    │                 │
    │ • Metadata      │    │ • Vector Store  │    │ • Chat UI       │
    │ • Jobs Queue    │    │ • Similarity    │    │ • Model Mgmt    │
    │ • Channels      │    │ • Search        │    │ • History       │
    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 복제
git clone <repository-url>
cd podcast_agent

# 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 설정
```

### 2. 서비스 시작

```bash
# 모든 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f data-collector
```

### 3. 서비스 확인

- **OpenWebUI**: http://localhost:3000
- **Agent API**: http://localhost:8000
- **Qdrant Dashboard**: http://localhost:6333/dashboard
- **PostgreSQL**: localhost:5432

## 📋 서비스 구성

### 🔄 Data Collector
- **기능**: YouTube 채널 및 Spotify 팟캐스트 데이터 수집
- **스케줄**: 매일 06:00, 매 4시간마다 증분 수집
- **지원 플랫폼**: YouTube, Spotify

### ⚙️ Data Processor
- **기능**: 자막 추출, STT 처리, 텍스트 벡터화
- **처리 순서**: 자막 추출 → STT (자막 없는 경우) → 벡터화
- **모델**: Whisper (STT), OpenAI Embeddings

### 🤖 Agent Service
- **기능**: LangGraph 기반 RAG 에이전트
- **API**: OpenAI 호환 인터페이스
- **검색**: 벡터 유사도 기반 콘텐츠 검색

### 🎨 UI Service
- **기능**: OpenWebUI 기반 채팅 인터페이스
- **연결**: Agent Service와 자동 연결
- **사용자**: 웹 브라우저에서 직접 질의응답

## 🛠️ 사용법

### 채널 등록

```bash
# 데이터베이스에 직접 삽입하거나 API 사용
docker-compose exec postgres psql -U podcast_user -d podcast_agent -c "
INSERT INTO channels (name, url, platform, category, description, language)
VALUES ('슈카월드', 'https://open.spotify.com/show/3iDP6OXw1CaSnjNEsN9k4v', 'spotify', 'talk', '유재석의 팟캐스트', 'ko');
"
```

### API 사용 예제

```bash
# 콘텐츠 검색
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "인공지능", "platform": "youtube", "limit": 5}'

# 질문하기
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "슈카월드에서 나온 재미있는 이야기가 있나요?"}'

# 통계 조회
curl "http://localhost:8000/stats"
```

### OpenWebUI 사용

1. http://localhost:3000 접속
2. 계정 생성 (첫 방문 시)
3. 모델 선택: `podcast-rag-agent`
4. 채팅으로 팟캐스트 콘텐츠에 대해 질문

## 🔧 개발 및 커스터마이징

### 새로운 플랫폼 추가

1. `shared/utils/`에 새 클라이언트 추가
2. `services/data-collector/app.py`에 수집 로직 추가
3. 데이터베이스 스키마 업데이트 (필요시)

### RAG 에이전트 커스터마이징

```python
# services/agent-service/rag_agent.py 수정
class PodcastRAGAgent:
    def _build_graph(self):
        # 새로운 노드 추가
        workflow.add_node("custom_node", self._custom_node)
        # ...
```

### 프롬프트 커스터마이징

`services/agent-service/rag_agent.py`의 `_generate_node` 메서드에서 프롬프트 템플릿 수정

## 📊 모니터링

### 서비스 상태 확인

```bash
# 모든 서비스 상태
docker-compose ps

# 리소스 사용량
docker stats

# 특정 서비스 재시작
docker-compose restart data-processor
```

### 로그 분석

```bash
# 실시간 로그
docker-compose logs -f --tail=100

# 에러 로그만
docker-compose logs | grep ERROR

# 특정 시간대 로그
docker-compose logs --since="2024-01-01T09:00:00"
```

## 🔧 문제 해결

### 일반적인 문제

1. **OpenAI API 키 오류**
   ```bash
   # .env 파일 확인
   cat .env | grep OPENAI_API_KEY
   ```

2. **Spotify 연결 오류**
   ```bash
   # Spotify 자격 증명 확인
   docker-compose logs data-collector | grep -i spotify
   ```

3. **벡터 데이터베이스 연결 오류**
   ```bash
   # Qdrant 상태 확인
   curl http://localhost:6333/health
   ```

### 데이터 초기화

```bash
# 모든 데이터 삭제 (주의!)
docker-compose down -v
docker-compose up -d
```

## 📈 성능 최적화

### 대용량 처리

- **배치 크기 조정**: `services/data-processor/app.py`에서 배치 크기 수정
- **병렬 처리**: 워커 프로세스 수 증가
- **캐싱**: Redis 활용한 결과 캐싱

### 비용 최적화

- **Whisper 로컬 실행**: GPU 사용하여 STT 비용 절약
- **임베딩 모델 변경**: 더 저렴한 모델로 변경 가능
- **스케줄 조정**: 수집 빈도 조정

## 🤝 기여

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 라이선스

MIT License

## 🙋‍♂️ 지원

이슈가 있으시면 GitHub Issues를 통해 문의해주세요.