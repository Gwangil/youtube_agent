"""
YouTube 채널 및 비디오에서 자막을 추출하는 모듈
"""

import re
import os
import json
from typing import List, Dict, Optional, Union
from urllib.parse import urlparse, parse_qs
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from pytube import YouTube, Channel
import pandas as pd


class YouTubeExtractor:
    """YouTube 채널에서 자막과 메타데이터를 추출하는 클래스"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def extract_video_id(self, url: str) -> Optional[str]:
        """YouTube URL에서 비디오 ID 추출"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/v\/([^&\n?#]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def normalize_channel_url(self, channel_url: str) -> str:
        """채널 URL을 정규화 (팟캐스트 URL 처리 포함)"""
        # /podcasts가 포함된 URL을 일반 채널 URL로 변환
        if '/podcasts' in channel_url:
            return channel_url.replace('/podcasts', '')
        return channel_url

    def is_podcast_url(self, channel_url: str) -> bool:
        """팟캐스트 전용 URL인지 확인"""
        return '/podcasts' in channel_url

    def get_channel_videos(self, channel_url: str, max_videos: int = 50) -> List[Dict]:
        """채널에서 비디오 목록 가져오기 (팟캐스트 포함)"""
        original_url = channel_url
        is_podcast_channel = self.is_podcast_url(channel_url)

        # URL 정규화
        normalized_url = self.normalize_channel_url(channel_url)

        try:
            # 먼저 yt-dlp로 시도 (더 안정적)
            videos = self._get_videos_with_ytdlp(normalized_url, max_videos, is_podcast_channel)

            if not videos:
                # yt-dlp 실패 시 pytube로 대체
                videos = self._get_videos_with_pytube(normalized_url, max_videos, is_podcast_channel)

            return videos

        except Exception as e:
            print(f"채널 비디오 목록 가져오기 실패: {e}")
            return []

    def _get_videos_with_ytdlp(self, channel_url: str, max_videos: int, is_podcast: bool) -> List[Dict]:
        """yt-dlp를 사용하여 비디오 목록 가져오기"""
        try:
            # 채널의 비디오 탭에서 실제 비디오들 가져오기
            videos_url = channel_url + '/videos'

            ydl_opts = {
                'quiet': False,  # Enable output to see what's happening
                'no_warnings': False,
                'extract_flat': True,
                'playlistend': max_videos,
            }

            # 팟캐스트 채널인 경우 플레이리스트 URL 구성
            if is_podcast:
                videos_url = channel_url + '/podcasts'

            print(f"yt-dlp URL: {videos_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(videos_url, download=False)

                if not info:
                    return []

                entries = info.get('entries', [])
                videos = []

                for entry in entries[:max_videos]:
                    if not entry:
                        continue

                    video_info = {
                        'video_id': entry.get('id'),
                        'title': entry.get('title', ''),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'publish_date': None,  # yt-dlp extract_flat에서는 제한적 정보
                        'length': entry.get('duration'),
                        'views': entry.get('view_count', 0),
                        'description': entry.get('description', '')[:500] if entry.get('description') else "",
                        'is_podcast': is_podcast
                    }
                    videos.append(video_info)

                print(f"yt-dlp로 {len(videos)}개 비디오 추출 완료")
                return videos

        except Exception as e:
            print(f"yt-dlp 추출 실패: {e}")
            return []

    def _get_videos_with_pytube(self, channel_url: str, max_videos: int, is_podcast: bool) -> List[Dict]:
        """pytube를 사용하여 비디오 목록 가져오기 (대체 방법)"""
        try:
            channel = Channel(channel_url)
            videos = []

            count = 0
            for video in channel.video_urls:
                if count >= max_videos:
                    break

                try:
                    yt = YouTube(video)
                    video_info = {
                        'video_id': self.extract_video_id(video),
                        'title': yt.title,
                        'url': video,
                        'publish_date': yt.publish_date,
                        'length': yt.length,
                        'views': yt.views,
                        'description': yt.description[:500] if yt.description else "",
                        'is_podcast': is_podcast
                    }
                    videos.append(video_info)
                    count += 1
                except Exception as e:
                    print(f"비디오 정보 추출 실패 {video}: {e}")
                    continue

            print(f"pytube로 {len(videos)}개 비디오 추출 완료")
            return videos

        except Exception as e:
            print(f"pytube 추출 실패: {e}")
            return []

    def extract_transcript(self, video_id: str, languages: List[str] = ['ko', 'en']) -> Optional[Dict]:
        """YouTube 자막 추출"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # 자동 생성 자막 우선 시도
            for lang in languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    transcript_data = transcript.fetch()

                    # 자막 텍스트 결합
                    full_text = ' '.join([item['text'] for item in transcript_data])

                    return {
                        'video_id': video_id,
                        'language': lang,
                        'transcript_type': 'auto' if transcript.is_generated else 'manual',
                        'transcript_data': transcript_data,
                        'full_text': full_text
                    }
                except Exception:
                    continue

            return None
        except Exception as e:
            print(f"자막 추출 실패 {video_id}: {e}")
            return None

    def extract_channel_transcripts(self, channel_url: str, max_videos: int = 50) -> List[Dict]:
        """채널의 모든 비디오에서 자막 추출"""
        videos = self.get_channel_videos(channel_url, max_videos)
        results = []

        for video in videos:
            video_id = video['video_id']
            if not video_id:
                continue

            print(f"자막 추출 중: {video['title']}")
            transcript = self.extract_transcript(video_id)

            if transcript:
                result = {
                    **video,
                    **transcript
                }
                results.append(result)
            else:
                # 자막이 없는 경우에도 비디오 정보는 저장
                result = {
                    **video,
                    'transcript_available': False
                }
                results.append(result)

        return results

    def save_to_csv(self, data: List[Dict], filename: str) -> str:
        """결과를 CSV 파일로 저장"""
        if not data:
            return ""

        df = pd.DataFrame(data)
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return filepath

    def save_to_json(self, data: List[Dict], filename: str) -> str:
        """결과를 JSON 파일로 저장"""
        if not data:
            return ""

        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return filepath