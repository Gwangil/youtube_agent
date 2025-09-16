"""
Podcast Agent 메인 CLI 인터페이스
YouTube 채널에서 자막 추출 및 STT 처리를 위한 명령줄 도구
"""

import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

from .youtube_extractor import YouTubeExtractor
from .stt_processor import STTProcessor


def main():
    parser = argparse.ArgumentParser(
        description="YouTube 채널에서 자막을 추출하고 STT 처리를 수행합니다."
    )

    parser.add_argument(
        "channel_url",
        help="YouTube 채널 URL (예: https://www.youtube.com/channel/...)"
    )

    parser.add_argument(
        "--max-videos",
        type=int,
        default=50,
        help="처리할 최대 비디오 수 (기본: 50)"
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="출력 디렉토리 (기본: output)"
    )

    parser.add_argument(
        "--language",
        default="ko",
        help="자막 언어 (기본: ko)"
    )

    parser.add_argument(
        "--enable-stt",
        action="store_true",
        help="자막이 없는 비디오에 대해 STT 처리 활성화"
    )

    parser.add_argument(
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper 모델 크기 (기본: base)"
    )

    parser.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="both",
        help="출력 형식 (기본: both)"
    )

    args = parser.parse_args()

    # 출력 디렉토리 생성
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"🎥 YouTube 채널 처리 시작: {args.channel_url}")
    print(f"📁 출력 디렉토리: {args.output_dir}")
    print(f"🔢 최대 비디오 수: {args.max_videos}")
    print(f"🌐 언어: {args.language}")
    print(f"🎤 STT 처리: {'활성화' if args.enable_stt else '비활성화'}")

    # YouTube 자막 추출
    extractor = YouTubeExtractor(args.output_dir)
    print("\n📋 채널에서 자막 추출 중...")

    try:
        results = extractor.extract_channel_transcripts(
            args.channel_url,
            args.max_videos
        )

        if not results:
            print("❌ 자막을 추출할 수 있는 비디오가 없습니다.")
            return

        print(f"✅ {len(results)}개 비디오 처리 완료")

        # 자막이 없는 비디오 수 계산
        no_transcript_count = sum(1 for r in results if not r.get('transcript_available', True))
        print(f"📊 자막 있음: {len(results) - no_transcript_count}개")
        print(f"📊 자막 없음: {no_transcript_count}개")

        # STT 처리 (요청된 경우)
        if args.enable_stt and no_transcript_count > 0:
            print(f"\n🎤 자막이 없는 {no_transcript_count}개 비디오에 대해 STT 처리 중...")

            stt_processor = STTProcessor(
                model_size=args.whisper_model,
                output_dir=args.output_dir
            )

            results = stt_processor.process_videos_without_transcripts(
                results,
                args.language
            )

            print("✅ STT 처리 완료")

        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"youtube_transcripts_{timestamp}"

        print(f"\n💾 결과 저장 중...")

        if args.format in ["csv", "both"]:
            csv_file = extractor.save_to_csv(results, f"{base_filename}.csv")
            if csv_file:
                print(f"📄 CSV 파일 저장: {csv_file}")

        if args.format in ["json", "both"]:
            json_file = extractor.save_to_json(results, f"{base_filename}.json")
            if json_file:
                print(f"📄 JSON 파일 저장: {json_file}")

        # 요약 정보 출력
        print(f"\n📈 처리 완료 요약:")
        print(f"   총 비디오: {len(results)}개")
        print(f"   자막 추출 성공: {sum(1 for r in results if r.get('transcript_available', False))}개")

        if args.enable_stt:
            stt_success = sum(1 for r in results if r.get('transcript_type') == 'stt_whisper')
            print(f"   STT 처리 성공: {stt_success}개")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


def process_single_video():
    """단일 비디오 처리를 위한 별도 함수"""
    parser = argparse.ArgumentParser(
        description="단일 YouTube 비디오에서 자막을 추출하거나 STT 처리를 수행합니다."
    )

    parser.add_argument(
        "video_url",
        help="YouTube 비디오 URL"
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="출력 디렉토리 (기본: output)"
    )

    parser.add_argument(
        "--language",
        default="ko",
        help="자막 언어 (기본: ko)"
    )

    parser.add_argument(
        "--force-stt",
        action="store_true",
        help="자막이 있어도 STT 처리 강제 실행"
    )

    parser.add_argument(
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper 모델 크기 (기본: base)"
    )

    args = parser.parse_args()

    # 출력 디렉토리 생성
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"🎥 단일 비디오 처리: {args.video_url}")

    extractor = YouTubeExtractor(args.output_dir)
    video_id = extractor.extract_video_id(args.video_url)

    if not video_id:
        print("❌ 유효하지 않은 YouTube URL입니다.")
        return

    # 자막 추출 시도
    transcript = extractor.extract_transcript(video_id, [args.language])

    if transcript and not args.force_stt:
        print("✅ 자막 추출 성공")
        result = transcript
    else:
        if not transcript:
            print("📋 자막이 없습니다. STT 처리를 시작합니다...")
        else:
            print("🎤 STT 처리 강제 실행...")

        # STT 처리
        stt_processor = STTProcessor(
            model_size=args.whisper_model,
            output_dir=args.output_dir
        )

        result = stt_processor.process_video(args.video_url, video_id, args.language)

        if result:
            print("✅ STT 처리 성공")
        else:
            print("❌ STT 처리 실패")
            return

    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_{video_id}_{timestamp}.json"

    import json
    filepath = os.path.join(args.output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"💾 결과 저장: {filepath}")


if __name__ == "__main__":
    main()