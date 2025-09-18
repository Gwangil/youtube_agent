#!/usr/bin/env python3
"""
Whisper 캐시 초기화 스크립트
모델 파일을 Whisper가 기대하는 정확한 위치와 이름으로 복사
"""

import os
import shutil

def init_whisper_cache():
    """Whisper 캐시 디렉토리에 모델 파일 복사"""

    # 모델 파일 매핑 (원본 -> 캐시)
    model_mappings = {
        "/app/models/whisper/large-v3.pt": {
            "cache_name": "large-v3.pt",
            "hash_name": None  # large-v3는 파일명 그대로 사용
        },
        "/app/models/whisper/large.pt": {
            "cache_name": "large-v2.pt",
            "hash_name": None  # large는 large-v2로 저장
        },
        "/app/models/whisper/medium.pt": {
            "cache_name": "medium.pt",
            "hash_name": None
        },
    }

    # Whisper 캐시 디렉토리들
    cache_dirs = [
        os.path.expanduser("~/.cache/whisper"),
        "/root/.cache/whisper",
        "/app/models/whisper"  # 백업 위치
    ]

    for cache_dir in cache_dirs:
        os.makedirs(cache_dir, exist_ok=True)
        print(f"📁 캐시 디렉토리 확인: {cache_dir}")

    # 모델 파일 복사
    for source_path, info in model_mappings.items():
        if os.path.exists(source_path):
            file_size_mb = os.path.getsize(source_path) / (1024 * 1024)
            print(f"🔍 발견: {source_path} ({file_size_mb:.1f}MB)")

            for cache_dir in cache_dirs[:2]:  # ~/.cache/whisper와 /root/.cache/whisper만
                cache_path = os.path.join(cache_dir, info["cache_name"])

                # 이미 존재하는지 확인
                if os.path.exists(cache_path):
                    cache_size_mb = os.path.getsize(cache_path) / (1024 * 1024)
                    if abs(cache_size_mb - file_size_mb) < 1:  # 1MB 차이 이내면 동일
                        print(f"  ✅ 이미 존재: {cache_path}")
                        continue
                    else:
                        print(f"  ⚠️ 크기 불일치, 재복사: {cache_path}")

                # 하드링크 시도 (빠르고 공간 절약)
                try:
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                    os.link(source_path, cache_path)
                    print(f"  🔗 하드링크 생성: {cache_path}")
                except:
                    # 실패 시 복사
                    try:
                        shutil.copy2(source_path, cache_path)
                        print(f"  📋 복사 완료: {cache_path}")
                    except Exception as e:
                        print(f"  ❌ 복사 실패: {e}")

    print("✨ Whisper 캐시 초기화 완료")

    # 캐시 상태 확인
    print("\n📊 캐시 상태:")
    for cache_dir in cache_dirs[:2]:
        if os.path.exists(cache_dir):
            files = os.listdir(cache_dir)
            if files:
                print(f"  {cache_dir}:")
                for file in files:
                    file_path = os.path.join(cache_dir, file)
                    if os.path.isfile(file_path):
                        size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        print(f"    - {file}: {size_mb:.1f}MB")

if __name__ == "__main__":
    init_whisper_cache()