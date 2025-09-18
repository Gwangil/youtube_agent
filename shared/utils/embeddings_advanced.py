"""
고급 하이브리드 임베딩 관리자
한국어 YouTube 콘텐츠에 최적화된 임베딩 모델 선택
"""

import os
import torch
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """임베딩 모델 설정"""
    name: str
    model_id: str
    dimension: int
    max_length: int
    memory_gb: float
    languages: List[str]
    use_mean_pooling: bool = True
    normalize: bool = True


# 모델 설정 정의
MODEL_CONFIGS = {
    "bge-m3": ModelConfig(
        name="BGE-M3",
        model_id="BAAI/bge-m3",
        dimension=1024,
        max_length=8192,
        memory_gb=2.5,
        languages=["multilingual"],
        use_mean_pooling=True,
        normalize=True
    ),
    "multilingual-e5-large": ModelConfig(
        name="Multilingual-E5-Large",
        model_id="intfloat/multilingual-e5-large",
        dimension=1024,
        max_length=512,
        memory_gb=2.2,
        languages=["multilingual"],
        use_mean_pooling=True,
        normalize=True
    ),
    "multilingual-e5-base": ModelConfig(
        name="Multilingual-E5-Base",
        model_id="intfloat/multilingual-e5-base",
        dimension=768,
        max_length=512,
        memory_gb=1.1,
        languages=["multilingual"],
        use_mean_pooling=True,
        normalize=True
    ),
    "ko-sroberta": ModelConfig(
        name="Ko-SRoBERTa-MultiTask",
        model_id="jhgan/ko-sroberta-multitask",
        dimension=768,
        max_length=512,
        memory_gb=1.2,
        languages=["ko"],
        use_mean_pooling=True,
        normalize=True
    ),
    "kosimcse": ModelConfig(
        name="KoSimCSE-RoBERTa",
        model_id="BM-K/KoSimCSE-roberta",
        dimension=768,
        max_length=512,
        memory_gb=1.2,
        languages=["ko"],
        use_mean_pooling=True,
        normalize=True
    ),
    "minilm": ModelConfig(
        name="All-MiniLM-L6-v2",
        model_id="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        max_length=256,
        memory_gb=0.5,
        languages=["en"],
        use_mean_pooling=True,
        normalize=True
    )
}


class AdvancedHybridEmbeddings:
    """
    고급 하이브리드 임베딩 시스템
    - BGE-M3를 기본으로 사용 (최고 성능)
    - 메모리 제약 시 자동 폴백
    - 한국어 콘텐츠 최적화
    """

    def __init__(
        self,
        preferred_model: str = "bge-m3",
        use_gpu: Optional[bool] = None,
        model_cache_dir: str = "/app/models/embeddings",
        fallback_to_api: bool = True
    ):
        self.preferred_model = preferred_model
        self.model_cache_dir = model_cache_dir
        self.fallback_to_api = fallback_to_api

        # GPU 사용 여부 자동 감지
        if use_gpu is None:
            self.use_gpu = torch.cuda.is_available()
        else:
            self.use_gpu = use_gpu and torch.cuda.is_available()

        self.device = "cuda" if self.use_gpu else "cpu"
        self.device_info = self._get_device_info()

        # 모델 초기화
        self.model = None
        self.model_config = None
        self.model_type = None

        self._initialize_model()

    def _get_device_info(self) -> Dict[str, Any]:
        """디바이스 정보 조회"""
        info = {
            "has_cuda": torch.cuda.is_available(),
            "device": self.device,
            "cpu_count": os.cpu_count()
        }

        if info["has_cuda"]:
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_memory_gb"] = torch.cuda.get_device_properties(0).total_memory / 1024**3
            info["gpu_memory_available_gb"] = (
                torch.cuda.get_device_properties(0).total_memory -
                torch.cuda.memory_allocated(0)
            ) / 1024**3

        return info

    def _can_load_model(self, model_config: ModelConfig) -> bool:
        """모델 로드 가능 여부 확인"""
        if self.use_gpu:
            available_memory = self.device_info.get("gpu_memory_available_gb", 0)
            return available_memory >= model_config.memory_gb * 1.2  # 20% 여유
        else:
            # CPU 메모리는 충분하다고 가정
            return True

    def _initialize_model(self):
        """최적 모델 선택 및 초기화"""

        # GPU가 있을 때만 로컬 모델 시도
        if self.use_gpu and torch.cuda.is_available():
            # 1. 선호 모델 시도
            if self.preferred_model in MODEL_CONFIGS:
                model_config = MODEL_CONFIGS[self.preferred_model]
                if self._can_load_model(model_config):
                    try:
                        self._load_sentence_transformer(model_config)
                        return
                    except Exception as e:
                        logger.warning(f"선호 모델 {self.preferred_model} 로드 실패: {e}")

            # 2. 대체 모델 순서 (성능 순)
            fallback_order = ["bge-m3", "multilingual-e5-base", "ko-sroberta", "kosimcse", "minilm"]

            for model_name in fallback_order:
                if model_name == self.preferred_model:
                    continue

                model_config = MODEL_CONFIGS[model_name]
                if self._can_load_model(model_config):
                    try:
                        self._load_sentence_transformer(model_config)
                        logger.info(f"대체 모델 {model_name} 로드 성공")
                        return
                    except Exception as e:
                        logger.warning(f"모델 {model_name} 로드 실패: {e}")

        # 3. OpenAI API 우선 사용 (CPU 환경이거나 GPU 모델 로드 실패 시)
        if self.fallback_to_api:
            try:
                self._init_openai_embeddings()
                return
            except Exception as e:
                logger.warning(f"OpenAI API 초기화 실패: {e}")
                # OpenAI API도 실패하면 CPU 모델 시도 (최후의 수단)
                if not self.use_gpu:
                    try:
                        self._try_cpu_fallback()
                        return
                    except Exception as cpu_error:
                        logger.warning(f"CPU 모델 로드도 실패: {cpu_error}")

        raise RuntimeError("사용 가능한 임베딩 모델이 없습니다")

    def _load_sentence_transformer(self, model_config: ModelConfig):
        """Sentence Transformer 모델 로드"""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"모델 로딩: {model_config.name} ({model_config.model_id})")

            # BGE-M3의 경우 특별 처리
            if "bge-m3" in model_config.model_id.lower():
                self.model = SentenceTransformer(
                    model_config.model_id,
                    device=self.device,
                    cache_folder=self.model_cache_dir
                )
                # BGE-M3는 instruction prefix 필요
                self.instruction_prefix = "Represent this sentence for retrieval: "
            else:
                self.model = SentenceTransformer(
                    model_config.model_id,
                    device=self.device,
                    cache_folder=self.model_cache_dir
                )
                self.instruction_prefix = ""

            self.model_config = model_config
            self.model_type = "local"

            # E5 모델의 경우 query/passage prefix
            if "e5" in model_config.model_id.lower():
                self.query_prefix = "query: "
                self.passage_prefix = "passage: "
            else:
                self.query_prefix = ""
                self.passage_prefix = ""

            logger.info(f"✅ {model_config.name} 모델 로드 완료 (device: {self.device})")

        except ImportError:
            raise ImportError("sentence-transformers 라이브러리가 설치되지 않았습니다")

    def _try_cpu_fallback(self):
        """CPU 모델 폴백 시도 (최후의 수단)"""
        try:
            from sentence_transformers import SentenceTransformer

            # 가장 가벼운 모델 시도
            model_config = MODEL_CONFIGS["minilm"]
            self.model = SentenceTransformer(
                model_config.model_id,
                device="cpu",
                cache_folder=self.model_cache_dir
            )
            self.model_config = model_config
            self.model_type = "local"
            self.instruction_prefix = ""
            self.query_prefix = ""
            self.passage_prefix = ""
            logger.info(f"✅ CPU 폴백 모델 로드 완료: {model_config.name}")
        except Exception as e:
            raise Exception(f"CPU 폴백 모델 로드 실패: {e}")

    def _init_openai_embeddings(self):
        """OpenAI API 임베딩 초기화"""
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")

        self.model = OpenAIEmbeddings(
            openai_api_key=api_key,
            model="text-embedding-3-small"
        )
        self.model_type = "api"
        self.model_config = ModelConfig(
            name="OpenAI-Embedding",
            model_id="text-embedding-3-small",
            dimension=1536,
            max_length=8191,
            memory_gb=0,
            languages=["multilingual"]
        )
        logger.info("✅ OpenAI API 임베딩 초기화 완료")

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """문서 임베딩 (배치 처리)"""
        if self.model_type == "api":
            return self.model.embed_documents(texts)

        # 로컬 모델 사용
        embeddings = []

        # Prefix 추가
        if self.passage_prefix:
            texts = [self.passage_prefix + text for text in texts]
        elif self.instruction_prefix:
            texts = [self.instruction_prefix + text for text in texts]

        # 배치 처리
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]

            if self.use_gpu:
                with torch.no_grad():
                    batch_embeddings = self.model.encode(
                        batch,
                        convert_to_numpy=True,
                        normalize_embeddings=self.model_config.normalize,
                        show_progress_bar=False
                    )
            else:
                batch_embeddings = self.model.encode(
                    batch,
                    convert_to_numpy=True,
                    normalize_embeddings=self.model_config.normalize,
                    show_progress_bar=False
                )

            embeddings.extend(batch_embeddings.tolist())

        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """쿼리 임베딩"""
        if self.model_type == "api":
            return self.model.embed_query(text)

        # Prefix 추가
        if self.query_prefix:
            text = self.query_prefix + text
        elif self.instruction_prefix:
            text = self.instruction_prefix + text

        # 단일 텍스트 임베딩
        if self.use_gpu:
            with torch.no_grad():
                embedding = self.model.encode(
                    text,
                    convert_to_numpy=True,
                    normalize_embeddings=self.model_config.normalize,
                    show_progress_bar=False
                )
        else:
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=self.model_config.normalize,
                show_progress_bar=False
            )

        return embedding.tolist()

    def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 반환"""
        return {
            "model_name": self.model_config.name,
            "model_id": self.model_config.model_id,
            "dimension": self.model_config.dimension,
            "max_length": self.model_config.max_length,
            "languages": self.model_config.languages,
            "device": self.device,
            "model_type": self.model_type,
            "device_info": self.device_info
        }

    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """두 임베딩 간 코사인 유사도 계산"""
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        cosine_sim = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        return float(cosine_sim)


# 전역 싱글톤 인스턴스
_advanced_embeddings = None


def get_advanced_embeddings(
    preferred_model: str = "bge-m3",
    force_reload: bool = False
) -> AdvancedHybridEmbeddings:
    """고급 임베딩 인스턴스 반환"""
    global _advanced_embeddings

    if _advanced_embeddings is None or force_reload:
        _advanced_embeddings = AdvancedHybridEmbeddings(preferred_model=preferred_model)

    return _advanced_embeddings