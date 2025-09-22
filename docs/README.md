# 📚 YouTube Agent 문서 모음

이 디렉토리는 YouTube Agent 프로젝트의 상세 기술 문서를 포함합니다.

## 📖 문서 구조

### 🏠 루트 문서 (프로젝트 루트)
- **[README.md](../README.md)** - 프로젝트 개요 및 빠른 시작 가이드
- **[CLAUDE.md](../CLAUDE.md)** - Claude AI를 위한 개발자 가이드

### 📁 상세 문서 (docs 폴더)

#### 아키텍처 및 설계
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - 시스템 아키텍처 상세 설명
  - 마이크로서비스 구조
  - 데이터 플로우
  - 기술 스택
  - 확장성 전략

- **[PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)** - 프로젝트 디렉토리 구조
  - 파일 구성
  - 모듈 설명
  - 의존성 관계

#### 개발 계획
- **[ROADMAP.md](./ROADMAP.md)** - 개발 로드맵
  - 단기 계획 (1-2개월)
  - 중기 계획 (3-6개월)
  - 장기 계획 (6-12개월)
  - KPIs 및 성공 지표

#### 운영 및 관리
- **[PROJECT_STATUS.md](./PROJECT_STATUS.md)** - 현재 프로젝트 상태
  - 시스템 현황 대시보드
  - 최근 개선사항
  - 알려진 이슈
  - 액션 아이템

- **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** - 문제 해결 가이드
  - 일반적인 오류 해결
  - GPU/CPU 모드 전환
  - 네트워크 문제
  - 성능 최적화

## 🔗 빠른 참조

### 서비스 URL
| 서비스 | URL | 설명 |
|--------|-----|------|
| OpenWebUI | http://localhost:3000 | 채팅 인터페이스 |
| Admin Dashboard | http://localhost:8090 | 통합 관리 대시보드 |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Monitoring | http://localhost:8081 | 실시간 모니터링 |
| Cost Management | http://localhost:8084 | STT 비용 관리 |

### 핵심 명령어
```bash
# 🚀 서비스 시작
./start.sh                # 자동 환경 감지
./start_gpu.sh           # GPU 모드
./start_cpu.sh           # CPU/API 모드

# 🔧 관리
docker-compose logs -f   # 로그 확인
docker ps               # 컨테이너 상태
docker restart [name]   # 서비스 재시작

# 🛑 종료
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml down
```

## 📝 문서 관리 가이드

### 문서 업데이트 원칙
1. **명확성**: 기술적 정확성과 이해하기 쉬운 설명
2. **일관성**: 통일된 용어와 포맷 사용
3. **최신성**: 변경사항 즉시 반영
4. **추적성**: 업데이트 날짜와 버전 명시

### 문서별 담당
- **README.md, CLAUDE.md**: 전체 팀
- **ARCHITECTURE.md**: 아키텍처 팀
- **ROADMAP.md**: 프로덕트 팀
- **PROJECT_STATUS.md**: 운영 팀
- **TROUBLESHOOTING.md**: DevOps 팀

---

**최종 업데이트**: 2025년 9월 23일
**문서 버전**: 1.0.0
**관리자**: YouTube Agent 개발팀