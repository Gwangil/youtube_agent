# YouTube Content Agent 튜토리얼

이 튜토리얼에서는 YouTube Content Agent를 처음부터 설정하고 사용하는 방법을 단계별로 안내합니다.

## 학습 목표

이 튜토리얼을 완료하면 다음을 할 수 있게 됩니다:
- YouTube 채널 콘텐츠 수집 및 처리
- RAG 기반 질의응답 시스템 사용
- OpenWebUI를 통한 대화형 인터페이스 활용
- API를 통한 프로그래밍 방식 접근

## 사전 준비

- Docker와 Docker Compose 설치 완료
- OpenAI API Key 준비
- 기본적인 터미널/명령줄 사용 지식

## 1단계: 프로젝트 설정

### 1.1 프로젝트 다운로드

```bash
# 프로젝트 클론
git clone https://github.com/your-org/youtube_agent.git
cd youtube_agent

# 디렉토리 구조 확인
ls -la
```

### 1.2 환경 변수 설정

```bash
# 환경 파일 생성
cp .env.example .env

# 편집기로 .env 파일 열기
nano .env
```

최소한 다음 값을 설정하세요:
```env
OPENAI_API_KEY=sk-proj-여러분의_API_키
```

### 1.3 서비스 시작

```bash
# Docker 이미지 빌드
docker-compose build

# 서비스 시작
docker-compose up -d

# 시작 상태 확인 (모두 Up 상태여야 함)
docker-compose ps
```

## 2단계: 첫 번째 YouTube 채널 추가

### 2.1 채널 URL 준비

분석하고 싶은 YouTube 채널을 선택합니다. 예시:
- 슈카월드: `https://www.youtube.com/@syukaworld`
- 삼프로TV: `https://www.youtube.com/@3protv`

### 2.2 채널 추가

`services/data-collector/app.py` 파일을 열고 채널을 추가합니다:

```python
channels = [
    "https://www.youtube.com/@syukaworld",
    "https://www.youtube.com/@3protv",  # 새로 추가
]
```

### 2.3 데이터 수집 시작

```bash
# data-collector 서비스 재시작
docker-compose restart data-collector

# 로그 확인
docker-compose logs -f data-collector
```

다음과 같은 로그가 보이면 정상입니다:
```
[INFO] Starting collection for channel: 슈카월드
[INFO] Found 234 videos
[INFO] Creating processing jobs...
```

## 3단계: 콘텐츠 처리 모니터링

### 3.1 처리 상태 확인

```bash
# 처리 중인 작업 확인
docker exec youtube_data_processor python -c "
from shared.models.database import ProcessingJob, get_database_url
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

stats = db.query(
    ProcessingJob.status,
    func.count(ProcessingJob.id)
).group_by(ProcessingJob.status).all()

for status, count in stats:
    print(f'{status}: {count}개')
"
```

### 3.2 처리 로그 모니터링

```bash
# STT 처리 로그 확인
docker-compose logs -f data-processor | grep STT

# 벡터화 로그 확인
docker-compose logs -f data-processor | grep Vector
```

## 4단계: OpenWebUI로 대화하기

### 4.1 OpenWebUI 접속

1. 브라우저에서 http://localhost:3000 접속
2. 첫 방문시 계정 생성
   - 이메일: admin@example.com
   - 비밀번호: 안전한 비밀번호 설정

### 4.2 모델 선택

1. 좌측 상단 모델 선택 드롭다운 클릭
2. "youtube-agent" 모델 선택

### 4.3 첫 대화 시작

질문 예시:
```
슈카월드에서 최근 경제 전망에 대해 어떻게 얘기했나요?
```

응답에는 다음이 포함됩니다:
- 요약된 답변
- YouTube 타임스탬프 링크
- 관련 콘텐츠 참조

## 5단계: API 사용하기

### 5.1 API 문서 확인

브라우저에서 http://localhost:8000/docs 접속하여 대화형 API 문서를 확인합니다.

### 5.2 검색 API 테스트

```bash
# 콘텐츠 검색
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "비트코인",
    "limit": 3
  }' | jq
```

### 5.3 채팅 API 테스트

```bash
# 질의응답
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "youtube-agent",
    "messages": [
      {"role": "user", "content": "최근 주식 시장 전망은?"}
    ]
  }' | jq
```

## 6단계: Python으로 통합하기

### 6.1 Python 클라이언트 작성

`client_example.py` 파일 생성:

```python
import requests
import json

class YouTubeAgentClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def search(self, query, limit=5):
        """콘텐츠 검색"""
        response = requests.post(
            f"{self.base_url}/search",
            json={"query": query, "limit": limit}
        )
        return response.json()

    def chat(self, message):
        """대화형 질의응답"""
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": "youtube-agent",
                "messages": [{"role": "user", "content": message}]
            }
        )
        return response.json()

    def get_stats(self):
        """시스템 통계"""
        response = requests.get(f"{self.base_url}/stats")
        return response.json()

# 사용 예시
if __name__ == "__main__":
    client = YouTubeAgentClient()

    # 통계 확인
    stats = client.get_stats()
    print(f"총 콘텐츠: {stats['total_contents']}개")

    # 검색
    results = client.search("경제 전망")
    for result in results['results']:
        print(f"- {result['title']} ({result['channel']})")
        print(f"  링크: {result['timestamp_url']}")

    # 대화
    response = client.chat("최근 핫한 주제가 뭐야?")
    print(f"\n답변: {response['choices'][0]['message']['content']}")
```

### 6.2 실행

```bash
python client_example.py
```

## 7단계: 고급 기능 활용

### 7.1 특정 채널 필터링

```python
# 특정 채널만 검색
results = client.search(
    query="비트코인",
    channel_filter=["슈카월드"],
    limit=5
)
```

### 7.2 날짜 범위 지정

```python
# 최근 일주일 콘텐츠만 검색
from datetime import datetime, timedelta

date_from = (datetime.now() - timedelta(days=7)).isoformat()
date_to = datetime.now().isoformat()

results = client.search(
    query="경제",
    date_from=date_from,
    date_to=date_to
)
```

### 7.3 스트리밍 응답

```python
import requests

def stream_chat(message):
    response = requests.post(
        "http://localhost:8000/v1/chat/completions",
        json={
            "model": "youtube-agent",
            "messages": [{"role": "user", "content": message}],
            "stream": True
        },
        stream=True
    )

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]
                if data != '[DONE]':
                    chunk = json.loads(data)
                    content = chunk['choices'][0]['delta'].get('content', '')
                    print(content, end='', flush=True)

# 사용
stream_chat("슈카월드의 투자 철학을 설명해줘")
```

## 8단계: 문제 해결

### 8.1 서비스가 시작되지 않을 때

```bash
# 상세 로그 확인
docker-compose logs [서비스명]

# 전체 재시작
docker-compose down
docker-compose up -d
```

### 8.2 처리가 멈췄을 때

```bash
# 처리 워커 재시작
docker-compose restart data-processor

# 실패한 작업 재시도
docker exec youtube_data_processor python -c "
from shared.models.database import ProcessingJob, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

failed_jobs = db.query(ProcessingJob).filter_by(status='failed').all()
for job in failed_jobs:
    job.status = 'pending'
    job.error_message = None

db.commit()
print(f'{len(failed_jobs)}개 작업 재시도 설정')
"
```

### 8.3 메모리 부족

```bash
# 컨테이너 메모리 사용량 확인
docker stats

# 불필요한 데이터 정리
docker system prune -a
```

## 9단계: 프로덕션 배포 준비

### 9.1 환경 변수 보안

```bash
# .env 파일을 안전한 곳에 백업
cp .env .env.backup

# 프로덕션용 환경 변수 설정
LOG_LEVEL=WARNING
DEBUG=false
```

### 9.2 백업 설정

```bash
# 데이터베이스 백업
make db-backup

# 정기 백업 크론탭 설정
crontab -e
# 추가: 0 2 * * * cd /path/to/youtube_agent && make db-backup
```

### 9.3 모니터링 설정

```bash
# 헬스체크 스크립트 작성
cat > health_check.sh << 'EOF'
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ $response != "200" ]; then
    echo "Service unhealthy!"
    # 알림 전송 로직
fi
EOF

chmod +x health_check.sh
```

## 10단계: 다음 단계

축하합니다! 기본적인 YouTube Content Agent 사용법을 모두 익히셨습니다.

### 추천 학습 경로

1. **고급 설정**: [OPERATIONS.md](.old/OPERATIONS.md) - 프로덕션 운영 가이드
2. **아키텍처 이해**: [ARCHITECTURE.md](ARCHITECTURE.md) - 시스템 구조 심화
3. **API 마스터**: [API.md](API.md) - 모든 API 엔드포인트 활용
4. **성능 최적화**: [PERFORMANCE.md](PERFORMANCE.md) - 성능 튜닝

### 커뮤니티

- GitHub Issues에서 질문하기
- Pull Request로 기여하기
- 사용 사례 공유하기

## 요약

이 튜토리얼에서 배운 내용:
- ✅ YouTube Content Agent 설치 및 설정
- ✅ YouTube 채널 추가 및 콘텐츠 수집
- ✅ OpenWebUI를 통한 대화형 인터페이스 사용
- ✅ API를 통한 프로그래밍 방식 접근
- ✅ Python 클라이언트 작성
- ✅ 문제 해결 방법

이제 YouTube 콘텐츠를 AI로 분석하고 활용할 준비가 되었습니다!