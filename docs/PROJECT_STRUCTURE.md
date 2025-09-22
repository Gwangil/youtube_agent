# 📂 YouTube Agent 프로젝트 구조

```
youtube_agent/
│
├── 📄 README.md                    # 프로젝트 개요 및 빠른 시작
├── 📄 Makefile                     # Make 명령어 (GPU/CPU 모드 지원)
├── 📄 .env.example                 # 환경 변수 예제
├── 📄 .env                        # 환경 변수 (Git 제외)
├── 📄 .detected_mode              # 감지된 모드 (gpu/cpu)
│
├── 🚀 시작 스크립트 (루트 레벨 - 쉬운 접근)
│   ├── start.sh                   # 자동 환경 감지 시작
│   ├── start_gpu.sh               # GPU 모드 강제 시작
│   └── start_cpu.sh               # CPU 모드 강제 시작
│
├── 📁 scripts/                    # 유틸리티 스크립트
│   ├── detect_environment.sh     # 환경 감지
│   ├── fix_network.sh            # 네트워크 문제 해결
│   ├── cleanup_old_containers.sh # 컨테이너 정리
│   ├── download_models.sh        # 모델 다운로드
│   └── restart_services.sh       # 서비스 재시작
│
├── 📁 docs/                       # 문서
│   ├── README.md                  # 문서 인덱스
│   ├── ARCHITECTURE.md           # 아키텍처 상세
│   ├── CLAUDE.md                 # 개발자 가이드
│   └── TROUBLESHOOTING.md        # 문제 해결 가이드
│
├── 🐳 Docker Compose 파일
│   ├── docker-compose.base.yml   # 공통 인프라
│   ├── docker-compose.gpu.yml    # GPU 모드 서비스
│   └── docker-compose.cpu.yml    # CPU 모드 서비스
│
├── 📁 src/                        # 핵심 라이브러리
│   └── youtube_agent/
│       ├── __init__.py
│       ├── youtube_extractor.py  # YouTube 데이터 추출
│       ├── stt_processor.py      # STT 처리
│       └── vectorizer.py         # 텍스트 벡터화
│
├── 📁 services/                   # 마이크로서비스
│   ├── data-collector/           # 데이터 수집 서비스
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app.py
│   ├── data-processor/           # 데이터 처리 서비스
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   ├── stt_worker.py
│   │   ├── stt_cost_manager.py
│   │   ├── stt_cost_api.py
│   │   ├── whisper_server.py
│   │   ├── embedding_server.py
│   │   └── embedding_server_wrapper.py
│   ├── agent-service/            # RAG 에이전트 서비스
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   └── rag_agent.py
│   ├── admin-dashboard/          # 관리 대시보드
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   └── templates/
│   └── ui-service/              # OpenWebUI
│       └── docker-compose.override.yml
│
├── 📁 shared/                    # 공통 모듈
│   ├── __init__.py
│   ├── models/
│   │   └── database.py         # DB 모델
│   └── utils/
│       ├── __init__.py
│       ├── logging_config.py   # 로깅 설정
│       └── config.py           # 설정 관리
│
├── 📁 backups/                   # 데이터베이스 백업 (Git 제외)
│
├── 📁 logs/                      # 로그 파일 (Git 제외)
│
├── 📁 models/                    # 모델 파일 (Git 제외)
│   ├── whisper/                 # Whisper 모델
│   └── embeddings/              # 임베딩 모델
│
├── 📁 .backup/                   # 백업 디렉토리 (통합)
│   ├── README.md                # 백업 구조 설명
│   ├── deprecated/              # 구버전 파일
│   │   ├── Makefile.old        # 구버전 Makefile
│   │   ├── docker-compose.yml.old
│   │   └── docs/               # 구버전 문서
│   └── experimental/           # 실험적 코드
│       ├── docker/             # 최적화 시도
│       └── services/           # 개선 버전
│
└── 📄 .gitignore                 # Git 제외 설정

```

## 🎯 핵심 디렉토리 설명

### `/` (루트)
- **README.md**: 프로젝트의 첫 진입점
- **시작 스크립트**: 쉬운 접근을 위해 루트에 배치
- **Docker Compose 파일**: 인프라 정의

### `/scripts`
- 유틸리티 스크립트 모음
- 시작 스크립트에서 참조

### `/docs`
- 모든 상세 문서
- 아키텍처, 개발 가이드, 문제 해결

### `/services`
- 각 마이크로서비스의 독립적 구현
- 자체 Dockerfile과 requirements.txt 포함

### `/shared`
- 서비스 간 공유 코드
- 데이터베이스 모델, 유틸리티

### `/backup_deprecated`
- 이전 버전 파일 백업
- 참조용으로만 보관

## 🚀 빠른 시작

```bash
# 1. 환경 설정
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 설정

# 2. 자동 시작
./start.sh

# 또는 Make 사용
make start
```

## 📝 주요 명령어

```bash
# 서비스 관리
make start          # 자동 시작
make stop           # 중지
make status         # 상태 확인
make logs           # 로그 확인

# 문서 확인
make docs           # 문서 위치 안내

# 정리
make clean          # 컨테이너 정리
make prune          # Docker 시스템 정리
```

## 🔗 관련 문서
- [아키텍처](./docs/ARCHITECTURE.md)
- [개발자 가이드](./docs/CLAUDE.md)
- [문제 해결](./docs/TROUBLESHOOTING.md)