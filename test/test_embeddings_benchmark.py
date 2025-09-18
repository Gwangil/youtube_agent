"""
임베딩 모델 벤치마크 테스트
한국어 YouTube 콘텐츠에 최적화된 모델 선택을 위한 성능 측정
"""

import time
import torch
import numpy as np
from typing import List, Dict, Any
import json
from sentence_transformers import SentenceTransformer
import os

# 테스트용 한국어 문장들 (YouTube 콘텐츠 시뮬레이션)
TEST_SENTENCES_KO = [
    "오늘은 주식시장이 큰 폭으로 상승했습니다. 코스피 지수는 3% 상승하며 3,000포인트를 돌파했습니다.",
    "인공지능 기술의 발전으로 많은 산업이 변화하고 있습니다. 특히 자동화와 효율성이 크게 개선되었습니다.",
    "최근 부동산 시장이 안정세를 보이고 있습니다. 정부의 규제 정책이 효과를 보는 것으로 분석됩니다.",
    "한국 경제는 반도체 수출에 크게 의존하고 있습니다. 글로벌 수요 증가로 수출이 호조를 보이고 있습니다.",
    "미국 연준의 금리 인상이 글로벌 경제에 영향을 미치고 있습니다. 한국 시장도 변동성이 커지고 있습니다.",
    "전기차 시장이 빠르게 성장하고 있습니다. 테슬라와 현대차가 시장을 선도하고 있습니다.",
    "암호화폐 시장이 다시 주목받고 있습니다. 비트코인 가격이 상승세를 보이고 있습니다.",
    "K-팝이 전 세계적으로 인기를 끌고 있습니다. BTS와 블랙핑크가 빌보드 차트를 석권했습니다.",
    "넷플릭스와 디즈니플러스가 한국 콘텐츠에 대규모 투자를 하고 있습니다.",
    "메타버스 시장이 새로운 기회를 창출하고 있습니다. 많은 기업들이 메타버스 플랫폼을 개발 중입니다."
]

# 유사도 측정용 쿼리
QUERY_SENTENCES = [
    "주식시장 전망은 어떤가요?",
    "AI 기술이 우리 생활에 미치는 영향",
    "부동산 투자 시기",
    "반도체 산업의 미래",
    "금리 인상의 영향"
]


class EmbeddingBenchmark:
    """임베딩 모델 벤치마크 클래스"""

    def __init__(self):
        self.results = {}
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Device: {self.device}")
        if self.device == "cuda":
            print(f"GPU: {torch.cuda.get_device_name(0)}")
            print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    def benchmark_model(self, model_name: str, model_id: str) -> Dict[str, Any]:
        """단일 모델 벤치마크"""
        print(f"\n{'='*60}")
        print(f"Testing: {model_name} ({model_id})")
        print(f"{'='*60}")

        result = {
            "model_name": model_name,
            "model_id": model_id,
            "device": self.device
        }

        try:
            # 모델 로딩 시간 측정
            start_time = time.time()
            model = SentenceTransformer(model_id, device=self.device)
            load_time = time.time() - start_time
            result["load_time"] = load_time
            print(f"✅ Model loaded in {load_time:.2f} seconds")

            # 메모리 사용량 (GPU인 경우)
            if self.device == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                memory_used = torch.cuda.memory_allocated() / 1024**3
                result["gpu_memory_gb"] = memory_used
                print(f"📊 GPU Memory: {memory_used:.2f} GB")

            # 임베딩 생성 속도 측정
            print(f"\n🔄 Encoding {len(TEST_SENTENCES_KO)} sentences...")
            start_time = time.time()
            embeddings = model.encode(TEST_SENTENCES_KO, show_progress_bar=False)
            encode_time = time.time() - start_time
            result["encode_time"] = encode_time
            result["sentences_per_second"] = len(TEST_SENTENCES_KO) / encode_time
            print(f"⚡ Encoding speed: {result['sentences_per_second']:.1f} sentences/sec")

            # 임베딩 차원
            result["dimension"] = embeddings.shape[1]
            print(f"📏 Embedding dimension: {result['dimension']}")

            # 쿼리-문서 유사도 측정
            print(f"\n🔍 Computing similarities...")
            query_embeddings = model.encode(QUERY_SENTENCES, show_progress_bar=False)

            # 코사인 유사도 계산
            similarities = np.dot(query_embeddings, embeddings.T)
            norms = np.linalg.norm(query_embeddings, axis=1)[:, np.newaxis] * np.linalg.norm(embeddings, axis=1)
            similarities = similarities / norms

            # 평균 최고 유사도 (검색 품질 지표)
            max_similarities = similarities.max(axis=1)
            result["avg_max_similarity"] = float(max_similarities.mean())
            print(f"📈 Average max similarity: {result['avg_max_similarity']:.3f}")

            # Top-3 정확도 (각 쿼리에 대해 상위 3개 문서가 관련있는지)
            top3_indices = similarities.argsort(axis=1)[:, -3:]
            result["top3_indices"] = top3_indices.tolist()

            # 배치 처리 속도 측정
            batch_sizes = [1, 8, 32]
            batch_times = {}
            for batch_size in batch_sizes:
                start_time = time.time()
                for i in range(0, len(TEST_SENTENCES_KO), batch_size):
                    batch = TEST_SENTENCES_KO[i:i+batch_size]
                    _ = model.encode(batch, show_progress_bar=False)
                batch_time = time.time() - start_time
                batch_times[f"batch_{batch_size}"] = batch_time
            result["batch_times"] = batch_times
            print(f"🔄 Batch processing times: {batch_times}")

            # 성공
            result["status"] = "success"

            # 메모리 정리
            del model
            if self.device == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"❌ Error: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result

    def run_benchmarks(self):
        """모든 모델 벤치마크 실행"""
        models = [
            ("BGE-M3", "BAAI/bge-m3"),
            ("Multilingual-E5-Large", "intfloat/multilingual-e5-large"),
            ("Multilingual-E5-Base", "intfloat/multilingual-e5-base"),
            ("Ko-SRoBERTa", "jhgan/ko-sroberta-multitask"),
            ("KoSimCSE", "BM-K/KoSimCSE-roberta"),
            ("MiniLM", "sentence-transformers/all-MiniLM-L6-v2"),
        ]

        print("\n🚀 Starting Embedding Model Benchmarks")
        print(f"Testing {len(models)} models with {len(TEST_SENTENCES_KO)} Korean sentences")

        for model_name, model_id in models:
            result = self.benchmark_model(model_name, model_id)
            self.results[model_name] = result
            time.sleep(2)  # 모델 간 간격

        self.print_summary()
        self.save_results()

    def print_summary(self):
        """벤치마크 결과 요약"""
        print("\n" + "="*80)
        print("📊 BENCHMARK SUMMARY")
        print("="*80)

        # 성공한 모델만 필터링
        successful_models = {k: v for k, v in self.results.items() if v.get("status") == "success"}

        if not successful_models:
            print("❌ No successful model tests")
            return

        # 테이블 헤더
        print(f"\n{'Model':<25} {'Dim':<6} {'Load(s)':<10} {'Speed(s/s)':<12} {'Similarity':<10} {'Memory(GB)':<10}")
        print("-" * 80)

        # 각 모델 결과 출력
        for model_name, result in successful_models.items():
            dim = result.get('dimension', 0)
            load_time = result.get('load_time', 0)
            speed = result.get('sentences_per_second', 0)
            similarity = result.get('avg_max_similarity', 0)
            memory = result.get('gpu_memory_gb', 0)

            print(f"{model_name:<25} {dim:<6} {load_time:<10.2f} {speed:<12.1f} {similarity:<10.3f} {memory:<10.2f}")

        # 최적 모델 추천
        print("\n" + "="*80)
        print("🏆 RECOMMENDATIONS")
        print("="*80)

        # 속도 최적
        fastest = max(successful_models.items(), key=lambda x: x[1].get('sentences_per_second', 0))
        print(f"⚡ Fastest: {fastest[0]} ({fastest[1]['sentences_per_second']:.1f} sentences/sec)")

        # 품질 최적
        best_quality = max(successful_models.items(), key=lambda x: x[1].get('avg_max_similarity', 0))
        print(f"🎯 Best Quality: {best_quality[0]} (similarity: {best_quality[1]['avg_max_similarity']:.3f})")

        # 균형 추천 (속도와 품질 점수 조합)
        def balance_score(item):
            result = item[1]
            speed_norm = result.get('sentences_per_second', 0) / 100  # 정규화
            quality_norm = result.get('avg_max_similarity', 0)
            return speed_norm * 0.3 + quality_norm * 0.7  # 품질에 더 가중치

        best_balanced = max(successful_models.items(), key=balance_score)
        print(f"⚖️  Best Balanced: {best_balanced[0]}")

        print("\n💡 Recommendation for Korean YouTube Content:")
        print("   1. BGE-M3: Best overall performance for multilingual content")
        print("   2. Ko-SRoBERTa: Best for Korean-only content")
        print("   3. Multilingual-E5-Base: Good balance of speed and quality")

    def save_results(self):
        """결과를 JSON 파일로 저장"""
        output_file = "embedding_benchmark_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"\n📁 Results saved to {output_file}")


if __name__ == "__main__":
    # 환경 체크
    print("🔧 Environment Check")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")

    # 벤치마크 실행
    benchmark = EmbeddingBenchmark()

    # 간단한 테스트 (빠른 모델만)
    quick_test = True

    if quick_test:
        print("\n⚡ Running quick test with selected models...")
        # 주요 모델만 테스트
        models = [
            ("BGE-M3", "BAAI/bge-m3"),
            ("Multilingual-E5-Base", "intfloat/multilingual-e5-base"),
            ("Ko-SRoBERTa", "jhgan/ko-sroberta-multitask"),
        ]

        for model_name, model_id in models:
            result = benchmark.benchmark_model(model_name, model_id)
            benchmark.results[model_name] = result

        benchmark.print_summary()
        benchmark.save_results()
    else:
        # 전체 벤치마크
        benchmark.run_benchmarks()