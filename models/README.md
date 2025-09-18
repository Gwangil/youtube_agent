# 모델 파일 관리

이 디렉토리는 Whisper와 임베딩 모델 파일을 저장합니다.

## ⚠️ 중요 사항

**Docker 컨테이너는 GPU/CPU를 자동 감지하여 작동합니다:**
- **GPU 환경**: 로컬 모델 자동 다운로드 및 사용
- **CPU 환경**: OpenAI API 자동 사용

**로컬 개발(WSL2) 환경에서만 수동 다운로드가 필요합니다.**

## 디렉토리 구조

```
models/
├── whisper/        # Whisper STT 모델
│   ├── base.pt     # 기본 모델 (~140MB)
│   ├── medium.pt   # 중간 모델 (~1.5GB)
│   └── large.pt    # 대형 모델 (~3GB)
└── embeddings/     # 문장 임베딩 모델
    ├── BAAI/       # BGE-M3 모델
    ├── intfloat/   # Multilingual-E5 모델
    └── jhgan/      # Ko-SRoBERTa 모델
```

## 모델 다운로드

### 방법 1: 자동 다운로드 스크립트 사용 (권장)

```bash
# 가상환경 활성화
source .venv/bin/activate

# 모델 다운로드
python download_models.py
```

옵션 선택:
- 1: 전체 모델 다운로드
- 2: Whisper 모델만
- 3: 임베딩 모델만

### 방법 2: 수동 다운로드

#### Whisper 모델
```python
import whisper
# base 모델
model = whisper.load_model("base", download_root="models/whisper")
# medium 모델
model = whisper.load_model("medium", download_root="models/whisper")
# large 모델 (GPU 권장)
model = whisper.load_model("large", download_root="models/whisper")
```

#### 임베딩 모델
```python
from sentence_transformers import SentenceTransformer

# BGE-M3 (최고 성능)
model = SentenceTransformer("BAAI/bge-m3", cache_folder="models/embeddings")

# Multilingual-E5-Base (경량)
model = SentenceTransformer("intfloat/multilingual-e5-base", cache_folder="models/embeddings")

# Ko-SRoBERTa (한국어 특화)
model = SentenceTransformer("jhgan/ko-sroberta-multitask", cache_folder="models/embeddings")
```

## Docker 이미지에 포함

모델을 다운로드한 후 Docker 이미지를 빌드하면 자동으로 포함됩니다:

```bash
# 모델 다운로드 먼저 실행
python download_models.py

# Docker 이미지 빌드
docker-compose build

# 또는 특정 서비스만
docker-compose build whisper-server data-processor
```

## 모델 크기 및 요구사항

### Whisper 모델
| 모델 | 크기 | VRAM 요구량 | 추천 환경 |
|------|------|------------|----------|
| base | ~140MB | ~1GB | CPU/GPU |
| medium | ~1.5GB | ~2GB | GPU |
| large | ~3GB | ~4GB | GPU |

### 임베딩 모델
| 모델 | 크기 | 차원 | 특징 |
|------|------|-----|------|
| BGE-M3 | ~2GB | 1024 | 최고 성능, 다국어 |
| Multilingual-E5-Base | ~1GB | 768 | 균형, 다국어 |
| Ko-SRoBERTa | ~1GB | 768 | 한국어 특화 |

## 주의사항

1. **Git에 포함되지 않음**: 모델 파일은 `.gitignore`에 포함되어 있어 Git에 커밋되지 않습니다.

2. **디스크 공간**: 전체 모델 다운로드 시 약 8-10GB의 디스크 공간이 필요합니다.

3. **초기 설정**: 프로젝트를 처음 클론한 후 반드시 모델을 다운로드해야 합니다.

4. **Docker 빌드 시간**: 모델이 포함된 이미지는 빌드 시간이 길어질 수 있습니다.

## 문제 해결

### 모델 로딩 실패
```bash
# 모델 파일 확인
ls -la models/whisper/
ls -la models/embeddings/

# 권한 문제 해결
chmod -R 755 models/
```

### 메모리 부족
- GPU 메모리 부족 시 더 작은 모델 사용
- CPU 모드로 전환

### 네트워크 문제
- 방화벽/프록시 설정 확인
- Hugging Face 미러 사이트 사용 고려