# API 문서

YouTube Content Agent의 RESTful API 문서입니다.

## 기본 정보

- **Base URL**: `http://localhost:8000`
- **Swagger UI**: `http://localhost:8000/docs` (대화형 API 테스트)
- **ReDoc**: `http://localhost:8000/redoc` (API 참조 문서)
- **관리 대시보드**: `http://localhost:8090` (웹 UI 관리 도구)
- **인증**: API Key (선택사항)
- **응답 형식**: JSON
- **문자 인코딩**: UTF-8

## API 엔드포인트

### 1. 서비스 상태

#### 헬스체크
```http
GET /health
```

**응답 예시:**
```json
{
  "status": "healthy",
  "timestamp": "2025-09-18T10:30:00Z",
  "services": {
    "database": "connected",
    "qdrant": "connected",
    "redis": "connected"
  }
}
```

#### 서비스 통계
```http
GET /stats
```

**응답 예시:**
```json
{
  "total_channels": 5,
  "total_contents": 1234,
  "total_chunks": 45678,
  "processed_today": 23,
  "pending_jobs": 12,
  "storage_used_gb": 15.4
}
```

### 2. 콘텐츠 검색

#### 벡터 검색
```http
POST /search
```

**요청 본문:**
```json
{
  "query": "코스피 3395 전망",
  "limit": 10,
  "threshold": 0.7,
  "channel_filter": ["슈카월드"],
  "date_from": "2025-01-01",
  "date_to": "2025-09-18"
}
```

**응답 예시:**
```json
{
  "results": [
    {
      "content_id": "abc123",
      "title": "코스피 3395 돌파 가능할까?",
      "channel": "슈카월드",
      "text": "오늘 코스피가 3395를 돌파했는데...",
      "similarity": 0.89,
      "timestamp_url": "https://youtube.com/watch?v=ABC123&t=120s",
      "published_at": "2025-09-15T09:00:00Z"
    }
  ],
  "total": 5,
  "query_time_ms": 234
}
```

### 3. 채팅 완성 (OpenAI 호환)

#### 채팅 생성
```http
POST /v1/chat/completions
```

**요청 본문:**
```json
{
  "model": "youtube-agent",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "슈카월드에서 최근 경제 전망은 어떻게 얘기했나요?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**응답 예시:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1695365700,
  "model": "youtube-agent",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "슈카월드의 최근 방송에 따르면...\n\n[출처: https://youtube.com/watch?v=ABC123&t=240s]"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 200,
    "total_tokens": 250
  }
}
```

#### 스트리밍 채팅
```http
POST /v1/chat/completions
```

**요청 본문:**
```json
{
  "model": "youtube-agent",
  "messages": [...],
  "stream": true
}
```

**응답 (Server-Sent Events):**
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1695365700,"model":"youtube-agent","choices":[{"index":0,"delta":{"content":"슈카"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1695365700,"model":"youtube-agent","choices":[{"index":0,"delta":{"content":"월드의"},"finish_reason":null}]}

data: [DONE]
```

### 4. 모델 관리

#### 모델 목록
```http
GET /v1/models
```

**응답 예시:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "youtube-agent",
      "object": "model",
      "created": 1695365700,
      "owned_by": "youtube-content-agent",
      "permission": [],
      "root": "youtube-agent",
      "parent": null
    }
  ]
}
```

### 5. 채널 관리

#### 채널 목록 조회
```http
GET /channels
```

**쿼리 파라미터:**
- `platform`: 플랫폼 필터 (youtube)
- `is_active`: 활성 상태 필터 (true/false)

**응답 예시:**
```json
[
  {
    "id": 1,
    "name": "슈카월드",
    "url": "https://www.youtube.com/@syukaworld",
    "platform": "youtube",
    "category": "경제",
    "description": "경제 이야기를 쉽게 풀어내는 채널",
    "language": "ko",
    "is_active": true
  }
]
```

#### 채널 추가
```http
POST /api/channels
```

**요청 본문:**
```json
{
  "name": "슈카월드",
  "url": "https://www.youtube.com/@syukaworld",
  "platform": "youtube",
  "category": "경제",
  "description": "경제 콘텐츠",
  "language": "ko"
}
```

**응답 예시:**
```json
{
  "id": 1,
  "name": "슈카월드",
  "url": "https://www.youtube.com/@syukaworld",
  "platform": "youtube",
  "category": "경제",
  "description": "경제 콘텐츠",
  "language": "ko",
  "is_active": true
}
```

#### 채널 수정
```http
PUT /api/channels/{channel_id}
```

**요청 본문:**
```json
{
  "name": "수정된 채널명",
  "category": "수정된 카테고리",
  "description": "수정된 설명",
  "is_active": true
}
```

#### 채널 삭제 (비활성화)
```http
DELETE /api/channels/{channel_id}
```

**응답 예시:**
```json
{
  "message": "채널 '슈카월드'이 비활성화되었습니다",
  "channel_id": 1
}
```

#### 채널 활성화
```http
POST /api/channels/{channel_id}/activate
```

**응답 예시:**
```json
{
  "message": "채널 '슈카월드'이 활성화되었습니다",
  "channel_id": 1
}
```

### 6. 작업 관리

#### 처리 작업 상태
```http
GET /jobs
```

**쿼리 파라미터:**
- `status`: pending, processing, completed, failed
- `job_type`: collect, stt, vectorize
- `limit`: 결과 개수 제한

**응답 예시:**
```json
{
  "jobs": [
    {
      "id": 123,
      "job_type": "stt",
      "status": "processing",
      "content_id": "abc123",
      "created_at": "2025-09-18T10:00:00Z",
      "started_at": "2025-09-18T10:05:00Z",
      "progress": 45,
      "error_message": null
    }
  ],
  "total": 25,
  "pending": 10,
  "processing": 5,
  "completed": 8,
  "failed": 2
}
```

#### 작업 재시도
```http
POST /jobs/{job_id}/retry
```

### 7. 질의응답

#### 단순 질문
```http
POST /ask
```

**요청 본문:**
```json
{
  "query": "최근 경제 전망은 어떤가요?",
  "sources_count": 5
}
```

**응답 예시:**
```json
{
  "answer": "최근 YouTube 콘텐츠를 분석한 결과...",
  "sources": [
    {
      "title": "2025년 경제 전망",
      "channel": "슈카월드",
      "url": "https://youtube.com/watch?v=ABC123&t=300s",
      "relevance": 0.92
    }
  ],
  "processing_time_ms": 1234
}
```

### 8. 트렌딩 토픽

#### 인기 주제
```http
GET /trending
```

**쿼리 파라미터:**
- `period`: today, week, month
- `limit`: 10

**응답 예시:**
```json
{
  "topics": [
    {
      "topic": "코스피 전망",
      "mentions": 45,
      "channels": ["슈카월드", "경제 브리핑"],
      "trend": "increasing"
    }
  ],
  "period": "week",
  "generated_at": "2025-09-18T10:30:00Z"
}
```

## 에러 응답

### 에러 형식
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found",
    "details": {
      "resource_id": "abc123"
    }
  },
  "request_id": "req_xyz789",
  "timestamp": "2025-09-18T10:30:00Z"
}
```

### 에러 코드

| 코드 | HTTP 상태 | 설명 |
|------|----------|------|
| `INVALID_REQUEST` | 400 | 잘못된 요청 형식 |
| `UNAUTHORIZED` | 401 | 인증 실패 |
| `FORBIDDEN` | 403 | 접근 권한 없음 |
| `RESOURCE_NOT_FOUND` | 404 | 리소스를 찾을 수 없음 |
| `RATE_LIMIT_EXCEEDED` | 429 | 요청 한도 초과 |
| `INTERNAL_ERROR` | 500 | 서버 내부 오류 |
| `SERVICE_UNAVAILABLE` | 503 | 서비스 일시적 불가 |

## Rate Limiting

- **기본 한도**: 분당 60 요청
- **인증된 사용자**: 분당 600 요청
- **헤더 정보**:
  - `X-RateLimit-Limit`: 한도
  - `X-RateLimit-Remaining`: 남은 요청 수
  - `X-RateLimit-Reset`: 리셋 시간 (Unix timestamp)

## 인증

### API Key 인증
```http
Authorization: Bearer YOUR_API_KEY
```

### 헤더 예시
```http
POST /v1/chat/completions
Authorization: Bearer sk-proj-xxxxxxxxxxxxx
Content-Type: application/json
```

## WebSocket 엔드포인트

### 실시간 채팅
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'message',
    content: '안녕하세요'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

## SDK 예제

### Python
```python
import requests

# 검색 API 호출
response = requests.post(
    "http://localhost:8000/search",
    json={
        "query": "경제 전망",
        "limit": 5
    }
)
results = response.json()

# 채팅 API 호출
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "youtube-agent",
        "messages": [
            {"role": "user", "content": "질문입니다"}
        ]
    }
)
answer = response.json()
```

### JavaScript/Node.js
```javascript
// 검색 API 호출
const searchResponse = await fetch('http://localhost:8000/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    query: '경제 전망',
    limit: 5
  })
});
const results = await searchResponse.json();

// 채팅 API 호출
const chatResponse = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    model: 'youtube-agent',
    messages: [
      { role: 'user', content: '질문입니다' }
    ]
  })
});
const answer = await chatResponse.json();
```

## Swagger UI 사용법

### 1. Swagger UI 접속
브라우저에서 http://localhost:8000/docs 접속

### 2. API 테스트
1. 테스트하려는 엔드포인트 클릭
2. "Try it out" 버튼 클릭
3. 파라미터 입력
4. "Execute" 버튼 클릭
5. 응답 확인

### 3. 관리 대시보드에서 테스트
1. http://localhost:8090/api-docs 접속
2. 내장된 Swagger UI에서 직접 테스트
3. 또는 빠른 테스트 버튼 사용

## OpenAPI Specification

완전한 OpenAPI 3.0 스펙은 다음에서 확인할 수 있습니다:
- **JSON**: `http://localhost:8000/openapi.json`
- **Swagger UI**: `http://localhost:8000/docs` (대화형 테스트)
- **ReDoc**: `http://localhost:8000/redoc` (읽기 전용 문서)
- **관리 대시보드**: `http://localhost:8090` (통합 관리 UI)