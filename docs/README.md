# YouTube Agent 문서

이 디렉토리는 프로젝트의 주요 문서에 대한 참조를 제공합니다.

## 📚 주요 문서

### 핵심 문서 (프로젝트 루트)
- [README.md](../README.md) - 프로젝트 개요 및 빠른 시작
- [ARCHITECTURE.md](../ARCHITECTURE.md) - 시스템 아키텍처 상세 설명
- [CLAUDE.md](../CLAUDE.md) - 개발자 가이드 및 기술 상세
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - 문제 해결 가이드

## 🔧 스크립트 및 도구
- [start.sh](../start.sh) - 자동 환경 감지 및 시작
- [start_gpu.sh](../start_gpu.sh) - GPU 모드 시작
- [start_cpu.sh](../start_cpu.sh) - CPU 모드 시작
- [detect_environment.sh](../detect_environment.sh) - 환경 감지
- [fix_network.sh](../fix_network.sh) - 네트워크 문제 해결
- [cleanup_old_containers.sh](../cleanup_old_containers.sh) - 컨테이너 정리

## 📁 구성 파일
- [docker-compose.base.yml](../docker-compose.base.yml) - 공통 인프라
- [docker-compose.gpu.yml](../docker-compose.gpu.yml) - GPU 모드 서비스
- [docker-compose.cpu.yml](../docker-compose.cpu.yml) - CPU 모드 서비스
- [.env.example](../.env.example) - 환경 변수 예제

## 🗂️ 백업된 문서
이전 버전의 문서들은 [backup_deprecated/docs/](../backup_deprecated/docs/) 폴더에 보관되어 있습니다.

## 🆕 최근 변경사항 (2025-09-23)
- GPU/CPU 모드 분리 구성
- 새로운 Makefile 작성
- 문서 구조 정리
- deprecated 파일 백업

## 🌐 서비스 접속
- OpenWebUI: http://localhost:3000
- Admin Dashboard: http://localhost:8090
- API Docs: http://localhost:8000/docs
- Cost Management: http://localhost:8084
- Monitoring: http://localhost:8081

## 💡 빠른 명령어
```bash
# 프로젝트 시작
make start

# 상태 확인
make status

# 로그 확인
make logs

# 도움말
make help
```