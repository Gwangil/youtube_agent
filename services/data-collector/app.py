"""
데이터 수집 서비스 메인 애플리케이션
YouTube 채널에서 콘텐츠 수집
"""

import os
import sys
import time
import json
import schedule
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to path
sys.path.append('/app')
sys.path.append('/app/shared')

from shared.models.database import Channel, Content, ProcessingJob, get_database_url
# from shared.utils.spotify_client import SpotifyClient  # Removed - YouTube only
from src.youtube_agent.youtube_extractor import YouTubeExtractor


class DataCollector:
    """통합 데이터 수집기"""

    def __init__(self):
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.youtube_extractor = YouTubeExtractor()

    def get_db(self):
        """데이터베이스 세션 생성"""
        db = self.SessionLocal()
        try:
            return db
        finally:
            pass

    def collect_youtube_channel(self, channel: Channel, max_videos: int = 50):
        """YouTube 채널 데이터 수집"""
        print(f"YouTube 채널 수집 시작: {channel.name}")

        try:
            # YouTube 데이터 추출
            videos = self.youtube_extractor.get_channel_videos(channel.url, max_videos)

            db = self.get_db()
            new_content_count = 0

            for video in videos:
                try:
                    # 기존 콘텐츠 확인
                    existing = db.query(Content).filter(
                        Content.channel_id == channel.id,
                        Content.external_id == video['video_id']
                    ).first()

                    if existing:
                        continue

                    # 새 콘텐츠 생성
                    content = Content(
                        channel_id=channel.id,
                        external_id=video['video_id'],
                        title=video['title'],
                        url=video['url'],
                        description=video.get('description', ''),
                        duration=video.get('length'),
                        publish_date=video.get('publish_date'),
                        views_count=video.get('views', 0),
                        language=channel.language,
                        is_podcast=video.get('is_podcast', False),
                        transcript_available=False
                    )

                    db.add(content)
                    db.commit()

                    # 자막 추출 작업 큐에 추가
                    job = ProcessingJob(
                        job_type='extract_transcript',
                        content_id=content.id,
                        status='pending'
                    )
                    db.add(job)
                    db.commit()

                    new_content_count += 1
                    print(f"새 비디오 추가: {video['title']}")

                except Exception as e:
                    print(f"비디오 처리 실패: {e}")
                    db.rollback()
                    continue

            db.close()
            print(f"YouTube 수집 완료: {new_content_count}개 새 비디오")

        except Exception as e:
            print(f"YouTube 채널 수집 실패: {e}")


    def collect_all_channels(self):
        """모든 활성 채널 데이터 수집"""
        db = self.get_db()

        try:
            active_channels = db.query(Channel).filter(Channel.is_active == True).all()

            for channel in active_channels:
                print(f"\n채널 수집 시작: {channel.name} ({channel.platform})")

                if channel.platform == 'youtube':
                    self.collect_youtube_channel(channel)
                else:
                    print(f"지원하지 않는 플랫폼: {channel.platform} (YouTube만 지원)")

                # 채널 업데이트 시간 갱신
                channel.updated_at = datetime.utcnow()
                db.commit()

                # 요청 간 대기 (API 제한 고려)
                time.sleep(2)

        except Exception as e:
            print(f"채널 수집 중 오류: {e}")
        finally:
            db.close()

    def start_scheduler(self):
        """스케줄러 시작"""
        # 매일 오전 6시에 데이터 수집
        schedule.every().day.at("06:00").do(self.collect_all_channels)

        # 매 4시간마다 증분 수집
        schedule.every(4).hours.do(self.collect_all_channels)

        print("데이터 수집 스케줄러 시작됨")
        print("- 매일 06:00에 전체 수집")
        print("- 매 4시간마다 증분 수집")

        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 스케줄 확인


def main():
    """메인 실행 함수"""
    print("데이터 수집 서비스 시작")

    collector = DataCollector()

    # 시작 시 즉시 한 번 수집
    print("초기 데이터 수집 시작...")
    collector.collect_all_channels()

    # 스케줄러 시작
    collector.start_scheduler()


if __name__ == "__main__":
    main()