# 🔐 YouTube Agent 데이터 백업 가이드

이 디렉토리는 YouTube Agent의 모든 데이터를 안전하게 백업하고 복원하기 위한 시스템입니다.

## ⚠️ 보안 주의사항

**이 폴더의 데이터는 매우 중요하고 민감합니다:**
- 데이터베이스 전체 덤프
- 벡터 인덱스 스냅샷
- 사용자 데이터 및 트랜스크립트
- 모델 바이너리 파일

**절대 공유하지 마세요:**
- Git에 커밋되지 않음 (.gitignore에 등록됨)
- 외부 저장소에 업로드 금지
- 팀 내부에서만 안전하게 공유

---

## 📂 백업 디렉토리 구조

```
.backup/
├── postgresql/          # PostgreSQL 데이터베이스 백업
│   ├── youtube_agent_*.sql.gz
│   ├── channels_*.sql.gz
│   ├── content_*.sql.gz
│   └── transcripts_*.sql.gz
├── qdrant/             # Qdrant 벡터 DB 스냅샷
│   ├── youtube_content_*.snapshot
│   └── youtube_summaries_*.snapshot
├── redis/              # Redis 덤프 파일
│   └── redis_*.rdb
├── models/             # 모델 바이너리 파일 (선택적)
│   └── whisper_large_v3.pt
├── scripts/            # 백업/복원 스크립트
│   ├── backup_all.sh   # 전체 백업
│   └── restore.sh      # 데이터 복원
└── backup_metadata_*.json  # 백업 메타데이터
```

---

## 🚀 사용법

### 1. 전체 백업 생성

```bash
# 모든 데이터 백업 (PostgreSQL, Qdrant, Redis, Models)
./.backup/scripts/backup_all.sh

# 실행 결과:
# - 타임스탬프가 포함된 백업 파일 생성
# - 자동으로 압축 (gzip)
# - 7일 이상 된 백업 자동 삭제
```

### 2. 데이터 복원

```bash
# 특정 시점으로 복원
./.backup/scripts/restore.sh [timestamp]

# 예시:
./.backup/scripts/restore.sh 20250923_120000

# 사용 가능한 백업 확인:
./.backup/scripts/restore.sh
```

### 3. 수동 백업 명령어

#### PostgreSQL 백업
```bash
# 전체 데이터베이스 백업
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent \
    | gzip > .backup/postgresql/manual_$(date +%Y%m%d).sql.gz

# 특정 테이블만 백업
docker exec youtube_postgres pg_dump -U youtube_user -d youtube_agent \
    -t content -t transcripts \
    > .backup/postgresql/content_data.sql
```

#### Qdrant 백업
```bash
# 스냅샷 생성
curl -X POST http://localhost:6333/collections/youtube_content/snapshots

# 스냅샷 목록 확인
curl http://localhost:6333/collections/youtube_content/snapshots
```

#### Redis 백업
```bash
# Redis 데이터 덤프
docker exec youtube_redis redis-cli BGSAVE
docker cp youtube_redis:/data/dump.rdb .backup/redis/redis_backup.rdb
```

---

## 📊 백업 정책

### 권장 백업 주기
- **일일 백업**: 프로덕션 환경
- **주간 백업**: 개발 환경
- **즉시 백업**: 중요 변경 전후

### 보관 정책
- **로컬**: 최근 7일간 백업 유지
- **외부 저장소**: 월별 백업 1개씩 보관 (수동)
- **아카이브**: 분기별 전체 백업 (선택적)

### 백업 크기 예상
| 데이터 유형 | 예상 크기 | 압축 후 |
|------------|----------|---------|
| PostgreSQL | ~100MB | ~20MB |
| Qdrant | ~500MB | ~150MB |
| Redis | ~10MB | ~3MB |
| Models | ~3GB | N/A |

---

## 🔧 문제 해결

### 백업 실패 시
1. Docker 컨테이너 상태 확인
   ```bash
   docker ps | grep youtube
   ```

2. 디스크 공간 확인
   ```bash
   df -h .backup/
   ```

3. 권한 확인
   ```bash
   ls -la .backup/scripts/
   ```

### 복원 실패 시
1. 백업 파일 무결성 확인
   ```bash
   gunzip -t .backup/postgresql/*.sql.gz
   ```

2. 서비스 재시작
   ```bash
   docker restart youtube_postgres youtube_qdrant youtube_redis
   ```

3. 로그 확인
   ```bash
   docker logs youtube_postgres --tail 50
   ```

---

## 🔒 보안 체크리스트

- [ ] `.backup/` 폴더가 `.gitignore`에 등록되었는지 확인
- [ ] 백업 파일에 민감한 정보(API 키, 비밀번호)가 포함되지 않았는지 확인
- [ ] 백업 스크립트 실행 권한이 적절히 설정되었는지 확인
- [ ] 외부 저장소 업로드 시 암호화 적용
- [ ] 정기적인 백업 무결성 테스트

---

## 📝 메타데이터 형식

각 백업 시 생성되는 `backup_metadata_*.json` 파일 형식:

```json
{
    "timestamp": "20250923_120000",
    "date": "2025-09-23T12:00:00+09:00",
    "services": {
        "postgresql": 105,  // 콘텐츠 수
        "qdrant": 2,       // 컬렉션 수
        "redis": 42        // 키 개수
    },
    "backup_files": [
        "/path/to/backup/file1.sql.gz",
        "/path/to/backup/file2.snapshot"
    ]
}
```

---

## 🆘 긴급 연락처

백업/복원 관련 문제 발생 시:
- **Slack**: #youtube-agent-ops
- **담당자**: DevOps 팀

---

**마지막 업데이트**: 2025년 9월 23일
**버전**: 1.0.0
**관리자**: YouTube Agent DevOps 팀