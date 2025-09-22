# 빠른 시작 가이드 🚀

5분 안에 YouTube Content Agent를 시작하는 가이드입니다.

## 📋 전제 조건

- Docker & Docker Compose 설치
- OpenAI API Key
- 16GB+ RAM

## 🎯 3단계 빠른 설치

### 1️⃣ 프로젝트 복제 및 설정

```bash
# 프로젝트 복제
git clone https://github.com/your-org/youtube_agent.git
cd youtube_agent

# 환경 설정
cp .env.example .env

# .env 파일에서 OpenAI API Key 설정
# OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

### 2️⃣ 서비스 시작

```bash
# Makefile 사용 (권장)
make quickstart

# 또는 Docker Compose 직접 사용
docker-compose up -d
```

### 3️⃣ 서비스 접속

모든 서비스가 시작되면 다음 URL에 접속하세요:

| 서비스 | URL | 설명 |
|--------|-----|------|
| 🎯 **관리 대시보드** | http://localhost:8090 | 통합 관리 인터페이스 |
| 💬 채팅 UI | http://localhost:3000 | 질의응답 인터페이스 |
| 📚 API 문서 | http://localhost:8000/docs | Swagger UI |
| 🗄️ Qdrant | http://localhost:6333/dashboard | 벡터 DB 관리 |

## 🎬 첫 YouTube 채널 추가하기

### 방법 1: 관리 대시보드 사용 (가장 쉬움) ✨

1. **관리 대시보드 접속**: http://localhost:8090/channels
2. **채널 추가**:
   - "새 채널 추가" 버튼 클릭
   - 채널 정보 입력:
     - 채널명: `슈카월드`
     - URL: `https://www.youtube.com/@syukaworld`
   - "추가" 버튼 클릭

3. **처리 상태 확인**:
   - 대시보드 메인: http://localhost:8090
   - 처리 현황 모니터링: http://localhost:8090/monitoring

### 방법 2: API 사용

```bash
curl -X POST "http://localhost:8000/api/channels" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "슈카월드",
    "url": "https://www.youtube.com/@syukaworld",
    "platform": "youtube",
    "language": "ko"
  }'
```

## 💬 첫 질문하기

### OpenWebUI 사용

1. **채팅 UI 접속**: http://localhost:3000
2. **계정 생성** (첫 방문 시)
3. **질문 예시**:
   - "슈카월드에서 최근 경제 전망은?"
   - "코스피 3395에 대해 뭐라고 했나요?"

### API 사용

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "youtube-agent",
    "messages": [
      {"role": "user", "content": "슈카월드 최신 영상 요약해줘"}
    ]
  }'
```

## 📊 시스템 상태 확인

### 관리 대시보드에서 확인
- **메인 대시보드**: http://localhost:8090
  - 총 채널 수
  - 총 콘텐츠 수
  - 처리율
  - 시스템 상태

### 명령줄로 확인

```bash
# 서비스 상태
make ps

# 실시간 로그
make logs

# 통계 조회
curl http://localhost:8000/stats | jq
```

## 🔍 API 테스트

### Swagger UI 사용
1. http://localhost:8000/docs 접속
2. 원하는 엔드포인트 선택
3. "Try it out" → 파라미터 입력 → "Execute"

### 관리 대시보드 API 테스트
1. http://localhost:8090/api-docs 접속
2. 내장된 테스트 도구 사용

## ⚡ 유용한 명령어

```bash
# 서비스 관리
make up          # 서비스 시작
make down        # 서비스 중지
make restart     # 서비스 재시작
make logs        # 로그 확인

# 데이터베이스
make db-shell    # PostgreSQL 접속
make db-backup   # 백업 생성

# 테스트
make test-health # 헬스체크
make test-search # 검색 테스트
make test-chat   # 채팅 테스트
```

## 🎓 다음 단계

1. **더 많은 채널 추가**: 관리 대시보드에서 YouTube 채널 추가
2. **처리 모니터링**: 콘텐츠 수집 및 처리 상태 확인
3. **API 활용**: Swagger UI로 다양한 API 테스트
4. **커스터마이징**: 프롬프트 및 설정 조정

## ❓ 문제 해결

### Docker 서비스가 시작되지 않을 때
```bash
# Docker 상태 확인
docker info

# 포트 충돌 확인
sudo lsof -i :8000 :3000 :8090

# 전체 재시작
make clean
make build
make up
```

### OpenAI API 키 오류
```bash
# .env 파일 확인
cat .env | grep OPENAI_API_KEY

# 환경 변수 재설정 후 재시작
make restart
```

### 메모리 부족
```bash
# Docker 리소스 정리
docker system prune -a

# 컨테이너별 메모리 사용량 확인
docker stats
```

## 🎉 축하합니다!

YouTube Content Agent가 실행 중입니다. 이제 YouTube 콘텐츠를 AI로 분석하고 질문에 답변받을 수 있습니다!

### 핵심 기능 요약:
- ✅ **관리 대시보드**: 웹 UI로 편리한 채널 관리
- ✅ **Swagger UI**: API 문서 및 테스트
- ✅ **채팅 인터페이스**: 자연스러운 대화형 질의응답
- ✅ **실시간 모니터링**: 처리 상태 실시간 확인

---

도움이 필요하신가요?
- 📖 [전체 문서](INDEX.md)
- 🏗️ [아키텍처 설명](ARCHITECTURE.md)
- 📚 [API 문서](API.md)
- 🎓 [튜토리얼](TUTORIAL.md)