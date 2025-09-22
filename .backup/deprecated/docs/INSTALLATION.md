# 설치 가이드

## 시스템 요구사항

### 최소 사양
- **CPU**: 4 코어 이상
- **RAM**: 16GB (Whisper Large 모델 실행용)
- **저장공간**: 50GB 이상
- **OS**: Ubuntu 20.04+, macOS 12+, Windows 10+ (WSL2)

### 권장 사양
- **CPU**: 8 코어 이상
- **RAM**: 32GB
- **GPU**: NVIDIA GPU (CUDA 11.8+)
- **저장공간**: 100GB SSD

### 필수 소프트웨어
- Docker 24.0+
- Docker Compose 2.20+
- Git
- Python 3.11+ (개발용)

## 설치 단계

### 1. Docker 설치

#### Ubuntu/Debian
```bash
# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose 설치
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

#### macOS
```bash
# Docker Desktop 다운로드 및 설치
# https://www.docker.com/products/docker-desktop/

# 또는 Homebrew 사용
brew install --cask docker
```

#### Windows (WSL2)
1. WSL2 설치 및 활성화
2. Docker Desktop for Windows 설치
3. WSL2 백엔드 활성화

### 2. 프로젝트 클론

```bash
# 저장소 클론
git clone https://github.com/your-org/youtube_agent.git
cd youtube_agent

# 브랜치 확인
git branch -a
```

### 3. 환경 변수 설정

```bash
# 환경 변수 파일 생성
cp .env.example .env

# 환경 변수 편집
nano .env
```

필수 환경 변수:
```env
# OpenAI API (필수)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# 데이터베이스 설정
DATABASE_URL=postgresql://youtube_user:youtube_pass@postgres:5432/youtube_agent
POSTGRES_USER=youtube_user
POSTGRES_PASSWORD=youtube_pass
POSTGRES_DB=youtube_agent

# Redis 설정
REDIS_URL=redis://redis:6379/0

# Qdrant 설정
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=optional_api_key

# 서비스 포트
AGENT_PORT=8000
UI_PORT=3000
QDRANT_PORT=6333

# 로깅 레벨
LOG_LEVEL=INFO

# 워커 설정
WORKER_CONCURRENCY=2
BATCH_SIZE=10
```

### 4. 모델 다운로드 (선택사항)

Whisper 모델을 사전 다운로드하여 첫 실행 속도 향상:

```bash
# 모델 다운로드 스크립트 실행
./download_models.sh

# 또는 Python으로 직접 다운로드
python -c "import whisper; whisper.load_model('large')"
```

### 5. Docker 이미지 빌드

```bash
# 모든 서비스 이미지 빌드
docker-compose build

# 특정 서비스만 빌드
docker-compose build data-processor
```

### 6. 서비스 시작

```bash
# 백그라운드에서 모든 서비스 시작
docker-compose up -d

# 로그와 함께 시작 (디버깅용)
docker-compose up

# 특정 서비스만 시작
docker-compose up -d postgres redis qdrant
docker-compose up -d data-collector data-processor
docker-compose up -d agent-service ui-service
```

### 7. 서비스 확인

```bash
# 컨테이너 상태 확인
docker-compose ps

# 헬스체크
curl http://localhost:8000/health

# 로그 확인
docker-compose logs -f --tail=100
```

## GPU 설정 (선택사항)

### NVIDIA GPU 지원

1. NVIDIA 드라이버 설치
```bash
# Ubuntu
sudo apt-get update
sudo apt-get install nvidia-driver-535
```

2. NVIDIA Container Toolkit 설치
```bash
# 저장소 설정
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# 설치
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

3. Docker Compose 설정 수정
```yaml
# docker-compose.yml
services:
  data-processor:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 초기 데이터 설정

### YouTube 채널 추가

```python
# services/data-collector/app.py 수정
channels = [
    "https://www.youtube.com/@channelname1",
    "https://www.youtube.com/@channelname2",
]
```

### 데이터베이스 초기화

```bash
# 데이터베이스 마이그레이션
docker-compose exec data-collector python -c "
from shared.models.database import Base, engine
Base.metadata.create_all(bind=engine)
print('Database initialized')
"
```

### 첫 번째 수집 실행

```bash
# 수동으로 수집 트리거
docker-compose exec data-collector python -c "
from app import collect_all_channels
collect_all_channels()
"
```

## 문제 해결

### Docker 관련 문제

```bash
# Docker 데몬이 실행 중인지 확인
sudo systemctl status docker

# Docker 재시작
sudo systemctl restart docker

# 권한 문제 해결
sudo chmod 666 /var/run/docker.sock
```

### 포트 충돌

```bash
# 사용 중인 포트 확인
sudo lsof -i :8000
sudo lsof -i :3000

# 포트 변경 (.env 파일)
AGENT_PORT=8001
UI_PORT=3001
```

### 메모리 부족

```bash
# Docker 메모리 제한 확인
docker system info | grep -i memory

# 불필요한 이미지/컨테이너 정리
docker system prune -a
```

### 네트워크 문제

```bash
# Docker 네트워크 재생성
docker-compose down
docker network prune
docker-compose up -d
```

## 설치 확인

설치가 완료되면 다음을 확인하세요:

1. **OpenWebUI 접속**: http://localhost:3000
2. **API 문서**: http://localhost:8000/docs
3. **Qdrant 대시보드**: http://localhost:6333/dashboard

모든 서비스가 정상적으로 실행되면 설치가 완료된 것입니다.