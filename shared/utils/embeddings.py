"""
하이브리드 임베딩 관리자
GPU/CPU 환경에 따라 로컬 또는 OpenAI API 자동 선택
"""

import os
import torch
import logging
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)


class HybridEmbeddings:
    """
    인프라 기반 자동 임베딩 모델 선택
    GPU 사용 가능 시 로컬 모델, 그렇지 않으면 OpenAI API
    """

    def __init__(self, prefer_local: bool = True, model_cache_dir: str = "/app/models"):
        self.prefer_local = prefer_local
        self.model_cache_dir = model_cache_dir
        self.device_info = self._get_device_info()
        self.embedding_model = None
        self.model_type = None

        # 모델 초기화
        self._initialize_model()

    def _get_device_info(self) -> dict:
        """디바이스 정보 조회"""
        info = {
            "has_cuda": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "cpu_count": os.cpu_count(),
            "device": "cuda" if torch.cuda.is_available() else "cpu"
        }

        if info["has_cuda"]:
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_memory_gb"] = torch.cuda.get_device_properties(0).total_memory / 1024**3

        return info

    def _initialize_model(self):
        """환경에 따른 최적 모델 선택 및 초기화"""

        # 1. GPU 사용 가능 시 BGE-M3 모델 우선 사용
        if self.device_info["has_cuda"]:
            try:
                self._init_bge_m3_gpu()
                logger.info("🚀 BGE-M3 GPU 모델 사용 - 로컬 처리로 빠르고 안전합니다")
                return
            except Exception as e:
                logger.warning(f"GPU BGE-M3 모델 초기화 실패, OpenAI API로 폴백: {e}")

        # 2. BGE-M3 실패 시 OpenAI API 사용 (폴백)
        try:
            self._init_openai_model()
            logger.info("📡 OpenAI API 사용 중 (BGE-M3 사용 불가)")
            return
        except Exception as e:
            logger.warning(f"OpenAI API 초기화도 실패: {e}")

        # 3. 최후의 수단으로 CPU 로컬 모델 (권장하지 않음)
        if self.device_info["cpu_count"] >= 4:
            try:
                self._init_local_model_cpu()
                logger.warning("⚠️ CPU 로컬 모델 사용 중 - 성능이 저하될 수 있습니다")
                return
            except Exception as e:
                logger.error(f"CPU 로컬 모델 초기화도 실패: {e}")

        raise Exception("임베딩 모델을 초기화할 수 없습니다")

    def _init_bge_m3_gpu(self):
        """BGE-M3 모델 전용 GPU 초기화 (1024차원)"""
        try:
            from sentence_transformers import SentenceTransformer

            model_name = "BAAI/bge-m3"
            logger.info(f"BGE-M3 모델 로딩 중 (1024차원)...")

            self.embedding_model = SentenceTransformer(
                model_name,
                device='cuda',
                cache_folder=self.model_cache_dir
            )
            self.model_type = "bge_m3_gpu"
            self.model_name = model_name
            self.dimension = 1024  # BGE-M3는 1024차원
            logger.info(f"✅ BGE-M3 GPU 모델 초기화 완료 (1024차원)")

        except ImportError:
            raise Exception("sentence-transformers 라이브러리가 설치되지 않았습니다")
        except Exception as e:
            raise Exception(f"BGE-M3 모델 로딩 실패: {e}")

    def _init_local_model_gpu(self):
        """GPU용 로컬 임베딩 모델 초기화"""
        try:
            from sentence_transformers import SentenceTransformer

            # GPU 메모리에 따른 모델 선택
            if self.device_info.get("gpu_memory_gb", 0) >= 3:
                # BGE-M3: 최고 성능 다국어 모델
                model_name = "BAAI/bge-m3"
            elif self.device_info.get("gpu_memory_gb", 0) >= 2:
                # 한국어 특화 모델
                model_name = "jhgan/ko-sroberta-multitask"
            else:
                # 경량 다국어 모델
                model_name = "intfloat/multilingual-e5-base"

            logger.info(f"GPU 로컬 모델 로딩: {model_name}")
            self.embedding_model = SentenceTransformer(
                model_name,
                device='cuda',
                cache_folder=self.model_cache_dir
            )
            self.model_type = "local_gpu"
            self.model_name = model_name
            logger.info(f"✅ GPU 로컬 임베딩 모델 초기화 완료: {model_name}")

        except ImportError:
            raise Exception("sentence-transformers 라이브러리가 설치되지 않았습니다")

    def _init_local_model_cpu(self):
        """CPU용 경량 로컬 임베딩 모델 초기화"""
        try:
            from sentence_transformers import SentenceTransformer

            # CPU용 경량 한국어 모델
            # CPU 코어 수에 따라 모델 선택
            if self.device_info["cpu_count"] >= 8:
                model_name = "jhgan/ko-sroberta-multitask"  # 한국어 특화
            else:
                model_name = "intfloat/multilingual-e5-base"  # 경량 다국어

            logger.info(f"CPU 로컬 모델 로딩: {model_name}")
            self.embedding_model = SentenceTransformer(
                model_name,
                device='cpu',
                cache_folder=self.model_cache_dir
            )
            self.model_type = "local_cpu"
            self.model_name = model_name
            logger.info(f"✅ CPU 로컬 임베딩 모델 초기화 완료: {model_name}")

        except ImportError:
            raise Exception("sentence-transformers 라이브러리가 설치되지 않았습니다")

    def _init_openai_model(self):
        """OpenAI API 임베딩 모델 초기화 (1024차원으로 통일)"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")

        # text-embedding-3-large를 1024차원으로 설정 (BGE-M3와 동일)
        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=api_key,
            model="text-embedding-3-large",
            dimensions=1024  # BGE-M3와 동일한 차원 설정
        )
        self.model_type = "openai_api"
        self.model_name = "text-embedding-3-large-1024"
        self.dimension = 1024  # 명시적으로 차원 설정
        logger.info("✅ OpenAI API 임베딩 모델 초기화 완료 (1024차원)")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """여러 문서 임베딩 (배치 처리)"""
        if self.model_type in ["bge_m3_gpu", "local_gpu", "local_cpu"]:
            # 로컬 모델 사용
            embeddings = self.embedding_model.encode(
                texts,
                batch_size=32 if "gpu" in self.model_type else 8,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return embeddings.tolist()
        else:
            # OpenAI API 사용
            return self.embedding_model.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """단일 쿼리 임베딩"""
        if self.model_type in ["bge_m3_gpu", "local_gpu", "local_cpu"]:
            # 로컬 모델 사용
            embedding = self.embedding_model.encode(
                text,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return embedding.tolist()
        else:
            # OpenAI API 사용
            return self.embedding_model.embed_query(text)

    def get_model_info(self) -> dict:
        """현재 사용 중인 모델 정보 반환"""
        return {
            "model_type": self.model_type,
            "model_name": self.model_name,
            "dimension": getattr(self, 'dimension', 1024),  # 기본 1024차원
            "device": self.device_info["device"],
            "device_info": self.device_info
        }

    def benchmark(self, test_texts: List[str] = None) -> dict:
        """임베딩 성능 벤치마크"""
        import time

        if test_texts is None:
            test_texts = [
                "이것은 테스트 문장입니다.",
                "The quick brown fox jumps over the lazy dog.",
                "한국어와 영어를 모두 포함한 문장입니다."
            ] * 10

        start_time = time.time()
        embeddings = self.embed_documents(test_texts)
        elapsed_time = time.time() - start_time

        return {
            "model_type": self.model_type,
            "model_name": self.model_name,
            "num_texts": len(test_texts),
            "total_time": elapsed_time,
            "avg_time_per_text": elapsed_time / len(test_texts),
            "embedding_dim": len(embeddings[0]) if embeddings else 0
        }


# 전역 싱글톤 인스턴스
_hybrid_embeddings = None


def get_embeddings(force_reload: bool = False) -> HybridEmbeddings:
    """싱글톤 임베딩 인스턴스 반환"""
    global _hybrid_embeddings

    if _hybrid_embeddings is None or force_reload:
        _hybrid_embeddings = HybridEmbeddings()

    return _hybrid_embeddings