"""Main pipeline orchestrator for video generation and upload."""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.config import get_config
from app.core.exceptions import PipelineError, ValidationError
from app.services.script_generator import ScriptGenerator
from app.services.video_generator import VideoGenerator
from app.services.audio_generator import AudioGenerator
from app.services.audio_overlay_service import AudioOverlayService
from app.services.youtube_uploader import YouTubeUploader
from app.pipeline.validators import PipelineValidator
from app.utils.file_manager import FileManager

logger = logging.getLogger(__name__)


class VideoOrchestrator:
    """Orchestrates the complete video generation and upload pipeline."""

    def __init__(self):
        """Initialize orchestrator with all services."""
        self.config = get_config()

        # Initialize services
        self.script_generator = ScriptGenerator(self.config)
        self.video_generator = VideoGenerator(self.config)
        self.audio_generator = AudioGenerator(self.config)
        self.audio_overlay = AudioOverlayService(self.config)
        self.youtube_uploader = YouTubeUploader(self.config)
        self.validator = PipelineValidator(self.config)
        self.file_manager = FileManager(self.config.settings.data_dir)

        logger.info("Video orchestrator initialized (OpenAI + Gemini Veo pipeline)")

    def run_pipeline(self, topic: str = None) -> Dict[str, Any]:
        """Run the complete pipeline from script generation to upload.

        Args:
            topic: Optional specific topic for the video.

        Returns:
            Dictionary with pipeline results.

        Raises:
            PipelineError: If any step fails.
        """
        start_time = time.time()
        job_id = self.file_manager.generate_job_id()

        logger.info(f"Starting pipeline execution for job_id: {job_id}")

        try:
            # Create job directories
            job_paths = self.file_manager.create_job_directories(job_id)

            # Step 1: Generate Script with OpenAI
            script_data = self._step_generate_script(job_id, topic)

            # Step 2: Generate Video Clips with Gemini Veo
            video_clips = self._step_generate_video_clips(job_id, script_data, job_paths["videos"])

            # Step 3: Generate Audio
            audio_path, audio_duration = self._step_generate_audio(job_id, script_data, job_paths["audio"])

            # Step 4: Combine Videos and Audio
            video_path, video_duration = self._step_combine_video_audio(
                job_id,
                video_clips,
                audio_path,
                job_paths["videos"]
            )

            # Step 5: Upload to YouTube
            upload_result = self._step_upload_to_youtube(job_id, video_path, script_data)

            # Calculate execution time
            execution_time = time.time() - start_time

            # Build result
            result = {
                "job_id": job_id,
                "status": "success",
                "title": script_data["title"],
                "video_path": video_path,
                "video_duration": video_duration,
                "video_id": upload_result["video_id"],
                "video_url": upload_result["video_url"],
                "shorts_url": upload_result["shorts_url"],
                "execution_time_seconds": round(execution_time, 1),
                "completed_at": datetime.now().isoformat(),
            }

            logger.info(f"Pipeline completed successfully in {execution_time:.1f}s")
            logger.info(f"Video uploaded: {upload_result['shorts_url']}")

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Pipeline failed after {execution_time:.1f}s: {str(e)}", exc_info=True)

            # Cleanup on failure (optional)
            if self.config.file_retention.auto_cleanup:
                logger.info(f"Cleaning up failed job: {job_id}")
                self.file_manager.delete_job_files(job_id)

            raise PipelineError(
                f"Pipeline execution failed: {str(e)}",
                step=self._get_current_step(e),
                job_id=job_id
            )

    def _step_generate_script(self, job_id: str, topic: Optional[str] = None) -> Dict[str, Any]:
        """Step 1: Generate video script using OpenAI.

        Args:
            job_id: Job identifier.
            topic: Optional specific topic.

        Returns:
            Script data dictionary.

        Raises:
            PipelineError: If script generation fails.
        """
        try:
            logger.info(f"[{job_id}] Step 1/5: Generating script with OpenAI...")

            script_data = self.script_generator.generate_script(topic)

            # Validate script
            is_valid, issues = self.validator.validate_script(script_data)
            if not is_valid:
                logger.error(f"Script validation failed: {issues}")
                raise ValidationError(f"Script validation failed: {issues}")

            # Save script
            self.file_manager.save_script(job_id, script_data)

            logger.info(f"[{job_id}] Script generated: {script_data['title']}")
            return script_data

        except Exception as e:
            raise PipelineError(f"Script generation failed: {str(e)}", step="script_generation", job_id=job_id)

    def _step_generate_video_clips(
        self,
        job_id: str,
        script_data: Dict[str, Any],
        output_dir: str
    ) -> list:
        """Step 2: Generate video clips using Gemini Veo.

        Args:
            job_id: Job identifier.
            script_data: Script data with scene descriptions.
            output_dir: Directory to save video clips.

        Returns:
            List of tuples (video_path, duration).

        Raises:
            PipelineError: If video generation fails.
        """
        try:
            logger.info(f"[{job_id}] Step 2/5: Generating video clips with Gemini Veo...")

            # Extract scene descriptions as prompts
            prompts = [scene["description"] for scene in script_data["scenes"]]

            video_clips = self.video_generator.generate_clips_batch(prompts, output_dir)

            logger.info(f"[{job_id}] Generated {len(video_clips)} video clips")
            return video_clips

        except Exception as e:
            raise PipelineError(f"Video generation failed: {str(e)}", step="video_generation", job_id=job_id)

    def _step_generate_audio(
        self,
        job_id: str,
        script_data: Dict[str, Any],
        output_dir: str
    ) -> tuple:
        """Step 3: Generate audio narration.

        Args:
            job_id: Job identifier.
            script_data: Script data with voiceovers.
            output_dir: Directory to save audio.

        Returns:
            Tuple of (audio_path, duration).

        Raises:
            PipelineError: If audio generation fails.
        """
        try:
            logger.info(f"[{job_id}] Step 3/5: Generating audio...")

            audio_path, duration = self.audio_generator.generate_from_scenes(
                scenes=script_data["scenes"],
                output_dir=output_dir
            )

            # Validate audio
            is_valid, issues = self.validator.validate_audio(audio_path)
            if not is_valid:
                logger.error(f"Audio validation failed: {issues}")
                raise ValidationError(f"Audio validation failed: {issues}")

            logger.info(f"[{job_id}] Audio generated: {duration:.1f}s")
            return audio_path, duration

        except Exception as e:
            raise PipelineError(f"Audio generation failed: {str(e)}", step="audio_generation", job_id=job_id)

    def _step_combine_video_audio(
        self,
        job_id: str,
        video_clips: list,
        audio_path: str,
        output_dir: str
    ) -> tuple:
        """Step 4: Combine video clips and audio.

        Args:
            job_id: Job identifier.
            video_clips: List of tuples (video_path, duration).
            audio_path: Path to audio file.
            output_dir: Directory to save final video.

        Returns:
            Tuple of (video_path, duration).

        Raises:
            PipelineError: If combining fails.
        """
        try:
            logger.info(f"[{job_id}] Step 4/5: Combining video clips with audio...")

            # Extract just the paths from (path, duration) tuples
            clip_paths = [clip[0] for clip in video_clips]

            # Concatenate clips and overlay audio
            video_path = f"{output_dir}/final.mp4"
            video_path, duration = self.audio_overlay.concatenate_clips_with_audio(
                video_clips=clip_paths,
                audio_path=audio_path,
                output_path=video_path
            )

            # Validate final video
            is_valid, issues = self.validator.validate_video(video_path)
            if not is_valid:
                logger.error(f"Video validation failed: {issues}")
                raise ValidationError(f"Video validation failed: {issues}")

            logger.info(f"[{job_id}] Final video created: {duration:.1f}s")
            return video_path, duration

        except Exception as e:
            raise PipelineError(f"Video combination failed: {str(e)}", step="video_combination", job_id=job_id)

    def _step_upload_to_youtube(
        self,
        job_id: str,
        video_path: str,
        script_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Step 5: Upload video to YouTube.

        Args:
            job_id: Job identifier.
            video_path: Path to video file.
            script_data: Script data with metadata.

        Returns:
            Upload result dictionary.

        Raises:
            PipelineError: If upload fails.
        """
        try:
            logger.info(f"[{job_id}] Step 5/5: Uploading to YouTube...")

            upload_result = self.youtube_uploader.upload_video(
                video_path=video_path,
                title=script_data["title"],
                description=script_data["description"],
                tags=script_data.get("tags", [])
            )

            logger.info(f"[{job_id}] Upload complete: {upload_result['video_id']}")
            return upload_result

        except Exception as e:
            raise PipelineError(f"YouTube upload failed: {str(e)}", step="youtube_upload", job_id=job_id)

    def _get_current_step(self, exception: Exception) -> str:
        """Determine current step from exception.

        Args:
            exception: Exception that occurred.

        Returns:
            Step name.
        """
        if isinstance(exception, PipelineError):
            return exception.step or "unknown"

        error_msg = str(exception).lower()
        if "script" in error_msg:
            return "script_generation"
        elif "prompt" in error_msg:
            return "prompt_enhancement"
        elif "video" in error_msg or "clip" in error_msg or "gemini" in error_msg:
            return "video_generation"
        elif "audio" in error_msg:
            return "audio_generation"
        elif "combine" in error_msg or "concatenate" in error_msg:
            return "video_combination"
        elif "youtube" in error_msg or "upload" in error_msg:
            return "youtube_upload"
        else:
            return "unknown"

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status and statistics.

        Returns:
            Dictionary with pipeline status.
        """
        try:
            # Get file manager stats
            disk_usage = self.file_manager.get_disk_usage()

            # Get recent jobs
            recent_jobs = self.file_manager.list_jobs(limit=5)

            # Get upload history
            upload_history = self.youtube_uploader.get_upload_history(limit=5)

            # Get quota usage
            quota_info = self.youtube_uploader.get_quota_usage()

            return {
                "status": "ready",
                "disk_usage": disk_usage,
                "recent_jobs": recent_jobs,
                "recent_uploads": upload_history,
                "quota_info": quota_info,
                "pipeline_version": "2.0.0",
                "video_provider": "gemini_veo",
                "script_provider": "openai",
            }

        except Exception as e:
            logger.error(f"Failed to get pipeline status: {str(e)}")
            return {"status": "error", "error": str(e)}
