#!/usr/bin/env python3
"""
STT 전용 워커
오디오 STT 처리만 전담하는 워커
"""

import os
import sys
import time
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import (
    Content, Transcript, ProcessingJob,
    get_database_url
)
from src.youtube_agent.stt_processor import STTProcessor


class STTWorker:
    """STT 전용 워커"""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # STT 프로세서 초기화 (Whisper Large)
        self.stt_processor = STTProcessor(model_size="large")

        print(f"🚀 STT 워커 #{worker_id} 초기화 완료")

    def get_db(self):
        """데이터베이스 세션 생성"""
        return self.SessionLocal()

    def process_audio_stt(self, job: ProcessingJob):
        """오디오 STT 처리"""
        print(f"🎙️ [Worker {self.worker_id}] STT 작업 처리: Job {job.id}")

        db = self.get_db()
        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠 정보 조회
            content = db.query(Content).filter(Content.id == job.content_id).first()
            if not content:
                raise Exception("콘텐츠를 찾을 수 없습니다")

            print(f"  🎯 처리 중: {content.title[:50]}...")

            # STT 처리
            stt_result = self.stt_processor.process_video(
                content.url,
                content.external_id,
                content.language
            )

            if stt_result:
                # 트랜스크립트 데이터 저장
                for i, segment in enumerate(stt_result.get('segments', [])):
                    transcript = Transcript(
                        content_id=content.id,
                        text=segment['text'],
                        start_time=segment.get('start', 0),
                        end_time=segment.get('end', 0),
                        segment_order=i
                    )
                    db.add(transcript)

                # 콘텐츠 업데이트
                content.transcript_available = True
                content.transcript_type = 'stt_whisper'
                content.language = stt_result.get('language', content.language)

                # 벡터화 작업 큐에 추가 (높은 우선순위)
                vector_job = ProcessingJob(
                    job_type='vectorize',
                    content_id=content.id,
                    status='pending',
                    priority=10  # 높은 우선순위
                )
                db.add(vector_job)

                # 작업 완료
                job.status = 'completed'
                job.completed_at = datetime.utcnow()

                print(f"  ✅ [Worker {self.worker_id}] STT 처리 완료: {content.title[:50]}...")

            else:
                raise Exception("STT 처리 실패")

            db.commit()

        except Exception as e:
            print(f"  ❌ [Worker {self.worker_id}] STT 처리 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def start_worker(self):
        """STT 워커 시작 - process_audio 작업만 처리"""
        print(f"🚀 STT 워커 #{self.worker_id} 시작")

        while True:
            try:
                db = self.get_db()

                # STT 작업만 조회 (우선순위 높은 순)
                stt_jobs = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type == 'process_audio',
                    ProcessingJob.status == 'pending'
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).limit(1).all()

                if stt_jobs:
                    for job in stt_jobs:
                        print(f"\n🎯 [Worker {self.worker_id}] STT 작업 선택: Job {job.id}")
                        self.process_audio_stt(job)
                        time.sleep(1)  # 작업 간 짧은 대기
                else:
                    print(f"📭 [Worker {self.worker_id}] 대기 중인 STT 작업 없음")

                db.close()
                time.sleep(5)  # 5초마다 확인

            except KeyboardInterrupt:
                print(f"🛑 STT 워커 #{self.worker_id} 종료")
                break
            except Exception as e:
                print(f"❌ [Worker {self.worker_id}] 워커 오류: {e}")
                time.sleep(15)


def main():
    """메인 실행 함수"""
    # 워커 ID를 환경변수나 CLI 인자로 받기
    worker_id = int(os.getenv('STT_WORKER_ID', sys.argv[1] if len(sys.argv) > 1 else 0))

    worker = STTWorker(worker_id)
    worker.start_worker()


if __name__ == "__main__":
    main()