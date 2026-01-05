"""Scheduler for automated video generation and uploads."""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_config
from app.core.logger import setup_logging

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler()


def scheduled_video_generation():
    """Job function called by the scheduler to generate and upload videos."""
    try:
        logger.info(f"Starting scheduled video generation at {datetime.now()}")

        # Import here to avoid circular imports
        from app.pipeline.orchestrator import VideoOrchestrator

        orchestrator = VideoOrchestrator()
        result = orchestrator.run_pipeline()

        logger.info(
            f"Scheduled generation completed successfully: {result['video_id']} "
            f"({result['execution_time_seconds']}s)"
        )
        logger.info(f"Shorts URL: {result['shorts_url']}")

    except Exception as e:
        logger.error(f"Scheduled video generation failed: {str(e)}", exc_info=True)
        # Don't raise - let the scheduler continue


def start_scheduler():
    """Start the background scheduler."""
    try:
        config = get_config()

        if scheduler.running:
            logger.warning("Scheduler is already running")
            return

        # Add the video generation job
        scheduler.add_job(
            func=scheduled_video_generation,
            trigger=IntervalTrigger(hours=config.settings.schedule_interval_hours),
            id='video_generation_job',
            name='Generate and upload YouTube Short',
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            misfire_grace_time=3600  # Run within 1 hour if missed
        )

        scheduler.start()
        logger.info(
            f"Scheduler started - will generate videos every "
            f"{config.settings.schedule_interval_hours} hours"
        )

    except Exception as e:
        logger.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
        raise


def stop_scheduler():
    """Stop the background scheduler."""
    try:
        if not scheduler.running:
            logger.warning("Scheduler is not running")
            return

        scheduler.shutdown()
        logger.info("Scheduler stopped")

    except Exception as e:
        logger.error(f"Failed to stop scheduler: {str(e)}", exc_info=True)
        raise


def is_running() -> bool:
    """Check if scheduler is running.

    Returns:
        True if scheduler is running, False otherwise.
    """
    return scheduler.running


def get_next_run_time() -> str:
    """Get the next scheduled run time.

    Returns:
        ISO format timestamp of next run, or None if not scheduled.
    """
    try:
        job = scheduler.get_job('video_generation_job')
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None
    except Exception:
        return None


def get_jobs() -> list:
    """Get list of scheduled jobs.

    Returns:
        List of job information dictionaries.
    """
    try:
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs
    except Exception as e:
        logger.error(f"Failed to get jobs: {str(e)}")
        return []


def schedule_immediate_and_recurring():
    """Run immediately then schedule recurring jobs.

    Useful for testing or ensuring first video is generated immediately.
    """
    try:
        config = get_config()

        if scheduler.running:
            logger.warning("Scheduler is already running")
            return

        # Run immediately
        scheduler.add_job(
            func=scheduled_video_generation,
            trigger='date',
            run_date=datetime.now(),
            id='immediate_run',
            name='Immediate video generation'
        )

        # Schedule recurring job
        scheduler.add_job(
            func=scheduled_video_generation,
            trigger=IntervalTrigger(hours=config.settings.schedule_interval_hours),
            id='video_generation_job',
            name='Generate and upload YouTube Short',
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=3600
        )

        scheduler.start()
        logger.info("Scheduler started with immediate first run")

    except Exception as e:
        logger.error(f"Failed to start scheduler with immediate run: {str(e)}", exc_info=True)
        raise


def run_once():
    """Run video generation once without starting the scheduler.

    Useful for manual testing.
    """
    try:
        logger.info("Running video generation once (manual trigger)")
        scheduled_video_generation()
    except Exception as e:
        logger.error(f"Manual generation failed: {str(e)}", exc_info=True)
        raise
