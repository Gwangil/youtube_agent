#!/usr/bin/env python3
"""
개선된 STT 워커 v2
- GPU 서버 우선 사용 (타임아웃 증가)
- 대용량 파일 청크 분할 처리
- 비동기 처리 지원
"""

import os
import sys
import time
import hashlib
import asyncio
import aiohttp
import subprocess
import tempfile
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import numpy as np

sys.path.append('/app')
sys.path.append('/app/shared')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.database import (
    ProcessingJob, Content, Transcript,
    get_database_url
)

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ImprovedSTTWorkerV2:
    """개선된 STT 워커 V2 - 대용량 파일 처리 최적화"""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.whisper_server_url = os.getenv('WHISPER_SERVER_URL', 'http://whisper-server:8082')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')

        # 데이터베이스 연결
        self.engine = create_engine(get_database_url())
        self.SessionLocal = sessionmaker(bind=self.engine)

        # 청크 설정 (10분 = 600초)
        self.chunk_duration = 600  # 10분 단위로 분할
        self.max_file_duration = 3600  # 1시간 이상은 분할 처리

        # 타임아웃 설정
        self.whisper_health_timeout = 10
        self.whisper_process_timeout = 1800  # 30분 (대용량 처리 고려)

        logger.info(f"🚀 STT Worker V2 #{self.worker_id} 초기화 완료")
        self._check_whisper_server()

    def _check_whisper_server(self):
        """Whisper 서버 상태 확인"""
        import requests
        try:
            response = requests.get(
                f"{self.whisper_server_url}/health",
                timeout=self.whisper_health_timeout
            )
            if response.status_code == 200:
                logger.info(f"✅ Whisper 서버 연결됨: {self.whisper_server_url}")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Whisper 서버 연결 실패: {e}")
        return False

    def _get_audio_duration(self, audio_file: str) -> float:
        """오디오 파일 길이 확인"""
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"오디오 길이 확인 실패: {e}")
            return 0

    def _split_audio(self, audio_file: str, chunk_duration: int = 600) -> List[str]:
        """오디오 파일을 청크로 분할"""
        duration = self._get_audio_duration(audio_file)
        if duration <= chunk_duration:
            return [audio_file]

        chunks = []
        num_chunks = int(np.ceil(duration / chunk_duration))

        logger.info(f"📚 오디오 분할: {duration:.1f}초 -> {num_chunks}개 청크")

        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_file = f"{audio_file}_chunk_{i}.wav"

            # FFmpeg로 청크 추출
            cmd = [
                'ffmpeg', '-i', audio_file,
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y', chunk_file
            ]

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            chunks.append((chunk_file, start_time))

        return chunks

    async def _process_chunk_async(self, chunk_file: str, offset: float, language: str = 'ko') -> Optional[dict]:
        """청크를 비동기로 처리"""
        import aiofiles
        import requests

        try:
            # Whisper 서버로 전송
            async with aiohttp.ClientSession() as session:
                # 파일 읽기
                async with aiofiles.open(chunk_file, 'rb') as f:
                    audio_data = await f.read()

                # FormData 생성
                data = aiohttp.FormData()
                data.add_field('audio', audio_data,
                              filename=os.path.basename(chunk_file),
                              content_type='audio/wav')
                data.add_field('language', language)

                # 비동기 요청 (긴 타임아웃)
                async with session.post(
                    f"{self.whisper_server_url}/transcribe",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=self.whisper_process_timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()

                        # 오프셋 적용
                        if 'segments' in result:
                            for segment in result['segments']:
                                segment['start'] += offset
                                segment['end'] += offset

                        return result
                    else:
                        logger.error(f"Whisper 서버 오류: {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error(f"청크 처리 타임아웃 ({self.whisper_process_timeout}초)")
            return None
        except Exception as e:
            logger.error(f"청크 처리 실패: {e}")
            return None
        finally:
            # 임시 파일 정리
            if chunk_file != chunk_file and os.path.exists(chunk_file):
                os.remove(chunk_file)

    def _process_with_whisper_server(self, audio_file: str, language: str = 'ko') -> Optional[dict]:
        """Whisper 서버로 처리 (청크 분할 지원)"""
        try:
            duration = self._get_audio_duration(audio_file)

            # 작은 파일은 직접 처리
            if duration <= self.max_file_duration:
                logger.info(f"🎯 단일 파일 처리: {duration:.1f}초")
                return self._process_single_file(audio_file, language)

            # 대용량 파일은 분할 처리
            logger.info(f"📂 대용량 파일 분할 처리: {duration:.1f}초")
            chunks = self._split_audio(audio_file, self.chunk_duration)

            # 비동기 처리를 위한 이벤트 루프
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 모든 청크를 비동기로 처리
            tasks = []
            for chunk_file, offset in chunks:
                task = self._process_chunk_async(chunk_file, offset, language)
                tasks.append(task)

            # 결과 수집
            results = loop.run_until_complete(asyncio.gather(*tasks))
            loop.close()

            # 결과 병합
            merged_result = self._merge_results(results)

            # 청크 파일 정리
            for chunk_file, _ in chunks:
                if os.path.exists(chunk_file):
                    os.remove(chunk_file)

            return merged_result

        except Exception as e:
            logger.error(f"Whisper 서버 처리 실패: {e}")
            return None

    def _process_single_file(self, audio_file: str, language: str = 'ko') -> Optional[dict]:
        """단일 파일 처리"""
        import requests

        try:
            with open(audio_file, 'rb') as f:
                files = {'audio': (os.path.basename(audio_file), f, 'audio/wav')}
                data = {'language': language}

                response = requests.post(
                    f"{self.whisper_server_url}/transcribe",
                    files=files,
                    data=data,
                    timeout=self.whisper_process_timeout
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Whisper 서버 응답 오류: {response.status_code}")
                    return None

        except requests.exceptions.Timeout:
            logger.error(f"Whisper 서버 타임아웃 ({self.whisper_process_timeout}초)")
            return None
        except Exception as e:
            logger.error(f"단일 파일 처리 실패: {e}")
            return None

    def _merge_results(self, results: List[Optional[dict]]) -> dict:
        """청크 결과 병합"""
        merged = {
            'text': '',
            'segments': [],
            'language': 'ko'
        }

        for result in results:
            if result:
                merged['text'] += ' ' + result.get('text', '')
                merged['segments'].extend(result.get('segments', []))
                if 'language' in result:
                    merged['language'] = result['language']

        merged['text'] = merged['text'].strip()

        # 세그먼트 정렬
        merged['segments'].sort(key=lambda x: x.get('start', 0))

        logger.info(f"✅ 결과 병합 완료: {len(merged['segments'])} 세그먼트")

        return merged

    def _fallback_to_openai(self, audio_file: str, language: str = 'ko') -> Optional[dict]:
        """OpenAI API 폴백"""
        if not self.openai_api_key:
            logger.error("OpenAI API 키가 설정되지 않음")
            return None

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

            # 파일 크기 확인 (OpenAI 제한: 25MB)
            file_size = os.path.getsize(audio_file) / (1024 * 1024)
            if file_size > 25:
                logger.error(f"파일이 너무 큼 ({file_size:.1f}MB > 25MB)")
                return None

            with open(audio_file, 'rb') as audio:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language=language,
                    response_format="verbose_json"
                )

            # OpenAI 응답을 우리 포맷으로 변환
            result = {
                'text': response.text,
                'segments': []
            }

            # 세그먼트 정보가 있으면 추가
            if hasattr(response, 'segments'):
                result['segments'] = response.segments

            return result

        except Exception as e:
            logger.error(f"OpenAI API 처리 실패: {e}")
            return None

    def process_job(self, job: ProcessingJob):
        """STT 작업 처리"""
        db = self.SessionLocal()

        try:
            # 작업 상태 업데이트
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            db.commit()

            # 콘텐츠 조회
            content = db.query(Content).filter_by(id=job.content_id).first()
            if not content:
                raise ValueError(f"Content {job.content_id} not found")

            logger.info(f"🎙️ STT 처리 시작: {content.title[:50]}...")

            # 오디오 다운로드
            audio_file = self._download_audio(content.url)
            if not audio_file:
                raise ValueError("오디오 다운로드 실패")

            # STT 처리 (GPU 서버 우선, OpenAI 폴백)
            result = self._process_with_whisper_server(audio_file)

            if not result and self.openai_api_key:
                logger.info("OpenAI API로 폴백...")
                result = self._fallback_to_openai(audio_file)

            if not result:
                raise ValueError("STT 처리 실패")

            # 트랜스크립트 저장
            self._save_transcripts(db, content, result)

            # 벡터화 작업 생성
            vector_job = ProcessingJob(
                job_type='vectorize',
                content_id=content.id,
                status='pending',
                priority=10
            )
            db.add(vector_job)

            # 작업 완료
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.commit()

            logger.info(f"✅ STT 처리 완료: {content.title[:50]}...")

            # 임시 파일 정리
            if os.path.exists(audio_file):
                os.remove(audio_file)

        except Exception as e:
            logger.error(f"STT 작업 실패: {e}")
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    def _download_audio(self, url: str) -> Optional[str]:
        """YouTube 오디오 다운로드"""
        try:
            import yt_dlp

            output_dir = '/tmp/youtube_audio'
            os.makedirs(output_dir, exist_ok=True)

            output_file = os.path.join(output_dir, f"{hashlib.md5(url.encode()).hexdigest()}.wav")

            # 이미 다운로드된 파일이 있으면 재사용
            if os.path.exists(output_file):
                logger.info(f"캐시된 오디오 사용: {output_file}")
                return output_file

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_file,
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                }],
                'postprocessor_args': [
                    '-ar', '16000',  # 16kHz 샘플링
                    '-ac', '1'       # 모노
                ]
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # 변환된 파일 찾기
            for file in os.listdir(output_dir):
                if file.startswith(os.path.basename(output_file)):
                    full_path = os.path.join(output_dir, file)
                    # WAV 파일로 이름 변경
                    if not full_path.endswith('.wav'):
                        new_path = output_file
                        os.rename(full_path, new_path)
                        return new_path
                    return full_path

            return None

        except Exception as e:
            logger.error(f"오디오 다운로드 실패: {e}")
            return None

    def _save_transcripts(self, db, content: Content, result: dict):
        """트랜스크립트 저장"""
        segments = result.get('segments', [])

        # 기존 트랜스크립트 삭제
        db.query(Transcript).filter_by(content_id=content.id).delete()

        # 세그먼트 저장
        for i, segment in enumerate(segments):
            transcript = Transcript(
                content_id=content.id,
                text=segment.get('text', ''),
                start_time=segment.get('start', 0),
                end_time=segment.get('end', 0),
                segment_order=i
            )
            db.add(transcript)

        # 콘텐츠 업데이트
        content.transcript_available = True
        content.transcript_type = 'stt_whisper'
        content.language = result.get('language', 'ko')

        db.commit()
        logger.info(f"💾 {len(segments)}개 세그먼트 저장 완료")

    def start_worker(self):
        """워커 시작"""
        logger.info(f"🚀 STT Worker V2 #{self.worker_id} 시작")

        while True:
            try:
                db = self.SessionLocal()

                # 대기 중인 작업 조회
                jobs = db.query(ProcessingJob).filter(
                    ProcessingJob.job_type.in_(['process_audio', 'extract_transcript']),
                    ProcessingJob.status == 'pending'
                ).order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at
                ).limit(1).all()

                if jobs:
                    job = jobs[0]
                    logger.info(f"🎯 작업 선택: Job {job.id}")
                    self.process_job(job)
                else:
                    logger.debug(f"대기 중인 작업 없음")

                db.close()
                time.sleep(10)

            except Exception as e:
                logger.error(f"워커 오류: {e}")
                time.sleep(30)


if __name__ == "__main__":
    worker_id = int(os.getenv('STT_WORKER_ID', '0'))
    worker = ImprovedSTTWorkerV2(worker_id=worker_id)
    worker.start_worker()