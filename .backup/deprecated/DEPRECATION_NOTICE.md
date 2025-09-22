# ⚠️ DEPRECATION NOTICE

이 폴더에는 프로젝트 구조 변경으로 인해 더 이상 사용되지 않는 파일들이 보관되어 있습니다.

## 📅 백업 일시
- 2025년 9월 23일

## 📂 백업된 파일들

### Makefile.old
- 구버전 Makefile (단일 docker-compose.yml 기준)
- 새 버전: 프로젝트 루트의 `Makefile` (GPU/CPU 모드 분리 지원)

### docker-compose.yml.old
- 구버전 단일 docker-compose.yml
- 새 버전: docker-compose.base.yml + gpu/cpu.yml 분리 구성

### main.py.old
- 초기 CLI 진입점 (더 이상 사용하지 않음)
- 현재: Docker 기반 마이크로서비스 아키텍처

### docs/ 폴더
- 구버전 문서들 (2025년 9월 18-19일 작성)
- 포함된 파일:
  - API.md
  - ARCHITECTURE.md (구버전)
  - DEPLOYMENT.md
  - EDUCATION.md
  - INDEX.md
  - INSTALLATION.md
  - OPERATIONS.md
  - QUICKSTART.md
  - TESTING.md
  - TUTORIAL.md

## 🔄 마이그레이션 정보

### 주요 변경사항
1. **Docker Compose 구조 변경**
   - 이전: 단일 `docker-compose.yml`
   - 현재: `docker-compose.base.yml` + `docker-compose.gpu.yml`/`docker-compose.cpu.yml`

2. **문서 위치 변경**
   - 핵심 문서는 프로젝트 루트로 이동
   - `docs/` 폴더는 참조 링크만 제공

3. **실행 방법 변경**
   - 이전: `docker-compose up -d`
   - 현재: `./start.sh` (자동 환경 감지)

## 📚 현재 사용 중인 문서
- [README.md](../README.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [CLAUDE.md](../CLAUDE.md)
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)

## ⚡ 빠른 시작
```bash
# 새로운 방식으로 프로젝트 시작
cd ..
./start.sh

# 또는 Make 명령어 사용
make start
```

## 🗑️ 삭제 가능 시점
이 백업 폴더는 다음 조건이 충족되면 삭제 가능합니다:
- 새로운 구조가 최소 1개월 이상 안정적으로 운영
- 모든 팀원이 새로운 구조에 익숙해짐
- 구버전 참조가 더 이상 필요하지 않음

---
**Note**: 이 파일들은 참조용으로만 보관되며, 실제 사용하지 마세요.