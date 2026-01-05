"""Audio overlay service using FFmpeg."""

import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

from app.core.config import Config
from app.core.exceptions import AudioGenerationError, VideoGenerationError

logger = logging.getLogger(__name__)


class AudioOverlayService:
    """Service for overlaying audio onto video clips using FFmpeg."""

    def __init__(self, config: Config):
        """Initialize audio overlay service.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.max_duration = config.settings.max_video_duration

    def overlay_audio_on_video(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        trim_to_audio: bool = True
    ) -> Tuple[str, float]:
        """Overlay audio onto a video file.

        Args:
            video_path: Path to input video file.
            audio_path: Path to audio file.
            output_path: Path to save output video.
            trim_to_audio: If True, trim video to match audio duration.

        Returns:
            Tuple of (output_path, duration_in_seconds).

        Raises:
            VideoGenerationError: If overlay fails.
        """
        try:
            logger.info(f"Overlaying audio onto video: {Path(video_path).name}")

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Build FFmpeg command
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',  # Copy video stream (no re-encoding)
                '-c:a', 'aac',  # AAC audio codec
                '-b:a', '128k',  # Audio bitrate
                '-map', '0:v:0',  # Map video from first input
                '-map', '1:a:0',  # Map audio from second input
            ]

            if trim_to_audio:
                # Trim video to audio length
                cmd.extend(['-shortest'])

            cmd.append(str(output_file))

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                raise VideoGenerationError(f"Audio overlay failed: {result.stderr[:500]}")

            # Get output duration
            duration = self._get_video_duration(str(output_file))

            logger.info(f"Audio overlay complete: {duration:.1f}s")
            return str(output_file), duration

        except subprocess.TimeoutExpired:
            raise VideoGenerationError("Audio overlay timed out")
        except Exception as e:
            if isinstance(e, VideoGenerationError):
                raise
            raise VideoGenerationError(f"Failed to overlay audio: {str(e)}")

    def concatenate_clips_with_audio(
        self,
        video_clips: List[str],
        audio_path: str,
        output_path: str
    ) -> Tuple[str, float]:
        """Concatenate multiple video clips and overlay audio.

        Args:
            video_clips: List of video clip paths (in order).
            audio_path: Path to audio file.
            output_path: Path to save final video.

        Returns:
            Tuple of (output_path, duration_in_seconds).

        Raises:
            VideoGenerationError: If concatenation fails.
        """
        try:
            logger.info(f"Concatenating {len(video_clips)} clips with audio...")

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Step 1: Create concat file list
            concat_file = output_file.parent / "concat_list.txt"
            with open(concat_file, 'w') as f:
                for clip_path in video_clips:
                    # FFmpeg concat format requires relative or absolute paths
                    abs_path = str(Path(clip_path).resolve())
                    f.write(f"file '{abs_path}'\n")

            # Step 2: Concatenate videos and add audio
            cmd = [
                'ffmpeg',
                '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-i', audio_path,
                '-c:v', 'libx264',  # Re-encode video for compatibility
                '-preset', 'fast',
                '-crf', '23',  # Quality (lower = better, 18-28 range)
                '-c:a', 'aac',
                '-b:a', '128k',
                '-map', '0:v:0',  # Video from concat
                '-map', '1:a:0',  # Audio from audio file
                '-shortest',  # Trim to shortest stream (audio)
                str(output_file)
            ]

            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg concatenation error: {result.stderr}")
                raise VideoGenerationError(f"Video concatenation failed: {result.stderr[:500]}")

            # Clean up concat file
            concat_file.unlink(missing_ok=True)

            # Get output duration
            duration = self._get_video_duration(str(output_file))

            # Validate duration
            if duration >= self.max_duration:
                logger.warning(
                    f"Video duration ({duration}s) exceeds YouTube Shorts limit ({self.max_duration}s)"
                )

            logger.info(f"Concatenation complete: {duration:.1f}s, size: {output_file.stat().st_size / (1024*1024):.2f} MB")
            return str(output_file), duration

        except subprocess.TimeoutExpired:
            raise VideoGenerationError("Video concatenation timed out")
        except Exception as e:
            if isinstance(e, VideoGenerationError):
                raise
            raise VideoGenerationError(f"Failed to concatenate clips: {str(e)}")

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe.

        Args:
            video_path: Path to video file.

        Returns:
            Duration in seconds.

        Raises:
            VideoGenerationError: If duration cannot be determined.
        """
        try:
            import json

            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                raise VideoGenerationError(f"ffprobe failed: {result.stderr}")

            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])

            return duration

        except json.JSONDecodeError as e:
            raise VideoGenerationError(f"Failed to parse ffprobe output: {str(e)}")
        except Exception as e:
            raise VideoGenerationError(f"Failed to get video duration: {str(e)}")

    def normalize_audio(self, audio_path: str, target_db: float = -20.0) -> str:
        """Normalize audio volume using FFmpeg.

        Args:
            audio_path: Path to audio file.
            target_db: Target loudness in dB (default: -20.0).

        Returns:
            Path to normalized audio file.

        Raises:
            AudioGenerationError: If normalization fails.
        """
        try:
            logger.info(f"Normalizing audio to {target_db} dB...")

            input_file = Path(audio_path)
            output_file = input_file.parent / f"{input_file.stem}_normalized{input_file.suffix}"

            cmd = [
                'ffmpeg',
                '-y',
                '-i', str(input_file),
                '-af', f'loudnorm=I={target_db}:TP=-1.5:LRA=11',
                '-ar', '44100',
                str(output_file)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.warning(f"Audio normalization failed: {result.stderr}. Using original.")
                return str(input_file)

            logger.info("Audio normalized successfully")
            return str(output_file)

        except Exception as e:
            logger.warning(f"Audio normalization failed: {e}. Using original.")
            return audio_path

    def add_fade_transitions(
        self,
        video_path: str,
        output_path: str,
        fade_duration: float = 0.5
    ) -> str:
        """Add fade in/out transitions to video.

        Args:
            video_path: Path to input video.
            output_path: Path to save output.
            fade_duration: Fade duration in seconds.

        Returns:
            Path to output video.

        Raises:
            VideoGenerationError: If adding transitions fails.
        """
        try:
            logger.info(f"Adding fade transitions ({fade_duration}s)...")

            # Get video duration first
            duration = self._get_video_duration(video_path)

            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-vf', f'fade=t=in:st=0:d={fade_duration},fade=t=out:st={duration-fade_duration}:d={fade_duration}',
                '-af', f'afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration-fade_duration}:d={fade_duration}',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-c:a', 'aac',
                output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                logger.warning(f"Failed to add transitions: {result.stderr}")
                return video_path

            logger.info("Fade transitions added successfully")
            return output_path

        except Exception as e:
            logger.warning(f"Failed to add transitions: {e}. Using original.")
            return video_path
