"""FastAPI routes for the application."""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.api.schemas import (
    GenerateVideoRequest,
    GenerateVideoResponse,
    ErrorResponse,
    HealthResponse,
    StatusResponse,
    VideosListResponse,
    VideoInfo,
    SchedulerResponse,
)
from app.pipeline.orchestrator import VideoOrchestrator
from app.core.config import get_config
from app.core.exceptions import PipelineError, QuotaExceededError, AuthenticationError
from app.utils.file_manager import FileManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global orchestrator instance (will be initialized when needed)
_orchestrator = None


def get_orchestrator() -> VideoOrchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = VideoOrchestrator()
    return _orchestrator


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        Health status.
    """
    config = get_config()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version=config.app.version
    )


@router.post("/generate", response_model=GenerateVideoResponse)
async def generate_video(request: GenerateVideoRequest):
    """Generate and upload a new video.

    Args:
        request: Video generation request.

    Returns:
        Generation result with video details.

    Raises:
        HTTPException: If generation fails.
    """
    try:
        logger.info(f"Received video generation request: topic={request.topic}")

        orchestrator = get_orchestrator()
        result = orchestrator.run_pipeline(topic=request.topic)

        return GenerateVideoResponse(**result)

    except QuotaExceededError as e:
        logger.error(f"YouTube quota exceeded: {str(e)}")
        raise HTTPException(
            status_code=429,
            detail="YouTube API quota exceeded. Please try again later."
        )

    except AuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )

    except PipelineError as e:
        logger.error(f"Pipeline error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "step": e.step,
                "job_id": e.job_id
            }
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/generate/async")
async def generate_video_async(request: GenerateVideoRequest, background_tasks: BackgroundTasks):
    """Generate and upload a new video asynchronously.

    Args:
        request: Video generation request.
        background_tasks: FastAPI background tasks.

    Returns:
        Acceptance message.
    """
    try:
        logger.info(f"Received async video generation request: topic={request.topic}")

        orchestrator = get_orchestrator()

        # Add generation to background tasks
        background_tasks.add_task(orchestrator.run_pipeline, topic=request.topic)

        return JSONResponse(
            status_code=202,
            content={
                "message": "Video generation started in background",
                "topic": request.topic
            }
        )

    except Exception as e:
        logger.error(f"Failed to start async generation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start generation: {str(e)}"
        )


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get pipeline status and statistics.

    Returns:
        Pipeline status information.
    """
    try:
        orchestrator = get_orchestrator()
        status = orchestrator.get_pipeline_status()
        return StatusResponse(**status)

    except Exception as e:
        logger.error(f"Failed to get status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


@router.get("/videos", response_model=VideosListResponse)
async def list_videos(limit: int = 10):
    """List recently generated videos.

    Args:
        limit: Maximum number of videos to return.

    Returns:
        List of video information.
    """
    try:
        config = get_config()
        file_manager = FileManager(config.settings.data_dir)

        jobs = file_manager.list_jobs(limit=limit, output_type="videos")
        videos = [VideoInfo(**job) for job in jobs]

        return VideosListResponse(
            videos=videos,
            total=len(videos)
        )

    except Exception as e:
        logger.error(f"Failed to list videos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list videos: {str(e)}"
        )


@router.get("/uploads")
async def list_uploads(limit: int = 10):
    """List recent YouTube uploads.

    Args:
        limit: Maximum number of uploads to return.

    Returns:
        Upload history.
    """
    try:
        orchestrator = get_orchestrator()
        uploads = orchestrator.youtube_uploader.get_upload_history(limit=limit)

        return {
            "uploads": uploads,
            "total": len(uploads)
        }

    except Exception as e:
        logger.error(f"Failed to list uploads: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list uploads: {str(e)}"
        )


@router.post("/scheduler/start", response_model=SchedulerResponse)
async def start_scheduler():
    """Start the automated scheduler.

    Returns:
        Scheduler status.
    """
    try:
        # Import here to avoid circular dependency
        import scheduler as sched

        if sched.is_running():
            return SchedulerResponse(
                message="Scheduler is already running",
                scheduler_running=True
            )

        sched.start_scheduler()

        return SchedulerResponse(
            message="Scheduler started successfully",
            scheduler_running=True
        )

    except Exception as e:
        logger.error(f"Failed to start scheduler: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start scheduler: {str(e)}"
        )


@router.post("/scheduler/stop", response_model=SchedulerResponse)
async def stop_scheduler():
    """Stop the automated scheduler.

    Returns:
        Scheduler status.
    """
    try:
        import scheduler as sched

        if not sched.is_running():
            return SchedulerResponse(
                message="Scheduler is not running",
                scheduler_running=False
            )

        sched.stop_scheduler()

        return SchedulerResponse(
            message="Scheduler stopped successfully",
            scheduler_running=False
        )

    except Exception as e:
        logger.error(f"Failed to stop scheduler: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop scheduler: {str(e)}"
        )


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status.

    Returns:
        Scheduler status information.
    """
    try:
        import scheduler as sched

        return {
            "running": sched.is_running(),
            "next_run": sched.get_next_run_time(),
            "jobs": sched.get_jobs()
        }

    except Exception as e:
        logger.error(f"Failed to get scheduler status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scheduler status: {str(e)}"
        )


@router.delete("/videos/{job_id}")
async def delete_video(job_id: str):
    """Delete video files for a specific job.

    Args:
        job_id: Job identifier.

    Returns:
        Deletion confirmation.
    """
    try:
        config = get_config()
        file_manager = FileManager(config.settings.data_dir)

        success = file_manager.delete_job_files(job_id)

        if success:
            return {"message": f"Video files deleted for job {job_id}"}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No files found for job {job_id}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete video: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete video: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_old_files(keep_days: int = 30):
    """Clean up old files based on retention policy.

    Args:
        keep_days: Number of days to keep files.

    Returns:
        Cleanup statistics.
    """
    try:
        config = get_config()
        file_manager = FileManager(config.settings.data_dir)

        result = file_manager.cleanup_old_files(keep_days=keep_days)

        return {
            "message": "Cleanup completed",
            "deleted_jobs": result["deleted_jobs"],
            "deleted_size_gb": result["deleted_size_gb"],
            "cutoff_date": result["cutoff_date"]
        }

    except Exception as e:
        logger.error(f"Failed to cleanup files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup files: {str(e)}"
        )
