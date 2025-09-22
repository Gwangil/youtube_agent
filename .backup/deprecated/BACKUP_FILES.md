# 백업 파일 관리

이 문서는 프로젝트의 백업 파일들과 실험적 버전들의 목록입니다.

## 백업 디렉토리 구조

```
backup/
├── docker/                          # Docker 설정 백업
│   └── docker-compose.optimized.yml # 최적화 시도 버전
├── scripts/                         # 스크립트 백업
│   └── rebuild-optimized.sh         # 최적화된 빌드 스크립트
└── services/                        # 서비스 코드 백업
    └── data-processor/
        ├── Dockerfile.optimized      # 최적화된 Dockerfile
        ├── improved_stt_worker.py    # STT 워커 초기 개선 버전
        ├── improved_stt_worker_nogpu_fallback.py  # GPU 폴백 없는 버전
        └── improved_stt_worker_v2.py # STT 워커 v2 (비용 관리 이전)
```

## 현재 사용 중인 파일들

### Docker 설정
- **실제 사용**: `docker-compose.yml`
- **백업**: `backup/docker/docker-compose.optimized.yml`

### Data Processor 서비스
- **실제 사용**:
  - `services/data-processor/stt_worker.py` (이전 improved_stt_worker_with_cost.py)
  - `services/data-processor/vectorize_worker.py` (통합 벡터화 워커)
- **백업**:
  - `backup/services/data-processor/improved_stt_worker*.py` (이전 버전들)
  - `backup/services/data-processor/enhanced_vectorizer.py` (다층 벡터화 실험 버전)

## 버전 히스토리

### STT Worker 진화 과정
1. `improved_stt_worker.py` - 초기 개선 버전
2. `improved_stt_worker_nogpu_fallback.py` - GPU 서버 전용 (폴백 제거)
3. `improved_stt_worker_v2.py` - 구조 개선
4. `improved_stt_worker_with_cost.py` → `stt_worker.py` (현재 버전)
   - GPU 서버 우선
   - OpenAI API 폴백
   - 비용 관리 통합

### Vectorize Worker 진화 과정
1. `improved_vectorize_worker.py` - 초기 개선 버전
2. `enhanced_vectorizer.py` - 다층 벡터화 실험 (paragraphs, full_text 등)
3. `vectorize_worker.py` (현재 버전)
   - Summary 생성 및 저장 통합
   - 의미 기반 청킹
   - 타임스탬프 보존
   - YouTube URL 생성
   - 임베딩 캐싱

## 백업 파일 복원

필요시 백업 파일을 복원하려면:

```bash
# 예: STT 워커 이전 버전 복원
cp backup/services/data-processor/improved_stt_worker_v2.py services/data-processor/stt_worker.py

# Docker 설정 복원
cp backup/docker/docker-compose.optimized.yml docker-compose.yml
```

## 정리 정책

- 백업 파일들은 최소 1개월 보관
- 프로덕션에서 안정화 후 3개월 후 삭제 검토
- 중요한 변경사항이 있던 버전은 영구 보관

## 현재 아키텍처 요약

### 실제 사용 중인 워커들
- **STT 처리**: `stt_worker.py` (3개 워커)
  - GPU 서버 우선, OpenAI API 폴백
  - 비용 관리 통합
- **벡터화 처리**: `vectorize_worker.py` (3개 워커)
  - youtube_summaries 컬렉션: 요약 저장
  - youtube_content 컬렉션: 세부 청크 저장
  - 임베딩 서버 사용 (BGE-M3 1024차원)

---
**마지막 정리**: 2025-09-22
**업데이트 내용**:
- enhanced_vectorizer.py를 백업으로 이동
- vectorize_worker.py에 Summary 생성 기능 통합
- 중복 vectorizer 코드 정리