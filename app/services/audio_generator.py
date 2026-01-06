"""Audio generation service using ElevenLabs or OpenAI TTS."""

import logging
import subprocess
import json
from pathlib import Path
from typing import List, Tuple
from openai import OpenAI
from elevenlabs import ElevenLabs

from app.core.config import Config
from app.core.exceptions import AudioGenerationError, DurationExceededError
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class AudioGenerator:
    """Generates audio narration using ElevenLabs or OpenAI Text-to-Speech."""

    def __init__(self, config: Config):
        """Initialize audio generator.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.audio_config = config.audio_generation
        self.max_duration = config.settings.max_video_duration

        # Initialize TTS clients based on provider
        self.provider = self.audio_config.provider.lower()

        if self.provider == "elevenlabs":
            self.elevenlabs_client = ElevenLabs(api_key=config.settings.elevenlabs_api_key)
            logger.info("Initialized ElevenLabs TTS")
        elif self.provider == "openai_tts":
            self.openai_client = OpenAI(api_key=config.settings.openai_api_key)
            logger.info("Initialized OpenAI TTS")
        else:
            raise AudioGenerationError(f"Unknown TTS provider: {self.provider}")

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration using ffprobe.

        Args:
            audio_path: Path to audio file.

        Returns:
            Duration in seconds.

        Raises:
            AudioGenerationError: If ffprobe fails.
        """
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    audio_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data['format']['duration'])
                return duration
            else:
                raise AudioGenerationError(f"ffprobe failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise AudioGenerationError("ffprobe timed out")
        except Exception as e:
            raise AudioGenerationError(f"Failed to get audio duration: {str(e)}")

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    def generate_audio(
        self,
        text: str,
        output_path: str,
        validate_duration: bool = True,
        voice: str = None
    ) -> Tuple[str, float]:
        """Generate audio from text using configured TTS provider.

        Args:
            text: Text to convert to speech.
            output_path: Path to save audio file.
            validate_duration: Whether to validate duration against max.
            voice: Voice to use (provider-specific, uses config if None).

        Returns:
            Tuple of (output_path, duration_in_seconds).

        Raises:
            AudioGenerationError: If audio generation fails.
            DurationExceededError: If audio duration exceeds maximum.
        """
        try:
            if not text or not text.strip():
                raise AudioGenerationError("Text cannot be empty")

            # Use configured voice if not specified
            if voice is None:
                voice = self.audio_config.voice

            # Save to file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            final_path = str(output_file.with_suffix('.mp3'))

            # Generate audio based on provider
            if self.provider == "elevenlabs":
                logger.info(f"Generating audio with ElevenLabs (voice: {voice})")
                self._generate_elevenlabs(text, final_path, voice)
            elif self.provider == "openai_tts":
                logger.info(f"Generating audio with OpenAI TTS (voice: {voice})")
                self._generate_openai(text, final_path, voice)
            else:
                raise AudioGenerationError(f"Unknown TTS provider: {self.provider}")

            # Get audio duration using ffprobe
            duration = self._get_audio_duration(final_path)

            # Validate duration
            if validate_duration and duration >= self.max_duration:
                logger.error(f"Audio duration ({duration}s) exceeds maximum ({self.max_duration}s)")
                Path(final_path).unlink(missing_ok=True)
                raise DurationExceededError(
                    f"Audio duration {duration:.1f}s exceeds maximum {self.max_duration}s",
                    details={"duration": duration, "max_duration": self.max_duration}
                )

            logger.info(f"Audio generated successfully: {duration:.1f}s, saved to {final_path}")
            return final_path, duration

        except DurationExceededError:
            raise
        except Exception as e:
            raise AudioGenerationError(f"Failed to generate audio: {str(e)}")

    def _generate_elevenlabs(self, text: str, output_path: str, voice_id: str):
        """Generate audio using ElevenLabs.

        Args:
            text: Text to convert to speech.
            output_path: Path to save audio file.
            voice_id: ElevenLabs voice ID.
        """
        try:
            # Generate audio using ElevenLabs
            audio_generator = self.elevenlabs_client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",  # High quality model
                output_format="mp3_44100_128"  # MP3 format, 44.1kHz, 128kbps
            )

            # Save audio to file
            with open(output_path, 'wb') as f:
                for chunk in audio_generator:
                    f.write(chunk)

        except Exception as e:
            raise AudioGenerationError(f"ElevenLabs generation failed: {str(e)}")

    def _generate_openai(self, text: str, output_path: str, voice: str):
        """Generate audio using OpenAI TTS.

        Args:
            text: Text to convert to speech.
            output_path: Path to save audio file.
            voice: OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer).
        """
        try:
            # Generate audio using OpenAI TTS
            response = self.openai_client.audio.speech.create(
                model="tts-1-hd",  # High quality model
                voice=voice,
                input=text,
                speed=1.0  # Normal speed
            )

            # Save the audio file
            response.stream_to_file(output_path)

        except Exception as e:
            raise AudioGenerationError(f"OpenAI TTS generation failed: {str(e)}")

    def generate_from_scenes(
        self,
        scenes: List[dict],
        output_dir: str,
        filename: str = "voiceover.mp3"
    ) -> Tuple[str, float]:
        """Generate audio from scene voiceovers.

        Args:
            scenes: List of scene dictionaries with voiceover text.
            output_dir: Directory to save audio file.
            filename: Output filename.

        Returns:
            Tuple of (output_path, duration_in_seconds).

        Raises:
            AudioGenerationError: If audio generation fails.
        """
        try:
            logger.info(f"Generating audio from {len(scenes)} scenes")

            # Concatenate all voiceover text
            voiceover_texts = []
            for scene in scenes:
                voiceover = scene.get("voiceover", "").strip()
                if voiceover:
                    voiceover_texts.append(voiceover)

            if not voiceover_texts:
                raise AudioGenerationError("No voiceover text found in scenes")

            # Join with appropriate pauses
            full_text = " ".join(voiceover_texts)

            # Generate audio with configured voice
            output_path = Path(output_dir) / filename
            return self.generate_audio(
                text=full_text,
                output_path=str(output_path),
                validate_duration=True,
                voice=self.audio_config.voice
            )

        except Exception as e:
            if isinstance(e, (AudioGenerationError, DurationExceededError)):
                raise
            raise AudioGenerationError(f"Failed to generate audio from scenes: {str(e)}")

    def estimate_duration(self, text: str) -> float:
        """Estimate audio duration from text.

        Args:
            text: Text to estimate duration for.

        Returns:
            Estimated duration in seconds.

        Note:
            This is a rough estimate based on average speaking rate.
            Actual duration may vary.
        """
        # Average speaking rate: ~150 words per minute = 2.5 words per second
        word_count = len(text.split())
        estimated_duration = word_count / 2.5

        return round(estimated_duration, 1)

    def validate_text_length(self, text: str, max_duration: int = None) -> bool:
        """Validate if text length is appropriate for target duration.

        Args:
            text: Text to validate.
            max_duration: Maximum allowed duration in seconds.

        Returns:
            True if valid, False otherwise.
        """
        if max_duration is None:
            max_duration = self.max_duration

        estimated = self.estimate_duration(text)
        return estimated < max_duration

    def get_audio_info(self, audio_path: str) -> dict:
        """Get information about an audio file.

        Args:
            audio_path: Path to audio file.

        Returns:
            Dictionary with audio information.

        Raises:
            AudioGenerationError: If file cannot be read.
        """
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    audio_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                raise AudioGenerationError(f"ffprobe failed: {result.stderr}")

            data = json.loads(result.stdout)
            format_info = data['format']
            audio_stream = data['streams'][0] if data['streams'] else {}

            return {
                "duration_seconds": float(format_info.get('duration', 0)),
                "sample_rate": int(audio_stream.get('sample_rate', 0)),
                "channels": int(audio_stream.get('channels', 0)),
                "bit_rate": int(format_info.get('bit_rate', 0)),
                "format": Path(audio_path).suffix[1:],
                "file_size_mb": Path(audio_path).stat().st_size / (1024 * 1024)
            }

        except Exception as e:
            raise AudioGenerationError(f"Failed to get audio info: {str(e)}")

    def trim_audio(self, audio_path: str, max_duration: float) -> str:
        """Trim audio to maximum duration.

        Args:
            audio_path: Path to audio file.
            max_duration: Maximum duration in seconds.

        Returns:
            Path to trimmed audio file.

        Raises:
            AudioGenerationError: If trimming fails.
        """
        try:
            logger.info(f"Trimming audio to {max_duration}s")

            # Create temp file for trimmed audio
            temp_path = str(Path(audio_path).with_suffix('.temp.mp3'))

            # Use ffmpeg to trim and add fade out
            fade_duration = min(0.5, max_duration * 0.1)  # 500ms or 10% of duration
            fade_start = max_duration - fade_duration

            result = subprocess.run(
                [
                    'ffmpeg', '-y',
                    '-i', audio_path,
                    '-t', str(max_duration),
                    '-af', f'afade=t=out:st={fade_start}:d={fade_duration}',
                    '-c:a', 'libmp3lame',
                    temp_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise AudioGenerationError(f"ffmpeg failed: {result.stderr}")

            # Replace original with trimmed version
            Path(audio_path).unlink()
            Path(temp_path).rename(audio_path)

            actual_duration = self._get_audio_duration(audio_path)
            logger.info(f"Audio trimmed successfully to {actual_duration:.1f}s")
            return audio_path

        except Exception as e:
            # Clean up temp file if it exists
            Path(temp_path).unlink(missing_ok=True) if 'temp_path' in locals() else None
            raise AudioGenerationError(f"Failed to trim audio: {str(e)}")
