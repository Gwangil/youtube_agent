#!/usr/bin/env python3
"""
트랜잭션 관리자
- 데이터 처리 시 원자성 보장
- 실패 시 자동 롤백
- RDB와 Vector DB 동기화
"""

import logging
from typing import Optional, Dict, List, Any, Callable
from contextlib import contextmanager
from sqlalchemy.orm import Session
from qdrant_client import QdrantClient
import redis
import json
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class TransactionLog:
    """트랜잭션 로그"""
    transaction_id: str
    content_id: int
    operation: str
    status: str  # pending, success, failed, rolled_back
    db_changes: Dict
    vector_changes: Dict
    error: Optional[str]
    timestamp: str

class TransactionManager:
    """트랜잭션 관리자"""

    def __init__(self, db_session: Session, qdrant: QdrantClient, redis_client: redis.Redis):
        self.db = db_session
        self.qdrant = qdrant
        self.redis = redis_client
        self.transaction_id = None

    @contextmanager
    def atomic_operation(self, content_id: int, operation: str):
        """
        원자적 작업 컨텍스트 매니저
        실패 시 자동 롤백
        """
        # 트랜잭션 시작
        self.transaction_id = f"{operation}_{content_id}_{datetime.utcnow().timestamp()}"

        # 롤백 정보 저장
        rollback_info = {
            "db_snapshot": self._snapshot_db_state(content_id),
            "vector_snapshot": self._snapshot_vector_state(content_id),
            "redis_snapshot": self._snapshot_redis_state(content_id)
        }

        # 트랜잭션 로그 생성
        log = TransactionLog(
            transaction_id=self.transaction_id,
            content_id=content_id,
            operation=operation,
            status="pending",
            db_changes={},
            vector_changes={},
            error=None,
            timestamp=datetime.utcnow().isoformat()
        )

        try:
            # 트랜잭션 시작 로깅
            self._log_transaction(log)

            # DB 트랜잭션 시작
            self.db.begin_nested()

            yield self

            # 성공 시 커밋
            self.db.commit()

            # 성공 로그
            log.status = "success"
            self._log_transaction(log)

        except Exception as e:
            # 실패 시 롤백
            logger.error(f"트랜잭션 실패 ({self.transaction_id}): {e}")

            # DB 롤백
            self.db.rollback()

            # Vector DB 롤백
            self._rollback_vectors(content_id, rollback_info["vector_snapshot"])

            # Redis 롤백
            self._rollback_redis(content_id, rollback_info["redis_snapshot"])

            # 실패 로그
            log.status = "rolled_back"
            log.error = str(e)
            self._log_transaction(log)

            raise

    def _snapshot_db_state(self, content_id: int) -> Dict:
        """DB 상태 스냅샷"""
        snapshot = {}

        # content 테이블
        content = self.db.execute(
            "SELECT * FROM content WHERE id = :id",
            {"id": content_id}
        ).fetchone()
        if content:
            snapshot["content"] = dict(content._mapping)

        # transcripts 테이블
        transcripts = self.db.execute(
            "SELECT * FROM transcripts WHERE content_id = :id",
            {"id": content_id}
        ).fetchall()
        snapshot["transcripts"] = [dict(t._mapping) for t in transcripts]

        # vector_mappings 테이블
        mappings = self.db.execute(
            "SELECT * FROM vector_mappings WHERE content_id = :id",
            {"id": content_id}
        ).fetchall()
        snapshot["vector_mappings"] = [dict(m._mapping) for m in mappings]

        # processing_jobs 테이블
        jobs = self.db.execute(
            "SELECT * FROM processing_jobs WHERE content_id = :id",
            {"id": content_id}
        ).fetchall()
        snapshot["processing_jobs"] = [dict(j._mapping) for j in jobs]

        return snapshot

    def _snapshot_vector_state(self, content_id: int) -> Dict:
        """Vector DB 상태 스냅샷"""
        snapshot = {}

        collections = ["youtube_content", "youtube_summaries"]

        for collection in collections:
            try:
                # 해당 content의 모든 벡터 조회
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                response = self.qdrant.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="content_id",
                                match=MatchValue(value=content_id)
                            )
                        ]
                    ),
                    limit=1000
                )

                points = response[0]
                snapshot[collection] = [
                    {
                        "id": str(p.id),
                        "vector": p.vector,
                        "payload": p.payload
                    }
                    for p in points
                ]
            except Exception as e:
                logger.warning(f"Vector 스냅샷 실패 ({collection}): {e}")
                snapshot[collection] = []

        return snapshot

    def _snapshot_redis_state(self, content_id: int) -> Dict:
        """Redis 상태 스냅샷"""
        snapshot = {}

        # 관련 키 패턴들
        patterns = [
            f"content:{content_id}:*",
            f"processing:{content_id}:*",
            f"cache:content:{content_id}:*"
        ]

        for pattern in patterns:
            keys = self.redis.keys(pattern)
            for key in keys:
                key_type = self.redis.type(key)

                if key_type == "string":
                    snapshot[key] = {"type": "string", "value": self.redis.get(key)}
                elif key_type == "hash":
                    snapshot[key] = {"type": "hash", "value": self.redis.hgetall(key)}
                elif key_type == "list":
                    snapshot[key] = {"type": "list", "value": self.redis.lrange(key, 0, -1)}
                elif key_type == "set":
                    snapshot[key] = {"type": "set", "value": list(self.redis.smembers(key))}

        return snapshot

    def _rollback_vectors(self, content_id: int, snapshot: Dict):
        """Vector DB 롤백"""
        for collection, points in snapshot.items():
            try:
                # 현재 벡터 모두 삭제
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                self.qdrant.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="content_id",
                                match=MatchValue(value=content_id)
                            )
                        ]
                    )
                )

                # 스냅샷 벡터 복원
                if points:
                    from qdrant_client.models import PointStruct

                    self.qdrant.upsert(
                        collection_name=collection,
                        points=[
                            PointStruct(
                                id=p["id"],
                                vector=p["vector"],
                                payload=p["payload"]
                            )
                            for p in points
                        ]
                    )

                logger.info(f"Vector 롤백 완료: {collection}, {len(points)}개 포인트")

            except Exception as e:
                logger.error(f"Vector 롤백 실패 ({collection}): {e}")

    def _rollback_redis(self, content_id: int, snapshot: Dict):
        """Redis 롤백"""
        # 현재 키 삭제
        patterns = [
            f"content:{content_id}:*",
            f"processing:{content_id}:*",
            f"cache:content:{content_id}:*"
        ]

        for pattern in patterns:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)

        # 스냅샷 복원
        for key, data in snapshot.items():
            try:
                if data["type"] == "string":
                    self.redis.set(key, data["value"])
                elif data["type"] == "hash":
                    self.redis.hset(key, mapping=data["value"])
                elif data["type"] == "list":
                    self.redis.rpush(key, *data["value"])
                elif data["type"] == "set":
                    self.redis.sadd(key, *data["value"])

            except Exception as e:
                logger.error(f"Redis 롤백 실패 ({key}): {e}")

    def _log_transaction(self, log: TransactionLog):
        """트랜잭션 로그 저장"""
        log_data = asdict(log)

        # Redis에 로그 저장
        self.redis.lpush(
            "transaction_logs",
            json.dumps(log_data, ensure_ascii=False)
        )

        # 최근 1000개만 유지
        self.redis.ltrim("transaction_logs", 0, 999)

        # 실패한 트랜잭션은 별도 저장
        if log.status in ["failed", "rolled_back"]:
            self.redis.lpush(
                "failed_transactions",
                json.dumps(log_data, ensure_ascii=False)
            )
            self.redis.ltrim("failed_transactions", 0, 99)

    def add_vector(self, content_id: int, collection: str, vector_data: Dict):
        """벡터 추가 (트랜잭션 내)"""
        # DB에 매핑 추가
        self.db.execute(
            """INSERT INTO vector_mappings
               (content_id, chunk_id, vector_collection, chunk_text, chunk_order, chunk_metadata)
               VALUES (:content_id, :chunk_id, :collection, :text, :order, :metadata)""",
            {
                "content_id": content_id,
                "chunk_id": vector_data["chunk_id"],
                "collection": collection,
                "text": vector_data["text"],
                "order": vector_data.get("order", 0),
                "metadata": json.dumps(vector_data.get("metadata", {}))
            }
        )

        # Qdrant에 벡터 추가
        from qdrant_client.models import PointStruct

        self.qdrant.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=vector_data["chunk_id"],
                    vector=vector_data["vector"],
                    payload={
                        "content_id": content_id,
                        "text": vector_data["text"],
                        **vector_data.get("metadata", {})
                    }
                )
            ]
        )

        # 콘텐츠 상태 업데이트
        self.db.execute(
            "UPDATE content SET vector_stored = TRUE WHERE id = :id",
            {"id": content_id}
        )

    def remove_vectors(self, content_id: int):
        """벡터 제거 (트랜잭션 내)"""
        # DB에서 매핑 제거
        self.db.execute(
            "DELETE FROM vector_mappings WHERE content_id = :id",
            {"id": content_id}
        )

        # Qdrant에서 벡터 제거
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        for collection in ["youtube_content", "youtube_summaries"]:
            self.qdrant.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="content_id",
                            match=MatchValue(value=content_id)
                        )
                    ]
                )
            )

        # 콘텐츠 상태 업데이트
        self.db.execute(
            "UPDATE content SET vector_stored = FALSE WHERE id = :id",
            {"id": content_id}
        )