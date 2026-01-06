"""Video generation service using Pexels stock videos."""

import logging
import time
import subprocess
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.config import Config
from app.core.exceptions import VideoGenerationError, VideoAPIError, RateLimitError
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class VideoGenerator:
    """Generates videos using Pexels stock footage."""

    def __init__(self, config: Config):
        """Initialize video generator.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.video_config = config.video_generation
        self.pexels_api_key = config.settings.pexels_api_key

        # Pexels API endpoint for videos
        self.pexels_base_url = "https://api.pexels.com/videos"
        self.headers = {
            "Authorization": self.pexels_api_key
        }

        logger.info("Video generator initialized with Pexels API")

    @retry_with_backoff(
        max_attempts=3,
        base_delay=5.0,
        exceptions=(VideoAPIError, RateLimitError, VideoGenerationError)
    )
    def generate_video_clip(
        self,
        prompt: str,
        output_path: str,
        scene_id: int = 1
    ) -> Tuple[str, float]:
        """Generate a single video clip from Pexels stock footage.

        Args:
            prompt: Text description of the scene (used to search Pexels).
            output_path: Path to save the video clip.
            scene_id: Scene identifier for logging.

        Returns:
            Tuple of (video_path, duration_in_seconds).

        Raises:
            VideoGenerationError: If video generation fails.
        """
        try:
            logger.info(f"[Scene {scene_id}] Searching Pexels for: {prompt[:100]}...")

            # Search Pexels for relevant video
            video_url = self._search_pexels_video(prompt, scene_id)

            # Download the video
            output_file = self._download_pexels_video(video_url, output_path, scene_id)

            # Resize/crop to 9:16 format if needed
            output_file = self._format_for_shorts(output_file, scene_id)

            # Get video duration
            duration = self._get_video_duration(output_file)

            logger.info(f"[Scene {scene_id}] Video generated successfully: {duration:.1f}s")
            return output_file, duration

        except Exception as e:
            if isinstance(e, (VideoGenerationError, VideoAPIError, RateLimitError)):
                raise
            raise VideoGenerationError(f"Failed to generate video clip: {str(e)}")

    def _search_pexels_video(self, prompt: str, scene_id: int) -> str:
        """Search Pexels for a relevant video.

        Args:
            prompt: Search query (scene description).
            scene_id: Scene identifier for logging.

        Returns:
            Video download URL (HD portrait format preferred).

        Raises:
            VideoAPIError: If search fails or no results found.
        """
        try:
            # Extract keywords from prompt (simple approach)
            keywords = self._extract_keywords(prompt)
            search_query = " ".join(keywords[:3])  # Use top 3 keywords

            logger.info(f"[Scene {scene_id}] Searching Pexels with query: '{search_query}'")

            # Search Pexels videos via REST API
            search_url = f"{self.pexels_base_url}/search"
            params = {
                'query': search_query,
                'orientation': 'portrait',
                'size': 'medium',
                'per_page': 5
            }

            response = requests.get(search_url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 429:
                raise RateLimitError("Pexels API rate limit exceeded")
            elif response.status_code != 200:
                raise VideoAPIError(f"Pexels API error: {response.status_code} - {response.text}")

            data = response.json()

            # Check if we got results
            if not data.get('videos') or len(data['videos']) == 0:
                logger.warning(f"[Scene {scene_id}] No results for '{search_query}', using fallback search")
                # Fallback to generic search
                params['query'] = 'nature'
                response = requests.get(search_url, headers=self.headers, params=params, timeout=30)
                data = response.json()

            if not data.get('videos') or len(data['videos']) == 0:
                raise VideoAPIError(f"No videos found on Pexels for: {search_query}")

            # Get the first video
            video = data['videos'][0]

            # Find best quality portrait video file
            video_url = None
            for video_file in video['video_files']:
                if video_file.get('width', 0) == 1080 and video_file.get('height', 0) == 1920:
                    # Perfect 9:16 format
                    video_url = video_file['link']
                    break
                elif video_file.get('quality') and 'hd' in str(video_file.get('quality')).lower():
                    # HD quality as fallback
                    video_url = video_file['link']

            if not video_url and video['video_files']:
                # Use any available file as last resort
                video_url = video['video_files'][0]['link']

            if not video_url:
                raise VideoAPIError("No downloadable video file found")

            logger.info(f"[Scene {scene_id}] Found video: {video.get('url', 'N/A')}")
            return video_url

        except Exception as e:
            if isinstance(e, VideoAPIError):
                raise
            raise VideoAPIError(f"Pexels search failed: {str(e)}")

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for search.

        Args:
            text: Input text.

        Returns:
            List of keywords.
        """
        # Remove common words
        stop_words = {'a', 'an', 'and', 'the', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'as'}
        words = text.lower().split()
        keywords = [w.strip('.,!?') for w in words if w.lower() not in stop_words and len(w) > 2]
        return keywords[:5]

    def _download_pexels_video(self, video_url: str, output_path: str, scene_id: int) -> str:
        """Download video from Pexels.

        Args:
            video_url: Direct download URL.
            output_path: Path to save video.
            scene_id: Scene identifier.

        Returns:
            Path to downloaded video file.

        Raises:
            VideoAPIError: If download fails.
        """
        try:
            logger.info(f"[Scene {scene_id}] Downloading video from Pexels...")

            # Create output directory
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # Download video
            response = requests.get(video_url, stream=True, timeout=60)

            if response.status_code != 200:
                raise VideoAPIError(f"Failed to download video: HTTP {response.status_code}")

            # Save to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info(f"[Scene {scene_id}] Downloaded video: {file_size_mb:.2f} MB")

            return output_path

        except requests.exceptions.RequestException as e:
            raise VideoAPIError(f"Failed to download video: {str(e)}")

    def _format_for_shorts(self, video_path: str, scene_id: int) -> str:
        """Format video to 9:16 aspect ratio for YouTube Shorts.

        Args:
            video_path: Path to input video.
            scene_id: Scene identifier.

        Returns:
            Path to formatted video.

        Raises:
            VideoGenerationError: If formatting fails.
        """
        try:
            # Get video dimensions
            probe_cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                video_path
            ]

            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            video_stream = next(s for s in data['streams'] if s['codec_type'] == 'video')

            width = int(video_stream['width'])
            height = int(video_stream['height'])

            # Check if already 9:16
            target_width = 1080
            target_height = 1920
            current_ratio = width / height
            target_ratio = target_width / target_height

            if abs(current_ratio - target_ratio) < 0.01:
                logger.info(f"[Scene {scene_id}] Video already in 9:16 format")
                return video_path

            # Need to crop/scale to 9:16
            logger.info(f"[Scene {scene_id}] Converting to 9:16 format ({width}x{height} → {target_width}x{target_height})")

            temp_output = str(Path(video_path).with_suffix('.formatted.mp4'))

            # FFmpeg command to crop and scale
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=increase,crop={target_width}:{target_height}',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-an',  # Remove audio (will be added later)
                temp_output
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                raise VideoGenerationError(f"FFmpeg formatting failed: {result.stderr}")

            # Replace original with formatted version
            Path(video_path).unlink()
            Path(temp_output).rename(video_path)

            logger.info(f"[Scene {scene_id}] Video formatted successfully")
            return video_path

        except Exception as e:
            raise VideoGenerationError(f"Failed to format video: {str(e)}")


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

        # Fallback: estimate based on typical Pexels video length
        estimated_duration = 8.0  # Most Pexels videos are 5-15 seconds
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
            max_workers = min(self.video_config.max_parallel_clips, len(prompts))

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
