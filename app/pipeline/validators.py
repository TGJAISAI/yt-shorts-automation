"""Validation utilities for the pipeline."""

import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

from app.core.config import Config
from app.core.exceptions import ValidationError, DurationExceededError

logger = logging.getLogger(__name__)


class PipelineValidator:
    """Validates data at each stage of the pipeline."""

    def __init__(self, config: Config):
        """Initialize validator.

        Args:
            config: Application configuration.
        """
        self.config = config

    def validate_script(self, script_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate script data.

        Args:
            script_data: Script data to validate.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues = []

        # Check required fields
        required_fields = ["title", "description", "tags", "scenes"]
        for field in required_fields:
            if field not in script_data:
                issues.append(f"Missing required field: {field}")

        # Validate title
        if "title" in script_data:
            title = script_data["title"]
            if not title or len(title) == 0:
                issues.append("Title is empty")
            elif len(title) > 100:
                issues.append(f"Title too long: {len(title)} chars (max 100)")

        # Validate description
        if "description" in script_data:
            description = script_data["description"]
            if not description:
                issues.append("Description is empty")
            elif len(description) > 5000:
                issues.append(f"Description too long: {len(description)} chars (max 5000)")

        # Validate tags
        if "tags" in script_data:
            tags = script_data["tags"]
            if not isinstance(tags, list):
                issues.append("Tags must be a list")
            elif len(tags) == 0:
                issues.append("No tags provided")

        # Validate scenes
        if "scenes" in script_data:
            scenes = script_data["scenes"]
            if not isinstance(scenes, list):
                issues.append("Scenes must be a list")
            elif len(scenes) == 0:
                issues.append("No scenes provided")
            else:
                for i, scene in enumerate(scenes):
                    scene_issues = self._validate_scene(scene, i + 1)
                    issues.extend(scene_issues)

        # Validate total duration
        if "scenes" in script_data and isinstance(script_data["scenes"], list):
            total_duration = sum(scene.get("duration", 0) for scene in script_data["scenes"])
            if total_duration >= self.config.settings.max_video_duration:
                issues.append(
                    f"Total duration {total_duration}s exceeds maximum "
                    f"{self.config.settings.max_video_duration}s"
                )

        is_valid = len(issues) == 0
        if is_valid:
            logger.info("Script validation passed")
        else:
            logger.warning(f"Script validation failed with {len(issues)} issues")

        return is_valid, issues

    def _validate_scene(self, scene: Dict[str, Any], scene_number: int) -> List[str]:
        """Validate a single scene.

        Args:
            scene: Scene data.
            scene_number: Scene number (for error messages).

        Returns:
            List of validation issues.
        """
        issues = []

        required_fields = ["scene_id", "description", "voiceover", "duration"]
        for field in required_fields:
            if field not in scene:
                issues.append(f"Scene {scene_number}: missing field '{field}'")

        if "description" in scene and not scene["description"].strip():
            issues.append(f"Scene {scene_number}: description is empty")

        if "voiceover" in scene and not scene["voiceover"].strip():
            issues.append(f"Scene {scene_number}: voiceover is empty")

        if "duration" in scene:
            duration = scene["duration"]
            if not isinstance(duration, (int, float)) or duration <= 0:
                issues.append(f"Scene {scene_number}: invalid duration {duration}")

        return issues

    def validate_images(self, image_paths: List[str]) -> Tuple[bool, List[str]]:
        """Validate generated images.

        Args:
            image_paths: List of image file paths.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues = []

        if not image_paths:
            issues.append("No images provided")
            return False, issues

        for image_path in image_paths:
            # Check file exists
            if not Path(image_path).exists():
                issues.append(f"Image file not found: {image_path}")
                continue

            # Check file size
            file_size = Path(image_path).stat().st_size
            if file_size == 0:
                issues.append(f"Image file is empty: {image_path}")
            elif file_size > 50 * 1024 * 1024:  # 50 MB
                issues.append(f"Image file too large: {image_path} ({file_size / 1024 / 1024:.1f} MB)")

            # Check dimensions using PIL
            try:
                from PIL import Image
                img = Image.open(image_path)
                width, height = img.size

                expected_width = self.config.settings.video_width
                expected_height = self.config.settings.video_height

                if width != expected_width or height != expected_height:
                    issues.append(
                        f"Image {Path(image_path).name}: wrong dimensions {width}x{height}, "
                        f"expected {expected_width}x{expected_height}"
                    )
            except Exception as e:
                issues.append(f"Failed to validate image {image_path}: {str(e)}")

        is_valid = len(issues) == 0
        if is_valid:
            logger.info(f"Image validation passed for {len(image_paths)} images")
        else:
            logger.warning(f"Image validation failed with {len(issues)} issues")

        return is_valid, issues

    def validate_audio(self, audio_path: str, max_duration: float = None) -> Tuple[bool, List[str]]:
        """Validate audio file.

        Args:
            audio_path: Path to audio file.
            max_duration: Maximum allowed duration in seconds.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues = []

        if max_duration is None:
            max_duration = self.config.settings.max_video_duration

        # Check file exists
        if not Path(audio_path).exists():
            issues.append(f"Audio file not found: {audio_path}")
            return False, issues

        # Check file size
        file_size = Path(audio_path).stat().st_size
        if file_size == 0:
            issues.append("Audio file is empty")
            return False, issues

        # Check duration using ffprobe
        try:
            import subprocess
            import json

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

                if duration >= max_duration:
                    issues.append(
                        f"Audio duration {duration:.1f}s exceeds maximum {max_duration}s"
                    )

                if duration == 0:
                    issues.append("Audio has zero duration")
            else:
                issues.append(f"Failed to probe audio: {result.stderr}")

        except Exception as e:
            issues.append(f"Failed to validate audio: {str(e)}")

        is_valid = len(issues) == 0
        if is_valid:
            logger.info("Audio validation passed")
        else:
            logger.warning(f"Audio validation failed with {len(issues)} issues")

        return is_valid, issues

    def validate_video(self, video_path: str) -> Tuple[bool, List[str]]:
        """Validate final video file.

        Args:
            video_path: Path to video file.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues = []

        # Check file exists
        if not Path(video_path).exists():
            issues.append(f"Video file not found: {video_path}")
            return False, issues

        # Check file size
        file_size = Path(video_path).stat().st_size
        if file_size == 0:
            issues.append("Video file is empty")
            return False, issues

        # Check video properties using ffprobe
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

                # Get video stream
                video_stream = None
                audio_stream = None
                for stream in data.get('streams', []):
                    if stream['codec_type'] == 'video':
                        video_stream = stream
                    elif stream['codec_type'] == 'audio':
                        audio_stream = stream

                if not video_stream:
                    issues.append("No video stream found")
                else:
                    width = int(video_stream.get('width', 0))
                    height = int(video_stream.get('height', 0))

                    # Validate dimensions
                    expected_width = self.config.settings.video_width
                    expected_height = self.config.settings.video_height

                    if width != expected_width:
                        issues.append(f"Video width {width} != expected {expected_width}")

                    if height != expected_height:
                        issues.append(f"Video height {height} != expected {expected_height}")

                # Get duration
                duration = float(data['format'].get('duration', 0))

                # Validate duration
                if duration >= self.config.settings.max_video_duration:
                    issues.append(
                        f"Video duration {duration:.1f}s >= maximum "
                        f"{self.config.settings.max_video_duration}s"
                    )

                if duration == 0:
                    issues.append("Video has zero duration")

                # Validate audio
                if not audio_stream:
                    issues.append("Video has no audio track")
            else:
                issues.append(f"Failed to probe video: {result.stderr}")

        except Exception as e:
            issues.append(f"Failed to validate video: {str(e)}")

        is_valid = len(issues) == 0
        if is_valid:
            logger.info("Video validation passed")
        else:
            logger.warning(f"Video validation failed with {len(issues)} issues")

        return is_valid, issues

    def validate_all(
        self,
        script_data: Dict[str, Any] = None,
        image_paths: List[str] = None,
        audio_path: str = None,
        video_path: str = None
    ) -> Tuple[bool, Dict[str, List[str]]]:
        """Validate all components.

        Args:
            script_data: Script data to validate.
            image_paths: Image paths to validate.
            audio_path: Audio path to validate.
            video_path: Video path to validate.

        Returns:
            Tuple of (all_valid, dict_of_issues_by_component).
        """
        all_issues = {}

        if script_data is not None:
            is_valid, issues = self.validate_script(script_data)
            if not is_valid:
                all_issues["script"] = issues

        if image_paths is not None:
            is_valid, issues = self.validate_images(image_paths)
            if not is_valid:
                all_issues["images"] = issues

        if audio_path is not None:
            is_valid, issues = self.validate_audio(audio_path)
            if not is_valid:
                all_issues["audio"] = issues

        if video_path is not None:
            is_valid, issues = self.validate_video(video_path)
            if not is_valid:
                all_issues["video"] = issues

        all_valid = len(all_issues) == 0

        return all_valid, all_issues
