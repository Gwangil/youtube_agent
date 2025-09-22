# 🚀 YouTube Content Agent 배포 가이드

## 📋 목차
- [사전 준비사항](#사전-준비사항)
- [환경별 배포](#환경별-배포)
- [프로덕션 설정](#프로덕션-설정)
- [모니터링 및 운영](#모니터링-및-운영)
- [문제 해결](#문제-해결)

## 사전 준비사항

### 시스템 요구사항

#### 최소 사양
- CPU: 8 Core 이상
- RAM: 16GB (Whisper Large 모델 실행용)
- Storage: 100GB 이상 (콘텐츠 및 모델 저장)
- OS: Ubuntu 20.04+ 또는 Docker 지원 OS

#### 권장 사양
- CPU: 16 Core 이상
- RAM: 32GB
- GPU: NVIDIA RTX 3090 이상 (CUDA 11.8+)
- Storage: 500GB SSD
- Network: 1Gbps 이상

### 필수 소프트웨어
```bash
# Docker & Docker Compose 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# NVIDIA Docker (GPU 사용 시)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

## 환경별 배포

### 1. 개발 환경

```bash
# 저장소 클론
git clone https://github.com/your-org/youtube_agent.git
cd youtube_agent

# 환경 변수 설정
cp .env.example .env
nano .env  # OpenAI API Key 등 설정

# 개발 환경 시작
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 로그 확인
docker-compose logs -f
```

### 2. 스테이징 환경

```bash
# 환경 변수 설정 (스테이징용)
cat > .env.staging << EOF
OPENAI_API_KEY=your_staging_key
DATABASE_URL=postgresql://youtube_user:strong_password@postgres:5432/youtube_agent
REDIS_URL=redis://redis:6379
QDRANT_URL=http://qdrant:6333
EMBEDDING_SERVER_URL=http://embedding-server:8083
NODE_ENV=staging
LOG_LEVEL=debug
EOF

# 스테이징 배포
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up -d
```

### 3. 프로덕션 환경

```bash
# 프로덕션 배포 스크립트 실행
chmod +x deploy-production.sh
./deploy-production.sh

# 또는 수동 배포
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

#### deploy-production.sh
```bash
#!/bin/bash

# 환경 변수 검증
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY not set"
    exit 1
fi

# 이전 백업
docker-compose exec postgres pg_dump -U youtube_user youtube_agent > backup_$(date +%Y%m%d_%H%M%S).sql

# 이미지 업데이트
docker-compose pull

# 롤링 업데이트
docker-compose up -d --no-deps --build agent-service
sleep 10
docker-compose up -d --no-deps --build data-processor
sleep 10
docker-compose up -d --no-deps --build data-collector

# 헬스체크
./scripts/health-check.sh

echo "✅ 프로덕션 배포 완료"
```

## 프로덕션 설정

### 1. 환경 변수 (.env.production)

```bash
# API Keys
OPENAI_API_KEY=sk-prod-xxxxx

# Database (강력한 비밀번호 사용)
DATABASE_URL=postgresql://youtube_user:STRONG_PASSWORD_HERE@postgres:5432/youtube_agent
POSTGRES_PASSWORD=STRONG_PASSWORD_HERE

# Redis (비밀번호 설정)
REDIS_URL=redis://:REDIS_PASSWORD@redis:6379
REDIS_PASSWORD=REDIS_PASSWORD_HERE

# Qdrant (API Key 설정)
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=QDRANT_API_KEY_HERE

# Embedding Server
EMBEDDING_SERVER_URL=http://embedding-server:8083

# Application Settings
NODE_ENV=production
LOG_LEVEL=info
MAX_WORKERS=10
BATCH_SIZE=100

# Security
JWT_SECRET=RANDOM_JWT_SECRET_HERE
ADMIN_PASSWORD=ADMIN_PASSWORD_HERE

# Monitoring
SENTRY_DSN=https://xxx@sentry.io/xxx
PROMETHEUS_ENABLED=true
```

### 2. docker-compose.prod.yml

```yaml
version: '3.8'

services:
  postgres:
    restart: always
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  redis:
    restart: always
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data

  qdrant:
    restart: always
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT_API_KEY: ${QDRANT_API_KEY}

  agent-service:
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '4'
          memory: 8G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  data-processor:
    restart: always
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G

  whisper-server:
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 12G

  embedding-server:
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 8G

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - agent-service
      - admin-dashboard

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  qdrant_data:
    driver: local
```

### 3. Nginx 설정 (nginx.conf)

```nginx
events {
    worker_connections 1024;
}

http {
    upstream agent_backend {
        least_conn;
        server agent-service:8000 max_fails=3 fail_timeout=30s;
    }

    upstream admin_backend {
        server admin-dashboard:8090;
    }

    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # API 엔드포인트
        location /api/ {
            proxy_pass http://agent_backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # 관리자 대시보드
        location /admin/ {
            proxy_pass http://admin_backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            # 기본 인증 추가
            auth_basic "Admin Area";
            auth_basic_user_file /etc/nginx/.htpasswd;
        }

        # 정적 파일
        location /static/ {
            alias /var/www/static/;
            expires 30d;
        }
    }
}
```

## 모니터링 및 운영

### 1. 모니터링 스택 구성

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    ports:
      - "3001:3000"

  node-exporter:
    image: prom/node-exporter
    ports:
      - "9100:9100"

volumes:
  prometheus_data:
  grafana_data:
```

### 2. 로그 관리

```bash
# 중앙 로그 수집 (ELK Stack)
docker-compose -f docker-compose.yml -f docker-compose.elk.yml up -d

# 로그 로테이션 설정
cat > /etc/logrotate.d/youtube-agent << EOF
/var/log/youtube-agent/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
EOF
```

### 3. 백업 전략

```bash
# 자동 백업 스크립트 (crontab에 추가)
#!/bin/bash

BACKUP_DIR="/backup/youtube-agent"
DATE=$(date +%Y%m%d_%H%M%S)

# PostgreSQL 백업
docker-compose exec -T postgres pg_dump -U youtube_user youtube_agent > $BACKUP_DIR/postgres_$DATE.sql

# Qdrant 백업
docker-compose exec -T qdrant curl -X POST http://localhost:6333/collections/youtube_content/snapshots

# Redis 백업
docker-compose exec -T redis redis-cli BGSAVE

# S3 업로드 (선택사항)
aws s3 sync $BACKUP_DIR s3://your-bucket/backups/

# 오래된 백업 삭제 (30일 이상)
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete
```

### 4. 성능 튜닝

```bash
# PostgreSQL 튜닝
docker exec youtube_postgres psql -U youtube_user -c "
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET work_mem = '16MB';
"

# Redis 튜닝
docker exec youtube_redis redis-cli CONFIG SET maxmemory 4gb
docker exec youtube_redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Docker 리소스 제한
docker update --cpus="4" --memory="8g" youtube_agent_service
```

## 문제 해결

### 일반적인 문제 및 해결 방법

#### 1. 메모리 부족
```bash
# 메모리 사용량 확인
docker stats

# 불필요한 이미지/컨테이너 정리
docker system prune -a

# 스왑 메모리 추가
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### 2. GPU 인식 실패
```bash
# NVIDIA 드라이버 확인
nvidia-smi

# Docker GPU 지원 확인
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# 컨테이너 재시작
docker-compose restart whisper-server embedding-server
```

#### 3. 데이터베이스 연결 실패
```bash
# PostgreSQL 상태 확인
docker-compose exec postgres pg_isready

# 연결 테스트
docker-compose exec postgres psql -U youtube_user -d youtube_agent -c "SELECT 1"

# 연결 수 증가
docker exec youtube_postgres psql -U youtube_user -c "ALTER SYSTEM SET max_connections = 200"
```

#### 4. 처리 속도 저하
```bash
# 병목 지점 확인
docker-compose exec data-processor python -m cProfile -o profile.stats app.py

# 워커 수 증가
docker-compose scale data-processor=5

# 인덱스 최적화
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_content_created_at ON content(created_at);
"
```

### 긴급 복구 절차

```bash
# 1. 서비스 중단
docker-compose stop

# 2. 백업에서 복원
docker-compose exec postgres psql -U youtube_user youtube_agent < backup_latest.sql

# 3. 데이터 무결성 확인
make check-data

# 4. 서비스 재시작
docker-compose start

# 5. 헬스체크
make test-health
```

## 보안 체크리스트

- [ ] 모든 환경 변수가 .env 파일에 안전하게 저장됨
- [ ] 강력한 비밀번호 사용 (최소 16자, 특수문자 포함)
- [ ] HTTPS 설정 완료
- [ ] 방화벽 규칙 설정 (필요한 포트만 개방)
- [ ] 정기적인 보안 업데이트
- [ ] 백업 암호화
- [ ] 액세스 로그 모니터링
- [ ] Rate limiting 설정
- [ ] SQL injection 방지
- [ ] CORS 설정 확인

## 배포 후 체크리스트

- [ ] 모든 서비스 정상 작동 확인
- [ ] 데이터베이스 연결 테스트
- [ ] API 엔드포인트 응답 확인
- [ ] GPU 서버 헬스체크
- [ ] 로그 수집 확인
- [ ] 모니터링 대시보드 설정
- [ ] 백업 자동화 확인
- [ ] 알림 설정 (Slack, Email 등)
- [ ] 성능 베이스라인 측정
- [ ] 문서 업데이트

---
**작성일**: 2025-09-19
**버전**: 1.2.0