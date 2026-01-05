"""Video generation service using Google Gemini Veo 3.1."""

import logging
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.config import Config
from app.core.exceptions import VideoGenerationError, VideoAPIError, RateLimitError
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class VideoGenerator:
    """Generates videos using Google Gemini Veo 3.1."""

    def __init__(self, config: Config):
        """Initialize video generator.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.video_config = config.video_generation
        self.gemini_config = config.video_generation.gemini
        self.api_key = config.settings.gemini_api_key

        # Gemini API endpoints
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.headers = {
            "Content-Type": "application/json"
        }

    @retry_with_backoff(
        max_attempts=3,
        base_delay=5.0,
        exceptions=(VideoAPIError, RateLimitError)
    )
    def generate_video_clip(
        self,
        prompt: str,
        output_path: str,
        scene_id: int = 1
    ) -> Tuple[str, float]:
        """Generate a single video clip from a prompt.

        Args:
            prompt: Text prompt for video generation.
            output_path: Path to save the video clip.
            scene_id: Scene identifier for logging.

        Returns:
            Tuple of (video_path, duration_in_seconds).

        Raises:
            VideoGenerationError: If video generation fails.
        """
        try:
            logger.info(f"[Scene {scene_id}] Generating video clip: {prompt[:100]}...")

            # Step 1: Create generation request
            generation_name = self._create_generation(prompt, scene_id)

            # Step 2: Poll for completion
            video_data = self._poll_generation_status(generation_name, scene_id)

            # Step 3: Download video
            output_file = self._download_video(video_data, output_path, scene_id)

            # Step 4: Get video duration
            duration = self._get_video_duration(output_file)

            logger.info(f"[Scene {scene_id}] Video generated successfully: {duration:.1f}s")
            return output_file, duration

        except Exception as e:
            if isinstance(e, (VideoGenerationError, VideoAPIError, RateLimitError)):
                raise
            raise VideoGenerationError(f"Failed to generate video clip: {str(e)}")

    def _create_generation(self, prompt: str, scene_id: int) -> str:
        """Create a video generation request.

        Args:
            prompt: Text prompt.
            scene_id: Scene identifier.

        Returns:
            Generation resource name.

        Raises:
            VideoAPIError: If API request fails.
        """
        try:
            payload = {
                "prompt": prompt,
                "videoGenerationConfig": {
                    "aspectRatio": self.gemini_config.aspect_ratio,
                    "duration": f"{self.gemini_config.duration_per_clip}s",
                    "model": self.gemini_config.model
                }
            }

            url = f"{self.base_url}/models/{self.gemini_config.model}:generateVideo?key={self.api_key}"

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 429:
                raise RateLimitError("Gemini API rate limit exceeded")
            elif response.status_code == 401 or response.status_code == 403:
                raise VideoAPIError("Gemini API authentication failed. Check your API key.")
            elif response.status_code != 200:
                raise VideoAPIError(f"Gemini API error: {response.status_code} - {response.text}")

            data = response.json()
            generation_name = data.get("name")

            if not generation_name:
                raise VideoAPIError("No generation name returned from Gemini API")

            logger.info(f"[Scene {scene_id}] Generation started: {generation_name}")
            return generation_name

        except requests.exceptions.Timeout:
            raise VideoAPIError("Gemini API request timed out")
        except requests.exceptions.RequestException as e:
            raise VideoAPIError(f"Gemini API request failed: {str(e)}")

    def _poll_generation_status(self, generation_name: str, scene_id: int) -> Dict[str, Any]:
        """Poll for generation completion.

        Args:
            generation_name: Generation resource name.
            scene_id: Scene identifier.

        Returns:
            Video data from completed generation.

        Raises:
            VideoAPIError: If polling fails or times out.
        """
        start_time = time.time()
        poll_interval = self.video_config.poll_interval_seconds
        max_wait = self.video_config.timeout_seconds

        while True:
            elapsed = time.time() - start_time

            if elapsed > max_wait:
                raise VideoAPIError(
                    f"Video generation timed out after {max_wait}s. "
                    f"Generation: {generation_name}"
                )

            try:
                url = f"{self.base_url}/{generation_name}?key={self.api_key}"

                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=30
                )

                if response.status_code != 200:
                    raise VideoAPIError(f"Failed to check status: {response.status_code}")

                data = response.json()
                state = data.get("state", "UNKNOWN")

                logger.debug(f"[Scene {scene_id}] Status: {state} ({elapsed:.0f}s)")

                if state == "SUCCEEDED":
                    video_data = data.get("videoData")
                    if not video_data:
                        raise VideoAPIError("No video data in completed generation")

                    logger.info(f"[Scene {scene_id}] Generation completed in {elapsed:.1f}s")
                    return video_data

                elif state == "FAILED":
                    error = data.get("error", {}).get("message", "Unknown error")
                    raise VideoAPIError(f"Video generation failed: {error}")

                elif state in ["PENDING", "PROCESSING"]:
                    time.sleep(poll_interval)
                    continue

                else:
                    logger.warning(f"[Scene {scene_id}] Unknown status: {state}")
                    time.sleep(poll_interval)

            except requests.exceptions.RequestException as e:
                logger.warning(f"Polling error: {e}. Retrying in {poll_interval}s...")
                time.sleep(poll_interval)

    def _download_video(self, video_data: Dict[str, Any], output_path: str, scene_id: int) -> str:
        """Download video from base64 data or URL.

        Args:
            video_data: Video data from API.
            output_path: Path to save video.
            scene_id: Scene identifier.

        Returns:
            Path to downloaded video file.

        Raises:
            VideoAPIError: If download fails.
        """
        try:
            import base64

            logger.info(f"[Scene {scene_id}] Downloading video...")

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Gemini returns video as base64 encoded data
            if "videoBase64" in video_data:
                video_bytes = base64.b64decode(video_data["videoBase64"])
                with open(output_file, 'wb') as f:
                    f.write(video_bytes)

            elif "uri" in video_data:
                # If URI is provided instead
                response = requests.get(video_data["uri"], timeout=120)
                if response.status_code != 200:
                    raise VideoAPIError(f"Failed to download video: {response.status_code}")

                with open(output_file, 'wb') as f:
                    f.write(response.content)

            else:
                raise VideoAPIError("No video data or URI in response")

            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            logger.info(f"[Scene {scene_id}] Video downloaded: {file_size_mb:.2f} MB")

            return str(output_file)

        except Exception as e:
            if isinstance(e, VideoAPIError):
                raise
            raise VideoAPIError(f"Failed to download video: {str(e)}")

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe or estimate.

        Args:
            video_path: Path to video file.

        Returns:
            Duration in seconds.
        """
        try:
            import subprocess
            import json

            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data['format']['duration'])
                return duration

        except Exception as e:
            logger.warning(f"Could not get video duration via ffprobe: {e}")

        # Fallback: estimate based on config
        estimated_duration = float(self.gemini_config.duration_per_clip)
        logger.info(f"Using estimated duration: {estimated_duration}s")
        return estimated_duration

    def generate_clips_batch(
        self,
        prompts: List[str],
        output_dir: str
    ) -> List[Tuple[str, float]]:
        """Generate multiple video clips in parallel.

        Args:
            prompts: List of text prompts.
            output_dir: Directory to save video clips.

        Returns:
            List of tuples (video_path, duration) for each clip.

        Raises:
            VideoGenerationError: If batch generation fails.
        """
        try:
            logger.info(f"Generating {len(prompts)} video clips in parallel...")

            output_dir_path = Path(output_dir)
            output_dir_path.mkdir(parents=True, exist_ok=True)

            clips = []
            max_workers = min(self.gemini_config.max_parallel_clips, len(prompts))

            # Generate clips in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}

                for i, prompt in enumerate(prompts):
                    scene_id = i + 1
                    output_path = str(output_dir_path / f"scene_{scene_id:02d}.mp4")

                    future = executor.submit(
                        self.generate_video_clip,
                        prompt,
                        output_path,
                        scene_id
                    )
                    futures[future] = scene_id

                # Collect results
                for future in as_completed(futures):
                    scene_id = futures[future]
                    try:
                        video_path, duration = future.result()
                        clips.append((video_path, duration))
                        logger.info(f"[Scene {scene_id}] Completed")
                    except Exception as e:
                        logger.error(f"[Scene {scene_id}] Failed: {str(e)}")
                        raise VideoGenerationError(f"Scene {scene_id} generation failed: {str(e)}")

            # Sort by scene order
            clips.sort(key=lambda x: x[0])

            logger.info(f"Successfully generated {len(clips)} video clips")
            return clips

        except Exception as e:
            if isinstance(e, VideoGenerationError):
                raise
            raise VideoGenerationError(f"Batch video generation failed: {str(e)}")
