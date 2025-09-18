#!/usr/bin/env python3
"""
Graceful Shutdown Script
서비스 중지 전 처리 중인 작업을 안전하게 처리
"""

import os
import sys
import signal
import time
from datetime import datetime, timedelta

sys.path.append('/app')
sys.path.append('/app/shared')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from shared.models.database import ProcessingJob, get_database_url


class GracefulShutdown:
    """안전한 서비스 종료 관리"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

    def reset_processing_jobs(self, grace_period_seconds=30):
        """처리 중인 작업을 pending으로 리셋"""
        with self.SessionLocal() as session:
            try:
                # 현재 processing 상태인 작업들 조회
                processing_jobs = session.query(ProcessingJob).filter(
                    ProcessingJob.status == 'processing'
                ).all()

                if not processing_jobs:
                    print("✅ 처리 중인 작업 없음")
                    return 0

                print(f"⚠️ 처리 중인 작업 {len(processing_jobs)}개 발견")

                # Grace period 대기
                if grace_period_seconds > 0:
                    print(f"⏰ {grace_period_seconds}초 대기 (작업 완료 대기)...")
                    time.sleep(grace_period_seconds)

                    # 다시 확인
                    processing_jobs = session.query(ProcessingJob).filter(
                        ProcessingJob.status == 'processing'
                    ).all()

                # 여전히 processing인 작업들을 pending으로 리셋
                reset_count = 0
                for job in processing_jobs:
                    print(f"  🔄 Job {job.id} ({job.job_type}) -> pending")
                    job.status = 'pending'
                    job.started_at = None
                    job.error_message = "Service stopped during processing"
                    reset_count += 1

                session.commit()
                print(f"✅ {reset_count}개 작업을 pending으로 리셋")
                return reset_count

            except Exception as e:
                print(f"❌ 작업 리셋 실패: {e}")
                session.rollback()
                return -1

    def wait_for_safe_point(self, max_wait_seconds=60):
        """안전한 중지 시점까지 대기"""
        with self.SessionLocal() as session:
            start_time = time.time()

            while time.time() - start_time < max_wait_seconds:
                # 다운로드 중인 작업 확인
                downloading = session.execute(
                    text("""
                        SELECT COUNT(*) FROM processing_jobs
                        WHERE status = 'processing'
                        AND job_type = 'process_audio'
                        AND started_at > NOW() - INTERVAL '1 minute'
                    """)
                ).scalar()

                if downloading == 0:
                    print("✅ 안전한 중지 시점")
                    return True

                print(f"⏳ 다운로드 중인 작업 {downloading}개 대기...")
                time.sleep(5)

            print("⚠️ 대기 시간 초과")
            return False

    def cleanup_orphaned_files(self):
        """임시 파일 정리"""
        temp_dirs = ['/tmp/shared_audio', '/tmp/youtube_downloads']

        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    import shutil
                    file_count = len(os.listdir(temp_dir))
                    if file_count > 0:
                        shutil.rmtree(temp_dir)
                        os.makedirs(temp_dir, exist_ok=True)
                        print(f"🧹 {temp_dir}: {file_count}개 임시 파일 정리")
                except Exception as e:
                    print(f"⚠️ 임시 파일 정리 실패: {e}")


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='Graceful Shutdown')
    parser.add_argument('--mode', choices=['stop', 'start'], required=True,
                      help='동작 모드')
    parser.add_argument('--grace', type=int, default=30,
                      help='Grace period in seconds')
    args = parser.parse_args()

    shutdown = GracefulShutdown()

    if args.mode == 'stop':
        print("🛑 서비스 안전 종료 시작...")

        # 1. 안전한 시점 대기
        shutdown.wait_for_safe_point(max_wait_seconds=args.grace)

        # 2. Processing 작업 리셋
        shutdown.reset_processing_jobs(grace_period_seconds=10)

        # 3. 임시 파일 정리
        shutdown.cleanup_orphaned_files()

        print("✅ 안전 종료 완료")

    elif args.mode == 'start':
        print("🚀 서비스 시작 전 정리...")

        # 1. Stuck 작업 리셋
        with shutdown.SessionLocal() as session:
            # 1시간 이상 processing 상태인 작업 리셋
            result = session.execute(
                text("""
                    UPDATE processing_jobs
                    SET status = 'pending', started_at = NULL
                    WHERE status = 'processing'
                    AND started_at < NOW() - INTERVAL '1 hour'
                """)
            )
            session.commit()

            if result.rowcount > 0:
                print(f"✅ {result.rowcount}개 stuck 작업 리셋")

        # 2. 임시 파일 정리
        shutdown.cleanup_orphaned_files()

        print("✅ 시작 준비 완료")


if __name__ == "__main__":
    main()