# 문제 해결 가이드 🔧

YouTube Agent 운영 중 발생할 수 있는 일반적인 문제와 해결 방법

## 📋 목차

- [시작 관련 문제](#시작-관련-문제)
- [Docker 관련 문제](#docker-관련-문제)
- [GPU 관련 문제](#gpu-관련-문제)
- [OpenAI API 관련 문제](#openai-api-관련-문제)
- [STT 처리 문제](#stt-처리-문제)
- [데이터베이스 문제](#데이터베이스-문제)
- [네트워크 문제](#네트워크-문제)
- [성능 문제](#성능-문제)

## 시작 관련 문제

### 🔴 문제: `./start.sh: Permission denied`

**해결방법:**
```bash
chmod +x start*.sh scripts/*.sh
```

### 🔴 문제: `.env` 파일 오류

**증상:**
```
export: `#': not a valid identifier
export: `일일': not a valid identifier
```

**원인:** 인라인 주석이 문제를 일으킴

**해결방법:**
```bash
# 잘못된 예
OPENAI_API_KEY=sk-xxx  # API 키

# 올바른 예
# API 키
OPENAI_API_KEY=sk-xxx
```

## Docker 관련 문제

### 🔴 문제: Docker 네트워크 경고

**증상:**
```
WARN[0000] a network with name youtube_network exists but was not created by compose
```

**해결방법:**
```bash
# 자동 해결
./scripts/fix_network.sh

# 또는 수동 해결
docker network rm youtube_network
docker network create youtube_network
```

### 🔴 문제: 고아 컨테이너 경고

**증상:**
```
WARN[0000] Found orphan containers ([youtube_embedding_server youtube_whisper_server]) for this project
```

**원인:** 이전 docker-compose.yml 구성에서 새로운 base/gpu/cpu 분리 구성으로 변경

**해결방법:**
```bash
# 방법 1: --remove-orphans 플래그 사용
docker-compose -f docker-compose.base.yml -f docker-compose.[gpu|cpu].yml down --remove-orphans

# 방법 2: 전체 정리 스크립트 사용
./scripts/cleanup_old_containers.sh
```

### 🔴 문제: 컨테이너가 계속 재시작됨

**진단:**
```bash
docker ps --filter "status=restarting"
docker logs [container_name] --tail 50
```

**일반적인 원인:**
- 데이터베이스 연결 실패
- 필수 환경변수 누락
- 포트 충돌

### 🔴 문제: Docker 빌드 경고

**증상:**
```
WARN: FromAsCasing: 'as' and 'FROM' keywords' casing do not match
```

**해결방법:**
Dockerfile에서 키워드 대소문자 일치:
```dockerfile
# 잘못된 예
FROM python:3.11-slim as builder

# 올바른 예
FROM python:3.11-slim AS builder
```

## GPU 관련 문제

### 🔴 문제: GPU를 인식하지 못함

**진단:**
```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**해결방법:**

1. **NVIDIA 드라이버 설치:**
```bash
# Ubuntu
sudo apt update
sudo apt install nvidia-driver-525

# 재부팅
sudo reboot
```

2. **nvidia-docker 설치:**
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 🔴 문제: VRAM 부족

**증상:**
```
CUDA out of memory
```

**해결방법:**
1. 작은 Whisper 모델 사용 (medium 또는 base)
2. 배치 크기 감소
3. CPU 모드로 전환: `./start_cpu.sh`

## OpenAI API 관련 문제

### 🔴 문제: API 키 인증 실패

**진단:**
```bash
echo $OPENAI_API_KEY
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**해결방법:**
1. `.env` 파일 확인
2. API 키 유효성 확인
3. 환경변수 재로드: `source .env`

### 🔴 문제: API 비용 한도 초과

**증상:**
```
Cost limit exceeded. Approval required.
```

**해결방법:**
1. 비용 관리 대시보드 접속: http://localhost:8084
2. 대기 중인 승인 확인
3. `.env`에서 한도 조정:
```bash
STT_DAILY_COST_LIMIT=20.0
STT_AUTO_APPROVE_THRESHOLD=0.50
```

## STT 처리 문제

### 🔴 문제: STT 워커가 OpenAI API 승인 대기에서 멈춤

**증상:**
```
⏳ 승인 대기 중... (남은 시간: 30분)
```

**원인:**
- Whisper GPU 서버 타임아웃 후 OpenAI API 폴백
- 고아 승인 요청이 Redis에 누적

**해결방법:**
```bash
# 1. 고아 승인 요청 확인
docker exec youtube_redis redis-cli HGETALL "stt:pending_approval"

# 2. 고아 승인 요청 삭제
docker exec youtube_redis redis-cli DEL "stt:pending_approval"

# 3. STT 워커 재시작
for i in 1 2 3; do docker restart youtube_stt_worker_${i}_gpu; done
```

### 🔴 문제: Whisper 서버 타임아웃 (10분 이상 오디오)

**증상:**
```
HTTPConnectionPool(host='whisper-server', port=8082): Read timed out
```

**원인:** 긴 오디오 파일 처리 시 메모리 부족

**해결방법:**
- 이미 자동으로 5분 단위 청킹 처리됨
- 문제 지속 시 Whisper 서버 재시작:
```bash
docker restart youtube_whisper_server
```

### 🔴 문제: GPU 사용률이 낮음 (CPU 처리로 넘어감)

**원인 진단:**
```bash
# GPU 사용률 확인
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv

# Whisper 서버 상태 확인
docker logs youtube_whisper_server --tail 20
```

**해결방법:**
1. Whisper 서버 재시작
2. VRAM 메모리 정리
3. GPU 모드 강제 실행:
```bash
./start_gpu.sh
```

## 데이터베이스 문제

### 🔴 문제: PostgreSQL 연결 실패

**진단:**
```bash
docker exec -it youtube_postgres psql -U youtube_user -d youtube_agent
```

**해결방법:**
```bash
# 데이터베이스 재시작
docker restart youtube_postgres

# 초기화 (데이터 손실 주의!)
docker-compose down -v
docker-compose up -d postgres
```

### 🔴 문제: Qdrant 검색 결과 없음

**진단:**
```bash
curl http://localhost:6333/collections/youtube_content
```

**해결방법:**
1. 벡터화 상태 확인: http://localhost:8081
2. 벡터화 워커 재시작
3. 임계값 조정 (기본 0.55)

## 네트워크 문제

### 🔴 문제: 서비스 간 통신 실패

**진단:**
```bash
# 네트워크 확인
docker network inspect youtube_network

# 컨테이너 간 연결 테스트
docker exec youtube_stt_worker_1 ping whisper-server
```

**해결방법:**
```bash
# 네트워크 재생성
./scripts/fix_network.sh

# 서비스 재시작
docker-compose restart
```

### 🔴 문제: 포트 충돌

**증상:**
```
bind: address already in use
```

**해결방법:**
```bash
# 사용 중인 포트 확인
sudo lsof -i :3000
sudo lsof -i :8000

# 프로세스 종료
sudo kill -9 [PID]

# 또는 포트 변경 (.env)
```

## 데이터 품질 문제

### 🔴 문제: 데이터 정합성 불일치

**증상:**
- PostgreSQL과 Qdrant 데이터 불일치
- 처리 플래그가 실제 상태와 다름
- 고아 데이터 존재

**해결방법:**
```bash
# 자동 정합성 체크 실행
./scripts/manage_quality_services.sh check

# 데이터 품질 대시보드 확인
http://localhost:8090/data-quality

# 수동 정합성 수정
./scripts/fix_data_integrity.sh
```

### 🔴 문제: 비활성 콘텐츠가 계속 처리됨

**원인:** 콘텐츠 비활성화 시 대기열이 정리되지 않음

**해결방법:**
```bash
# 비활성 콘텐츠의 대기 작업 취소
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
UPDATE processing_jobs j
SET status = 'cancelled', error_message = 'Content is inactive'
FROM content c
WHERE j.content_id = c.id
AND c.is_active = FALSE
AND j.status IN ('pending', 'processing');"
```

### 🔴 문제: 중복 벡터/작업 누적

**진단:**
```bash
# 중복 작업 확인
docker exec youtube_postgres psql -U youtube_user -d youtube_agent -c "
SELECT content_id, job_type, COUNT(*)
FROM processing_jobs
WHERE status = 'pending'
GROUP BY content_id, job_type
HAVING COUNT(*) > 1;"
```

**해결방법:**
```bash
# 자동 정리 서비스 실행
./scripts/manage_quality_services.sh start
```

## 성능 문제

### 🔴 문제: 메모리 부족

**진단:**
```bash
docker stats --no-stream
free -h
```

**해결방법:**
1. 워커 수 감소
2. 스왑 메모리 증가
3. 불필요한 서비스 중지

### 🔴 문제: CPU 100% 사용

**원인 확인:**
```bash
top
docker stats
```

**해결방법:**
1. CPU 모드에서 워커 수 조절
2. 처리 배치 크기 감소
3. Rate limiting 적용

## 🆘 긴급 복구

### 전체 시스템 재시작
```bash
# 1. 모든 서비스 중지
docker-compose down

# 2. Docker 시스템 정리
docker system prune -f

# 3. 네트워크 재생성
./scripts/fix_network.sh

# 4. 서비스 재시작
./start.sh
```

### 데이터 백업 및 복구
```bash
# 백업
docker exec youtube_postgres pg_dump -U youtube_user youtube_agent > backup.sql

# 복구
docker exec -i youtube_postgres psql -U youtube_user youtube_agent < backup.sql
```

## 📞 추가 지원

### 로그 수집
```bash
# 전체 로그 수집
docker-compose logs > system_logs.txt

# 특정 서비스 로그
docker logs youtube_stt_worker_1 > stt_worker_logs.txt
```

### 시스템 정보 수집
```bash
./detect_environment.sh > env_info.txt
docker version >> env_info.txt
docker-compose version >> env_info.txt
```

### 도움 요청 시 제공 정보
1. 오류 메시지 전문
2. 실행한 명령어
3. 환경 정보 (GPU/CPU 모드)
4. Docker 로그
5. `.env` 설정 (API 키 제외)

## 🆕 최근 추가된 해결 방법

### GPU/CPU 모드 전환
```bash
# 현재 모드 확인
cat .detected_mode

# GPU → CPU 전환
docker-compose -f docker-compose.base.yml -f docker-compose.gpu.yml down --remove-orphans
./start_cpu.sh

# CPU → GPU 전환
docker-compose -f docker-compose.base.yml -f docker-compose.cpu.yml down --remove-orphans
./start_gpu.sh
```

### 환경 변수 문제 해결
```bash
# .env 파일 검증
# 인라인 주석 제거 필요
sed -i 's/\(.*\)#.*/\1/' .env

# 환경 변수 재로드
set -a
source .env
set +a
```

### 컨테이너 상태 확인
```bash
# 모든 YouTube Agent 컨테이너 상태
docker ps --filter "name=youtube" --format "table {{.Names}}\t{{.Status}}\t{{.State}}"

# 문제가 있는 컨테이너 로그
docker ps --filter "name=youtube" --filter "status=restarting" --format "{{.Names}}" | \
  xargs -I {} docker logs {} --tail 50
```

---

문제가 해결되지 않으면 [GitHub Issues](https://github.com/your-repo/issues)에 문의하세요.