"""
STT (Speech-to-Text) 처리 모듈
자막이 없는 YouTube 비디오에 대해 음성을 텍스트로 변환
"""

import os
import tempfile
import subprocess
from typing import Dict, Optional, List
import whisper
import yt_dlp
from pathlib import Path


class STTProcessor:
    """Whisper를 사용한 음성-텍스트 변환 클래스"""

    def __init__(self, model_size: str = "large", output_dir: str = "output"):
        """
        Args:
            model_size: whisper 모델 크기 (tiny, base, small, medium, large)
            output_dir: 출력 디렉토리
        """
        self.model_size = model_size
        self.output_dir = output_dir
        self.model = None
        os.makedirs(output_dir, exist_ok=True)

    def load_model(self):
        """Whisper 모델 로드"""
        if self.model is None:
            print(f"Whisper {self.model_size} 모델 로딩 중...")
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"사용 디바이스: {device}")
            self.model = whisper.load_model(self.model_size, device=device)
            print("모델 로딩 완료")

    def download_audio(self, video_url: str, temp_dir: str) -> Optional[str]:
        """YouTube 비디오에서 오디오만 다운로드"""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '320',
                }],
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                title = info.get('title', 'unknown')

                # 다운로드된 파일 찾기
                for ext in ['wav', 'mp3', 'm4a']:
                    audio_file = os.path.join(temp_dir, f"{title}.{ext}")
                    if os.path.exists(audio_file):
                        return audio_file

                return None

        except Exception as e:
            print(f"오디오 다운로드 실패: {e}")
            return None

    def transcribe_audio(self, audio_file: str, language: str = 'ko') -> Optional[Dict]:
        """오디오 파일을 텍스트로 변환"""
        try:
            self.load_model()

            print(f"STT 처리 중: {os.path.basename(audio_file)}")
            import torch
            fp16_enabled = torch.cuda.is_available()
            print(f"FP16 사용: {fp16_enabled}")

            result = self.model.transcribe(
                audio_file,
                language=language,
                task='transcribe',
                fp16=fp16_enabled,  # GPU에서 FP16 사용으로 속도 향상
                beam_size=1,  # Reduce beam size to prevent hallucination
                best_of=1,    # Reduce best_of to prevent hallucination
                temperature=(0.0, 0.2, 0.4, 0.6, 0.8),  # Temperature fallback
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                initial_prompt="다음은 한국어 팟캐스트입니다."  # Korean context
            )

            # 세그먼트별 정보 구성 및 반복 제거
            segments = []
            processed_segments = self._remove_repetitive_segments(result.get('segments', []))

            for segment in processed_segments:
                clean_text = self._clean_repetitive_text(segment['text'].strip())
                if clean_text:  # 빈 텍스트 제외
                    segments.append({
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': clean_text
                    })

            # 전체 텍스트도 반복 제거 처리
            full_text = ' '.join([seg['text'] for seg in segments])
            clean_full_text = self._clean_repetitive_text(full_text)

            return {
                'language': result.get('language', language),
                'text': clean_full_text,
                'segments': segments,
                'transcript_type': 'stt_whisper'
            }

        except Exception as e:
            print(f"STT 처리 실패: {e}")
            return None

    def _clean_repetitive_text(self, text: str) -> str:
        """반복되는 텍스트 패턴 제거"""
        import re

        if not text:
            return text

        # 연속된 동일 단어 제거 (예: "안녕 안녕 안녕" -> "안녕")
        text = re.sub(r'\b(\w+)(\s+\1\b)+', r'\1', text)

        # 연속된 동일 구문 제거 (예: "안녕하세요 안녕하세요" -> "안녕하세요")
        words = text.split()
        if len(words) < 4:
            return text

        cleaned_words = []
        i = 0
        while i < len(words):
            # 2-gram부터 5-gram까지 반복 패턴 체크
            max_pattern_length = min(5, (len(words) - i) // 2)
            pattern_found = False

            for pattern_len in range(max_pattern_length, 1, -1):
                if i + pattern_len * 2 <= len(words):
                    pattern = words[i:i+pattern_len]
                    next_pattern = words[i+pattern_len:i+pattern_len*2]

                    if pattern == next_pattern:
                        # 패턴 발견 - 한 번만 추가하고 건너뛰기
                        cleaned_words.extend(pattern)
                        i += pattern_len * 2
                        pattern_found = True
                        break

            if not pattern_found:
                cleaned_words.append(words[i])
                i += 1

        return ' '.join(cleaned_words)

    def _remove_repetitive_segments(self, segments: List[Dict]) -> List[Dict]:
        """반복되는 세그먼트 제거"""
        if len(segments) < 2:
            return segments

        cleaned_segments = []
        prev_text = None

        for segment in segments:
            current_text = segment.get('text', '').strip().lower()

            # 이전 세그먼트와 완전히 동일하거나 매우 유사한 경우 제외
            if prev_text and (
                current_text == prev_text or
                (len(current_text) > 10 and self._similarity_ratio(current_text, prev_text) > 0.8)
            ):
                continue

            cleaned_segments.append(segment)
            prev_text = current_text

        return cleaned_segments

    def _similarity_ratio(self, text1: str, text2: str) -> float:
        """두 텍스트의 유사도 계산 (0.0 ~ 1.0)"""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    def process_video(self, video_url: str, video_id: str, language: str = 'ko') -> Optional[Dict]:
        """YouTube 비디오에 대해 STT 처리"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 오디오 다운로드
            audio_file = self.download_audio(video_url, temp_dir)
            if not audio_file:
                return None

            # STT 처리
            transcript = self.transcribe_audio(audio_file, language)
            if transcript:
                transcript['video_id'] = video_id

            return transcript

    def process_videos_without_transcripts(self, video_data: List[Dict], language: str = 'ko') -> List[Dict]:
        """자막이 없는 비디오들에 대해 STT 처리"""
        results = []

        for video in video_data:
            # 이미 자막이 있는 경우 건너뛰기
            if video.get('transcript_available', True):
                results.append(video)
                continue

            print(f"STT 처리 중: {video['title']}")
            stt_result = self.process_video(video['url'], video['video_id'], language)

            if stt_result:
                # STT 결과를 비디오 정보에 추가
                video.update({
                    'transcript_available': True,
                    'language': stt_result['language'],
                    'transcript_type': stt_result['transcript_type'],
                    'full_text': stt_result['text'],
                    'transcript_data': [
                        {
                            'text': seg['text'],
                            'start': seg['start'],
                            'duration': seg['end'] - seg['start']
                        }
                        for seg in stt_result['segments']
                    ]
                })
            else:
                video['stt_failed'] = True

            results.append(video)

        return results

    def batch_process(self, video_urls: List[str], language: str = 'ko') -> List[Dict]:
        """여러 비디오에 대해 배치 STT 처리"""
        results = []

        for i, url in enumerate(video_urls):
            print(f"처리 중 ({i+1}/{len(video_urls)}): {url}")

            # 비디오 ID 추출
            from .youtube_extractor import YouTubeExtractor
            extractor = YouTubeExtractor()
            video_id = extractor.extract_video_id(url)

            if not video_id:
                print(f"비디오 ID 추출 실패: {url}")
                continue

            stt_result = self.process_video(url, video_id, language)
            if stt_result:
                stt_result['url'] = url
                results.append(stt_result)

        return results