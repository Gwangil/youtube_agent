# 운영 가이드

## 🛠️ 서비스 제어 명령

### 서비스 라이프사이클 관리

#### 일시 정지/재개 (메모리 유지)
```bash
# 모든 서비스 일시 정지 (상태 보존)
make pause

# 일시 정지된 서비스 재개
make unpause
```
**특징**: 컨테이너 메모리와 상태를 그대로 유지하면서 CPU 사용만 중단

#### 정지/시작 (컨테이너 유지)
```bash
# 모든 서비스 정지
make stop

# 정지된 서비스 시작
make start
```
**특징**: 컨테이너는 유지하되 프로세스를 종료

#### 안전한 정지/시작 (데이터 무결성 보장)
```bash
# 처리 중인 작업 완료 대기 후 정지
make safe-stop

# 안전하게 시작 (stuck 작업 정리)
make safe-start
```
**특징**:
- 처리 중인 작업을 pending으로 안전하게 리셋
- 임시 파일 정리
- 1시간 이상 stuck된 작업 자동 재설정

#### 완전 종료/시작 (컨테이너 재생성)
```bash
# 모든 컨테이너 제거
make down

# 컨테이너 새로 생성 및 시작
make up
```
**특징**: 컨테이너를 완전히 제거하고 재생성 (볼륨 데이터는 유지)

### 서비스 중단 시나리오별 가이드

#### 1. 짧은 유지보수 (5분 이내)
```bash
# 일시 정지 사용
make pause
# ... 유지보수 작업 ...
make unpause
```

#### 2. 중간 유지보수 (30분 이내)
```bash
# 안전한 정지 사용
make safe-stop
# ... 유지보수 작업 ...
make safe-start
```

#### 3. 장기 유지보수 (1시간 이상)
```bash
# 완전 종료 사용
make down
# ... 유지보수 작업 ...
make up
make check-data  # 데이터 정합성 확인
```

## 🔄 데이터 정합성 관리

### 정합성 체크

PostgreSQL과 Qdrant 간의 데이터 일관성을 검증하고 문제를 해결하는 기능입니다.

#### 기본 정합성 체크
```bash
# 데이터 정합성 확인
make check-data
```

이 명령은 다음을 확인합니다:
- 데이터베이스 연결 상태
- 필수 테이블 존재 여부
- Qdrant 컬렉션 상태
- PostgreSQL 청크와 Qdrant 벡터 일치 여부
- 오래된 processing 작업 존재 여부

#### 자동 수정 모드
```bash
# 문제를 발견하고 자동으로 수정
make check-data-fix
```

자동으로 수정되는 사항:
- 고아 벡터 삭제 (Qdrant에만 있는 벡터)
- 1일 이상 처리 중인 작업 재설정

#### 개별 수정 작업
```bash
# 멈춘 작업만 재설정
make reset-stuck-jobs

# 고아 벡터만 삭제
make clean-orphans
```

### 정합성 보고서 해석

정합성 체크 결과는 다음 상태로 분류됩니다:

- **✅ healthy**: 모든 검증 통과
- **⚠️ warning**: 경고 사항 발견 (예: 고아 벡터, 멈춘 작업)
- **❌ critical**: 심각한 문제 발견 (예: DB 연결 실패)

## 🔄 데이터 초기화

### 소프트 리셋 (채널 보존)

채널 정보는 유지하고 콘텐츠 데이터만 삭제합니다.

```bash
make reset-soft
```

삭제되는 데이터:
- ✅ 모든 YouTube 콘텐츠
- ✅ STT 처리 결과 (전사)
- ✅ 청크 데이터
- ✅ Qdrant 벡터
- ✅ 처리 작업 큐
- ✅ Redis 캐시
- ✅ 임시 파일

보존되는 데이터:
- 💾 채널 정보 (channels 테이블)

### 하드 리셋 (전체 초기화)

모든 데이터를 완전히 삭제합니다.

```bash
make reset-hard
```

⛔ **경고**: 이 작업은 되돌릴 수 없습니다!
- 모든 채널 정보
- 모든 콘텐츠 데이터
- 모든 처리 결과
- 모든 벡터 데이터

### 초기화 시나리오

#### 1. 테스트 환경 초기화
```bash
# 테스트 완료 후 데이터 정리
make reset-soft

# 새 채널 추가 및 테스트
```

#### 2. 오류 복구
```bash
# 정합성 체크
make check-data

# 문제가 있으면 소프트 리셋
make reset-soft

# 서비스 재시작
make restart
```

#### 3. 완전 초기화
```bash
# 모든 데이터 백업
make backup-all

# 하드 리셋 실행
make reset-hard

# 새로운 채널 추가 시작
```

## 🔍 데이터 정합성 모니터링

### 정기 체크 스크립트

```bash
#!/bin/bash
# daily_integrity_check.sh

# 정합성 체크
if make check-data | grep -q "critical\|warning"; then
    echo "⚠️ 데이터 정합성 문제 발견"

    # 자동 수정 시도
    make check-data-fix

    # 재검증
    make check-data
else
    echo "✅ 데이터 정합성 정상"
fi
```

### Cron 작업 설정

```bash
# crontab -e
0 2 * * * /path/to/daily_integrity_check.sh >> /var/log/integrity_check.log 2>&1
```

## 🐛 문제 해결

### 일반적인 문제 및 해결 방법

#### 데이터 불일치
```bash
# 1. 정합성 체크
make check-data

# 2. 자동 수정
make check-data-fix

# 3. 여전히 문제가 있다면
make reset-soft
```

#### 처리 작업 멈춤
```bash
# 멈춘 작업 확인
make check-jobs

# 멈춘 작업 재설정
make reset-stuck-jobs

# 서비스 재시작
docker restart youtube_data_processor
```

#### Qdrant 벡터 불일치
```bash
# 고아 벡터 정리
make clean-orphans

# 전체 정합성 체크
make check-data-fix
```

### 로그 분석

```bash
# 정합성 체크 로그
docker logs youtube_data_processor | grep "integrity"

# 초기화 작업 로그
docker logs youtube_data_processor | grep "reset"
```

## 📊 성능 모니터링

### 시스템 리소스
```bash
# 컨테이너별 리소스 사용량
docker stats

# 디스크 사용량
df -h

# 메모리 사용량
free -h
```

### 데이터베이스 통계
```bash
# PostgreSQL 통계
make db-shell
\dt+  -- 테이블 크기
SELECT pg_database_size('youtube_agent');  -- DB 크기

# Qdrant 통계
curl http://localhost:6333/collections/youtube_content
```

## 💾 데이터 무결성 보장 메커니즘

### 트랜잭션 기반 작업 처리

#### PostgreSQL ACID 보장
- **Atomicity**: 모든 DB 작업은 트랜잭션으로 처리
- **Consistency**: 외래키 제약과 상태 전이 규칙 적용
- **Isolation**: READ COMMITTED 격리 수준
- **Durability**: WAL(Write-Ahead Logging) 활성화

#### 작업 상태 관리
```
pending → processing → completed/failed
```
- 중단 시 processing → pending 자동 리셋
- 재시작 시 pending 작업 자동 재처리
- 실패 시 retry_count 증가 및 재시도

### 서비스 중단 시 데이터 보호

#### Graceful Shutdown 프로세스
1. **작업 완료 대기** (30초)
2. **Processing 작업 리셋**
3. **임시 파일 정리**
4. **서비스 정지**

```python
# scripts/graceful_shutdown.py
def reset_processing_jobs(self, grace_period_seconds=30):
    # 처리 중인 작업을 안전하게 pending으로 리셋
    processing_jobs = session.query(ProcessingJob).filter(
        ProcessingJob.status == 'processing'
    ).all()

    for job in processing_jobs:
        job.status = 'pending'
        job.started_at = None
        job.error_message = "Service stopped during processing"
```

### 데이터 일관성 유지

#### Qdrant 벡터 동기화
- 청크 생성 시 벡터 즉시 생성
- 삭제 시 cascade delete로 일관성 유지
- 정기적인 orphan 벡터 정리

#### Redis 캐시 관리
- 서비스 재시작 시 자동 캐시 재구성
- TTL 설정으로 오래된 데이터 자동 제거

## 🔒 백업 및 복구

### 정기 백업

```bash
# 전체 백업
make backup-all

# DB만 백업
make db-backup
```

### 복구 절차

```bash
# 1. 서비스 중지
make down

# 2. DB 복원
make db-restore FILE=backup_20250918.sql

# 3. 서비스 시작
make up

# 4. 정합성 체크
make check-data
```

## 📝 체크리스트

### 일일 체크
- [ ] 서비스 상태 확인 (`make ps`)
- [ ] 에러 로그 확인 (`make logs-error`)
- [ ] 처리 작업 상태 (`make check-jobs`)

### 주간 체크
- [ ] 데이터 정합성 (`make check-data`)
- [ ] 백업 생성 (`make db-backup`)
- [ ] 디스크 공간 확인

### 월간 체크
- [ ] 전체 시스템 백업 (`make backup-all`)
- [ ] 성능 분석
- [ ] 오래된 로그 정리 (`make clean-logs`)