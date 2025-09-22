# 📦 Backup Directory

이 디렉토리는 프로젝트의 구버전 파일과 실험적 코드를 보관합니다.

## 📁 디렉토리 구조

```
.backup/
├── deprecated/     # 더 이상 사용하지 않는 구버전 파일
└── experimental/   # 실험적/최적화 시도 코드 (미적용)
```

## 🗂️ deprecated/ - 구버전 파일

현재 아키텍처로 마이그레이션되면서 사용하지 않게 된 파일들:

- **Makefile.old**: 단일 docker-compose.yml 기준 (현재: base/gpu/cpu 분리)
- **docker-compose.yml.old**: 구버전 단일 구성 (현재: 모듈화된 구성)
- **main.py.old**: 초기 CLI 진입점 (현재: Docker 마이크로서비스)
- **README_old.md**: 이전 버전 문서
- **docs/**: 2025년 9월 18-19일 작성된 구버전 문서들

### 마이그레이션 일자
- 2025년 9월 23일

## 🧪 experimental/ - 실험적 코드

성능 최적화나 새로운 접근을 시도했지만 아직 적용되지 않은 코드:

### docker/
- **docker-compose.optimized.yml**: 최적화 시도 버전

### services/data-processor/
- **Dockerfile.optimized**: 최적화된 Dockerfile
- **enhanced_vectorizer.py**: 개선된 벡터화 로직
- **improved_stt_worker*.py**: STT 워커 개선 버전들

### scripts/
- **rebuild-optimized.sh**: 최적화 빌드 스크립트

## ⚠️ 주의사항

1. **deprecated/** 폴더의 파일들은 참조용으로만 보관
2. **experimental/** 폴더의 코드는 충분한 테스트 후 적용
3. 이 폴더는 `.gitignore`에 포함될 수 있음 (팀 결정 필요)

## 🗑️ 정리 기준

### 삭제 가능 시점
- **deprecated/**: 새 구조가 3개월 이상 안정적 운영 후
- **experimental/**: 코드 리뷰 후 적용 또는 폐기 결정

### 보관 이유
- 롤백 필요시 참조
- 히스토리 보존
- 실험적 아이디어 보관

---
**마지막 정리**: 2025년 9월 23일