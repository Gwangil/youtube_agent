#!/usr/bin/env python3
"""
Whisper 캐시 초기화 스크립트
모델 파일을 Whisper가 기대하는 정확한 위치와 이름으로 복사
"""

import os
import sys
import shutil
import time

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
        "/root/.cache/whisper"
    ]

    for cache_dir in cache_dirs:
        os.makedirs(cache_dir, exist_ok=True)
        print(f"📁 캐시 디렉토리 확인: {cache_dir}")

    # 모델 파일 확인 및 링크 생성
    models_found = False
    for source_path, info in model_mappings.items():
        if os.path.exists(source_path):
            models_found = True
            file_size_mb = os.path.getsize(source_path) / (1024 * 1024)
            print(f"🔍 발견: {source_path} ({file_size_mb:.1f}MB)")

            for cache_dir in cache_dirs:
                cache_path = os.path.join(cache_dir, info["cache_name"])

                # 이미 존재하는지 확인
                if os.path.exists(cache_path):
                    try:
                        cache_size_mb = os.path.getsize(cache_path) / (1024 * 1024)
                        if abs(cache_size_mb - file_size_mb) < 1:  # 1MB 차이 이내면 동일
                            print(f"  ✅ 이미 존재: {cache_path}")
                            continue
                        else:
                            print(f"  ⚠️ 크기 불일치, 재생성: {cache_path}")
                            os.remove(cache_path)
                    except:
                        pass

                # 심볼릭 링크 생성 (하드링크 대신, 더 안전)
                try:
                    if not os.path.exists(cache_path):
                        os.symlink(source_path, cache_path)
                        print(f"  🔗 심볼릭 링크 생성: {cache_path}")
                except Exception as e:
                    print(f"  ⚠️ 링크 생성 실패: {e}")
                    # 링크 실패시 스킵 (복사는 하지 않음 - 너무 오래 걸림)

    if not models_found:
        print("⚠️ 경고: 모델 파일이 없습니다. 서버 시작 시 다운로드될 예정입니다.")

    print("✨ Whisper 캐시 초기화 완료")

    # 캐시 상태 간단히 확인
    print("\n📊 캐시 상태:")
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            files = [f for f in os.listdir(cache_dir) if f.endswith('.pt')]
            if files:
                print(f"  {cache_dir}: {len(files)} 모델")

if __name__ == "__main__":
    start_time = time.time()
    try:
        init_whisper_cache()
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"⏱️ 소요 시간: {elapsed:.1f}초")