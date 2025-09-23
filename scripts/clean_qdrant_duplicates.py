#!/usr/bin/env python3
"""
Qdrant 중복 벡터 정리 스크립트
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from collections import defaultdict
import sys

def clean_duplicates():
    print("🔍 Qdrant 중복 데이터 정리 시작...")

    # Qdrant 연결
    client = QdrantClient(host="localhost", port=6333)

    collections = ["youtube_content", "youtube_summaries"]

    total_deleted = 0

    for collection in collections:
        print(f"\n📦 {collection} 컬렉션 처리 중...")

        try:
            # 모든 포인트 조회 (최대 10000개)
            response = client.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )

            points = response[0]
            print(f"  총 {len(points)}개 포인트 발견")

            # content_id별로 그룹화
            content_groups = defaultdict(list)
            for point in points:
                content_id = point.payload.get('content_id')
                if content_id:
                    content_groups[content_id].append({
                        'id': point.id,
                        'text': point.payload.get('text', '')[:50],  # 처음 50자만
                        'chunk_id': point.payload.get('chunk_id', point.id)
                    })

            # 중복 확인 및 제거
            for content_id, point_list in content_groups.items():
                if len(point_list) > 1:
                    # chunk_id별로 그룹화하여 진짜 중복 찾기
                    chunk_groups = defaultdict(list)
                    for p in point_list:
                        chunk_groups[p['chunk_id']].append(p['id'])

                    # 각 chunk_id에서 첫 번째만 남기고 나머지 삭제
                    points_to_delete = []
                    for chunk_id, ids in chunk_groups.items():
                        if len(ids) > 1:
                            # 첫 번째를 제외한 나머지를 삭제 대상으로
                            points_to_delete.extend(ids[1:])

                    if points_to_delete:
                        print(f"  Content {content_id}: {len(points_to_delete)}개 중복 발견")

                        # 삭제 실행
                        client.delete(
                            collection_name=collection,
                            points_selector=points_to_delete
                        )

                        total_deleted += len(points_to_delete)
                        print(f"    ✅ {len(points_to_delete)}개 삭제 완료")

            # 컬렉션 최적화
            print(f"  🔧 {collection} 컬렉션 최적화 중...")
            # Qdrant는 자동으로 최적화되므로 특별한 API 호출 불필요

        except Exception as e:
            print(f"  ❌ {collection} 처리 실패: {e}")

    print(f"\n✅ 총 {total_deleted}개 중복 벡터 삭제 완료")

    # 정리 후 상태 확인
    print("\n📊 정리 후 상태:")
    for collection in collections:
        try:
            info = client.get_collection(collection)
            print(f"  {collection}: {info.points_count} 포인트")
        except:
            print(f"  {collection}: 조회 실패")

    return total_deleted

if __name__ == "__main__":
    deleted = clean_duplicates()
    sys.exit(0 if deleted >= 0 else 1)