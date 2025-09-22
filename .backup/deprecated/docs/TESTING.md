# 테스트 가이드

## 📋 테스트 전략

### 테스트 레벨
1. **단위 테스트 (Unit Tests)**: 개별 함수/클래스 검증
2. **통합 테스트 (Integration Tests)**: 서비스 간 연동 검증
3. **E2E 테스트 (End-to-End Tests)**: 전체 워크플로우 검증
4. **성능 테스트 (Performance Tests)**: 부하 및 응답시간 검증

## 🧪 단위 테스트

### STT 처리 테스트
```bash
# Whisper 서버 단위 테스트
pytest test/test_whisper_server.py -v

# 반복 텍스트 제거 로직 테스트
pytest test/test_text_cleaning.py::test_remove_repetitive_text -v
```

### 임베딩 테스트
```bash
# 임베딩 차원 및 품질 테스트
python test/test_embeddings_benchmark.py

# BGE-M3 vs OpenAI 일관성 테스트
pytest test/test_embedding_consistency.py -v
```

### 청킹 알고리즘 테스트
```bash
# 문장 기반 청킹 테스트
pytest test/test_chunking.py::test_sentence_chunking -v

# 타임스탬프 보존 테스트
pytest test/test_chunking.py::test_timestamp_preservation -v
```

## 🔗 통합 테스트

### 데이터 파이프라인 테스트
```bash
# 전체 파이프라인 테스트 (수집 → STT → 벡터화)
make test-pipeline

# 구현할 테스트 시나리오:
# 1. YouTube URL 추가
# 2. 비디오 메타데이터 수집 확인
# 3. 오디오 다운로드 및 STT 처리 확인
# 4. 텍스트 청킹 및 벡터화 확인
# 5. Qdrant 저장 확인
```

### API 통합 테스트
```bash
# 현재 구현된 API 테스트
make test-health    # 헬스체크
make test-search    # 검색 기능
make test-chat      # 채팅 기능
make test-all       # 모든 API 테스트
```

### 데이터베이스 정합성 테스트
```bash
# PostgreSQL-Qdrant 일관성 테스트
make check-data

# 트랜잭션 롤백 테스트
pytest test/test_database_transactions.py -v
```

## 🚀 E2E 테스트

### 시나리오 1: 새 채널 추가 및 처리
```bash
# E2E 테스트 스크립트
./test/e2e/test_new_channel.sh

# 테스트 단계:
# 1. 새 YouTube 채널 추가
# 2. 데이터 수집 트리거
# 3. 처리 완료 대기
# 4. 검색 쿼리 실행
# 5. RAG 응답 검증
```

### 시나리오 2: 서비스 중단 복구
```bash
# 복구 테스트
./test/e2e/test_recovery.sh

# 테스트 단계:
# 1. 처리 작업 시작
# 2. 서비스 강제 중단
# 3. 서비스 재시작
# 4. 작업 자동 재개 확인
# 5. 데이터 무결성 검증
```

### 시나리오 3: GPU 폴백 테스트
```bash
# GPU → OpenAI API 폴백 테스트
./test/e2e/test_gpu_fallback.sh

# 테스트 단계:
# 1. GPU 서버 중단 시뮬레이션
# 2. STT 처리 요청
# 3. OpenAI API 폴백 확인
# 4. 처리 품질 검증
```

## 📊 성능 테스트

### 부하 테스트
```bash
# Locust를 사용한 부하 테스트
locust -f test/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users=100 \
  --spawn-rate=10

# 측정 항목:
# - 동시 사용자 처리 능력
# - 평균 응답 시간
# - 에러율
# - 처리량 (RPS)
```

### 벤치마크 테스트
```bash
# STT 처리 속도 벤치마크
python test/benchmark/stt_benchmark.py

# 벡터 검색 속도 벤치마크
python test/benchmark/vector_search_benchmark.py

# 임베딩 생성 속도 비교 (GPU vs API)
python test/benchmark/embedding_benchmark.py
```

### 메모리 프로파일링
```bash
# 메모리 누수 테스트
pytest test/test_memory_leaks.py --memprof

# 장시간 실행 테스트
python test/stress/long_running_test.py --duration=24h
```

## 🐳 Docker 환경 테스트

### 컨테이너 헬스체크
```bash
# 모든 서비스 헬스체크
make health-check-all

# 개별 서비스 헬스체크
docker exec youtube_whisper_server curl -f http://localhost:8082/health
docker exec youtube_embedding_server curl -f http://localhost:8083/health
```

### 볼륨 마운트 테스트
```bash
# 모델 파일 접근 테스트
docker exec youtube_whisper_server ls -la /app/models/whisper/
docker exec youtube_embedding_server python -c "from sentence_transformers import SentenceTransformer; print('BGE-M3 로드 성공')"
```

## 🔄 CI/CD 테스트

### GitHub Actions 워크플로우
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run unit tests
        run: |
          pip install -r requirements.txt
          pytest test/unit/ --cov=src --cov-report=xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
    steps:
      - name: Run integration tests
        run: |
          docker-compose up -d
          make test-all

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run E2E tests
        run: |
          ./test/e2e/run_all_tests.sh
```

### 배포 전 체크리스트
```bash
# 배포 전 필수 테스트
make pre-deploy-check

# 포함 항목:
# 1. 모든 유닛 테스트 통과
# 2. 통합 테스트 통과
# 3. 데이터 정합성 확인
# 4. 성능 벤치마크 기준 충족
# 5. 보안 취약점 스캔
```

## 🔧 테스트 환경 설정

### 테스트 데이터베이스
```bash
# 테스트 DB 생성
docker exec youtube_postgres createdb -U youtube_user youtube_test

# 테스트 데이터 시딩
python test/seed_test_data.py
```

### 환경 변수
```bash
# .env.test
DATABASE_URL=postgresql://youtube_user:youtube_pass@localhost:5432/youtube_test
REDIS_URL=redis://localhost:6379/1
QDRANT_URL=http://localhost:6333
OPENAI_API_KEY=sk-test-key
TEST_MODE=true
```

### Mock 서버
```bash
# OpenAI API Mock 서버 실행
python test/mocks/openai_mock_server.py

# YouTube API Mock 서버 실행
python test/mocks/youtube_mock_server.py
```

## 📈 테스트 커버리지

### 현재 커버리지 목표
- 단위 테스트: 80% 이상
- 통합 테스트: 70% 이상
- E2E 테스트: 주요 시나리오 100%

### 커버리지 리포트
```bash
# 커버리지 측정
pytest --cov=src --cov=services --cov-report=html

# HTML 리포트 확인
open htmlcov/index.html

# 커버리지 배지 생성
coverage-badge -o coverage.svg
```

## 🐛 디버깅 도구

### 로그 분석
```bash
# 에러 로그 필터링
make logs-error

# 특정 요청 추적
docker logs youtube_agent_service 2>&1 | grep "request_id=xyz"
```

### 디버거 연결
```bash
# Python 디버거 연결
docker exec -it youtube_data_processor python -m pdb app.py

# 원격 디버깅 (VS Code)
docker-compose -f docker-compose.debug.yml up
```

## 📝 테스트 작성 가이드

### 단위 테스트 템플릿
```python
import pytest
from unittest.mock import Mock, patch

class TestYourComponent:
    @pytest.fixture
    def setup(self):
        # 테스트 설정
        return Mock()

    def test_should_do_something(self, setup):
        # Given
        expected = "expected_result"

        # When
        result = your_function()

        # Then
        assert result == expected
```

### 통합 테스트 템플릿
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.mark.integration
class TestDataPipeline:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("postgresql://...")
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.rollback()
        session.close()

    def test_full_pipeline(self, db_session):
        # 전체 파이프라인 테스트
        pass
```

## ✅ 테스트 체크리스트

### 개발 중
- [ ] 변경사항에 대한 단위 테스트 작성
- [ ] 기존 테스트 실행 및 통과 확인
- [ ] 테스트 커버리지 확인

### PR 제출 전
- [ ] 모든 테스트 통과
- [ ] 린터 및 포매터 실행
- [ ] 통합 테스트 실행
- [ ] 문서 업데이트

### 배포 전
- [ ] E2E 테스트 실행
- [ ] 성능 테스트 실행
- [ ] 보안 스캔 실행
- [ ] 롤백 계획 준비

## 🚨 일반적인 테스트 문제 해결

### 테스트 실패 시
1. 로그 확인: `pytest -vvs`
2. 단일 테스트 실행: `pytest test/test_file.py::test_name`
3. 디버거 사용: `pytest --pdb`

### 느린 테스트
1. 병렬 실행: `pytest -n 4`
2. 마크 사용: `pytest -m "not slow"`
3. 캐시 활용: `pytest --cache-show`

### 플래키 테스트
1. 재시도 설정: `pytest --reruns 3`
2. 타임아웃 증가: `pytest --timeout=300`
3. 격리 실행: `pytest --forked`

---
**마지막 업데이트**: 2025-09-18