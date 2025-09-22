#!/bin/bash
#
# 모델 사전 다운로드 스크립트
# Docker 컨테이너에서 사용할 모델을 미리 다운로드합니다.
# 컨테이너 시작 시간을 크게 단축시킵니다.
#

set -e  # 에러 발생 시 스크립트 중단

echo "📦 AI 모델 다운로드 매니저"
echo "================================"
echo ""

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 디렉토리 생성
MODELS_DIR="models"
WHISPER_DIR="$MODELS_DIR/whisper"
EMBEDDINGS_DIR="$MODELS_DIR/torch/sentence_transformers"

mkdir -p "$WHISPER_DIR"
mkdir -p "$EMBEDDINGS_DIR"

# GPU 확인
HAS_GPU=false
GPU_MEMORY=0
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi &> /dev/null; then
        GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
        echo -e "${GREEN}✅ GPU 감지됨 (${GPU_MEMORY}MB)${NC}"
        HAS_GPU=true
    fi
fi

# Whisper 모델 URL
declare -A WHISPER_MODELS=(
    ["tiny"]="https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt"
    ["base"]="https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5628b9654882c91e7c029681a7e08018e3c61/base.pt"
    ["small"]="https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt"
    ["medium"]="https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt"
    ["large"]="https://openaipublic.azureedge.net/main/whisper/models/81f7c96c852ee8fc832187b0132e569d6c3065a3252ed18e56effd0b6884abef/large-v2.pt"
    ["large-v2"]="https://openaipublic.azureedge.net/main/whisper/models/81f7c96c852ee8fc832187b0132e569d6c3065a3252ed18e56effd0b6884abef/large-v2.pt"
    ["large-v3"]="https://openaipublic.azureedge.net/main/whisper/models/e4f3b22d006720c8137ad27b182a9134fb9e1c4b2ca1c67b1ad76ad4bbeb97e8/large-v3.pt"
)

# 모델 크기 정보 (MB)
declare -A MODEL_SIZES=(
    ["whisper-tiny"]="39"
    ["whisper-base"]="74"
    ["whisper-small"]="244"
    ["whisper-medium"]="769"
    ["whisper-large"]="1550"
    ["bge-m3"]="2200"
)

# ========================
# 함수 정의
# ========================

download_file() {
    local url=$1
    local output=$2
    local name=$3

    if [ -f "$output" ]; then
        echo -e "${GREEN}✅ ${name} 이미 존재${NC}"
        return 0
    fi

    echo -e "${BLUE}📥 ${name} 다운로드 중...${NC}"

    # wget 또는 curl 사용
    if command -v wget &> /dev/null; then
        wget --progress=bar:force -O "$output" "$url"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "$output" "$url"
    else
        echo -e "${RED}❌ wget 또는 curl이 필요합니다${NC}"
        return 1
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ${name} 다운로드 완료${NC}"
        return 0
    else
        echo -e "${RED}❌ ${name} 다운로드 실패${NC}"
        rm -f "$output"
        return 1
    fi
}

download_whisper_model() {
    local model=$1
    local url=${WHISPER_MODELS[$model]}
    local file="$WHISPER_DIR/${model}.pt"

    download_file "$url" "$file" "Whisper $model"
}

download_bge_m3() {
    echo -e "${BLUE}📥 BGE-M3 임베딩 모델 다운로드 준비...${NC}"

    # Hugging Face 모델 다운로드를 위한 Python 스크립트
    cat > /tmp/download_bge_m3.py << 'EOF'
#!/usr/bin/env python3
import os
import sys
from sentence_transformers import SentenceTransformer

model_cache_dir = sys.argv[1] if len(sys.argv) > 1 else "models/torch/sentence_transformers"
os.makedirs(model_cache_dir, exist_ok=True)

print("BGE-M3 모델 다운로드 중... (약 2.2GB)")
try:
    model = SentenceTransformer('BAAI/bge-m3', cache_folder=model_cache_dir)
    print("✅ BGE-M3 모델 다운로드 완료")

    # 간단한 테스트
    test_embedding = model.encode("테스트 문장")
    print(f"✅ BGE-M3 모델 검증 완료 (차원: {len(test_embedding)})")
except Exception as e:
    print(f"❌ BGE-M3 다운로드 실패: {e}")
    sys.exit(1)
EOF

    # Python 환경 확인
    if command -v python3 &> /dev/null; then
        # sentence-transformers 설치 확인
        if python3 -c "import sentence_transformers" 2>/dev/null; then
            python3 /tmp/download_bge_m3.py "$EMBEDDINGS_DIR"
        else
            echo -e "${YELLOW}⚠️ sentence-transformers가 설치되지 않았습니다.${NC}"
            echo "설치하려면 다음 명령을 실행하세요:"
            echo "pip install sentence-transformers"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ Python3가 설치되지 않았습니다.${NC}"
        echo "BGE-M3는 컨테이너 시작 시 자동으로 다운로드됩니다."
        return 1
    fi

    rm -f /tmp/download_bge_m3.py
}

show_disk_usage() {
    echo ""
    echo "💾 디스크 사용량:"
    echo "----------------"

    if [ -d "$WHISPER_DIR" ] && [ "$(ls -A $WHISPER_DIR 2>/dev/null)" ]; then
        echo -e "${BLUE}Whisper 모델:${NC}"
        du -sh $WHISPER_DIR/*.pt 2>/dev/null | sed 's/^/   /'
    fi

    if [ -d "$EMBEDDINGS_DIR" ] && [ "$(ls -A $EMBEDDINGS_DIR 2>/dev/null)" ]; then
        echo -e "${BLUE}임베딩 모델:${NC}"
        du -sh $EMBEDDINGS_DIR/* 2>/dev/null | head -5 | sed 's/^/   /'
    fi

    echo ""
    echo -e "${GREEN}총 사용량:${NC}"
    du -sh $MODELS_DIR 2>/dev/null || echo "   계산 불가"
}

# ========================
# 메인 메뉴
# ========================

echo "시스템 정보:"
echo "------------"
if [ "$HAS_GPU" = true ]; then
    echo -e "GPU: ${GREEN}사용 가능${NC} (${GPU_MEMORY}MB)"
    echo -e "권장: Whisper large + BGE-M3"
else
    echo -e "GPU: ${YELLOW}사용 불가${NC}"
    echo -e "권장: Whisper base (CPU 모드)"
fi

echo ""
echo "다운로드 옵션:"
echo "=============="
echo ""
echo "📝 Whisper (음성인식) 모델:"
echo "   1. tiny (39MB) - 테스트용"
echo "   2. base (74MB) - CPU 환경"
echo "   3. medium (769MB) - 중간 성능"
echo "   4. large (1.5GB) - GPU 권장 ⭐"
echo "   5. large-v3 (1.5GB) - 최신 버전"
echo ""
echo "🔤 임베딩 모델:"
echo "   6. BGE-M3 (2.2GB) - GPU 권장 ⭐"
echo ""
echo "🚀 자동 설정:"
echo "   7. GPU 최적 설정 (large + BGE-M3)"
echo "   8. CPU 최적 설정 (base 모델만)"
echo "   9. 전체 다운로드 (모든 모델)"
echo ""
echo "   0. 종료"
echo ""

# 여러 선택 가능
echo -e "${YELLOW}여러 옵션을 선택하려면 쉼표로 구분하세요 (예: 4,6)${NC}"
read -p "선택: " choices

# 쉼표로 구분된 선택 처리
IFS=',' read -ra CHOICES <<< "$choices"

for choice in "${CHOICES[@]}"; do
    choice=$(echo "$choice" | xargs)  # 공백 제거

    case $choice in
        1) download_whisper_model "tiny" ;;
        2) download_whisper_model "base" ;;
        3) download_whisper_model "medium" ;;
        4) download_whisper_model "large" ;;
        5) download_whisper_model "large-v3" ;;
        6) download_bge_m3 ;;
        7) # GPU 최적 설정
            if [ "$HAS_GPU" = true ]; then
                download_whisper_model "large"
                download_bge_m3
            else
                echo -e "${RED}❌ GPU가 감지되지 않았습니다${NC}"
            fi
            ;;
        8) # CPU 최적 설정
            download_whisper_model "base"
            echo -e "${YELLOW}ℹ️ CPU 환경에서는 OpenAI API 사용을 권장합니다${NC}"
            ;;
        9) # 전체 다운로드
            download_whisper_model "base"
            download_whisper_model "medium"
            download_whisper_model "large"
            download_bge_m3
            ;;
        0)
            echo "종료합니다."
            exit 0
            ;;
        *)
            echo -e "${RED}잘못된 선택: $choice${NC}"
            ;;
    esac
done

# ========================
# 완료 및 요약
# ========================

echo ""
echo "================================"
echo -e "${GREEN}✨ 다운로드 완료!${NC}"
echo "================================"

show_disk_usage

echo ""
echo "📌 다음 단계:"
echo "------------"
echo "1. Docker 컨테이너 재시작:"
echo "   docker-compose restart whisper-server embedding-server"
echo ""
echo "2. 또는 전체 서비스 재시작:"
echo "   docker-compose down && docker-compose up -d"
echo ""
echo "💡 팁:"
echo "- 다운로드된 모델은 ${MODELS_DIR}/ 디렉토리에 저장됩니다"
echo "- Docker Compose에서 이 디렉토리를 볼륨 마운트하면 재다운로드가 필요 없습니다"
echo "- whisper-server와 embedding-server가 자동으로 로컬 모델을 감지합니다"
echo ""
echo "🔍 현재 docker-compose.yml 볼륨 설정:"
echo "   ./models:/app/models"