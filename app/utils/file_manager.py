"""File management utilities."""

import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
import logging
import uuid

from app.core.exceptions import FileOperationError

logger = logging.getLogger(__name__)


class FileManager:
    """Manages file operations for the application."""

    def __init__(self, data_dir: str):
        """Initialize file manager.

        Args:
            data_dir: Root data directory path.
        """
        self.data_dir = Path(data_dir)
        self.outputs_dir = self.data_dir / "outputs"
        self.scripts_dir = self.outputs_dir / "scripts"
        self.images_dir = self.outputs_dir / "images"
        self.audio_dir = self.outputs_dir / "audio"
        self.videos_dir = self.outputs_dir / "videos"
        self.metadata_dir = self.data_dir / "metadata"

    def generate_job_id(self) -> str:
        """Generate a unique job ID.

        Returns:
            Job ID string in format: YYYYMMDD_HHMMSS_UUID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique_id}"

    def create_job_directories(self, job_id: str) -> dict:
        """Create directories for a specific job.

        Args:
            job_id: Unique job identifier.

        Returns:
            Dictionary with paths for each output type.
        """
        try:
            paths = {
                "scripts": self.scripts_dir / job_id,
                "images": self.images_dir / job_id,
                "audio": self.audio_dir / job_id,
                "videos": self.videos_dir / job_id,
            }

            for path in paths.values():
                path.mkdir(parents=True, exist_ok=True)

            logger.info(f"Created job directories for job_id: {job_id}")
            return {k: str(v) for k, v in paths.items()}

        except Exception as e:
            raise FileOperationError(f"Failed to create job directories: {str(e)}")

    def get_job_paths(self, job_id: str) -> dict:
        """Get paths for a specific job.

        Args:
            job_id: Unique job identifier.

        Returns:
            Dictionary with paths for each output type.
        """
        return {
            "scripts": str(self.scripts_dir / job_id),
            "images": str(self.images_dir / job_id),
            "audio": str(self.audio_dir / job_id),
            "videos": str(self.videos_dir / job_id),
        }

    def save_script(self, job_id: str, script_data: dict, filename: str = "script.json") -> str:
        """Save script data to file.

        Args:
            job_id: Unique job identifier.
            script_data: Script data to save.
            filename: Filename for the script.

        Returns:
            Path to saved script file.
        """
        try:
            import json

            script_dir = self.scripts_dir / job_id
            script_dir.mkdir(parents=True, exist_ok=True)

            script_path = script_dir / filename
            with open(script_path, 'w') as f:
                json.dump(script_data, f, indent=2)

            logger.info(f"Saved script to {script_path}")
            return str(script_path)

        except Exception as e:
            raise FileOperationError(f"Failed to save script: {str(e)}")

    def get_disk_usage(self) -> dict:
        """Get disk usage statistics for the data directory.

        Returns:
            Dictionary with usage statistics in GB.
        """
        try:
            total_size = 0
            file_count = 0

            for dirpath, dirnames, filenames in os.walk(self.outputs_dir):
                for filename in filenames:
                    file_path = Path(dirpath) / filename
                    if file_path.exists():
                        total_size += file_path.stat().st_size
                        file_count += 1

            total_size_gb = total_size / (1024 ** 3)

            return {
                "total_size_gb": round(total_size_gb, 2),
                "file_count": file_count,
                "directory": str(self.outputs_dir)
            }

        except Exception as e:
            logger.error(f"Failed to get disk usage: {str(e)}")
            return {"total_size_gb": 0, "file_count": 0, "directory": str(self.outputs_dir)}

    def cleanup_old_files(self, keep_days: int = 30) -> dict:
        """Clean up old files based on retention policy.

        Args:
            keep_days: Number of days to keep files.

        Returns:
            Dictionary with cleanup statistics.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            deleted_count = 0
            deleted_size = 0

            for output_type in ["scripts", "images", "audio", "videos"]:
                output_dir = self.outputs_dir / output_type

                if not output_dir.exists():
                    continue

                for job_dir in output_dir.iterdir():
                    if not job_dir.is_dir():
                        continue

                    # Check directory modification time
                    dir_mtime = datetime.fromtimestamp(job_dir.stat().st_mtime)

                    if dir_mtime < cutoff_date:
                        # Calculate size before deleting
                        dir_size = sum(
                            f.stat().st_size
                            for f in job_dir.rglob('*')
                            if f.is_file()
                        )

                        # Delete directory
                        shutil.rmtree(job_dir)
                        deleted_count += 1
                        deleted_size += dir_size

                        logger.info(f"Deleted old job directory: {job_dir}")

            deleted_size_gb = deleted_size / (1024 ** 3)

            result = {
                "deleted_jobs": deleted_count,
                "deleted_size_gb": round(deleted_size_gb, 2),
                "cutoff_date": cutoff_date.isoformat()
            }

            logger.info(f"Cleanup completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to cleanup old files: {str(e)}")
            return {"deleted_jobs": 0, "deleted_size_gb": 0, "error": str(e)}

    def delete_job_files(self, job_id: str) -> bool:
        """Delete all files for a specific job.

        Args:
            job_id: Unique job identifier.

        Returns:
            True if successful, False otherwise.
        """
        try:
            deleted = False

            for output_type in ["scripts", "images", "audio", "videos"]:
                job_dir = self.outputs_dir / output_type / job_id

                if job_dir.exists():
                    shutil.rmtree(job_dir)
                    deleted = True
                    logger.info(f"Deleted {output_type} directory for job {job_id}")

            return deleted

        except Exception as e:
            logger.error(f"Failed to delete job files for {job_id}: {str(e)}")
            return False

    def list_jobs(self, limit: int = 10, output_type: str = "videos") -> List[dict]:
        """List recent jobs.

        Args:
            limit: Maximum number of jobs to return.
            output_type: Type of output to list (scripts, images, audio, videos).

        Returns:
            List of job information dictionaries.
        """
        try:
            output_dir = self.outputs_dir / output_type

            if not output_dir.exists():
                return []

            jobs = []
            for job_dir in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if not job_dir.is_dir():
                    continue

                job_info = {
                    "job_id": job_dir.name,
                    "created_at": datetime.fromtimestamp(job_dir.stat().st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(job_dir.stat().st_mtime).isoformat(),
                    "files": [f.name for f in job_dir.iterdir() if f.is_file()]
                }

                jobs.append(job_info)

                if len(jobs) >= limit:
                    break

            return jobs

        except Exception as e:
            logger.error(f"Failed to list jobs: {str(e)}")
            return []

    def ensure_directory(self, path: str) -> Path:
        """Ensure a directory exists.

        Args:
            path: Directory path.

        Returns:
            Path object for the directory.
        """
        dir_path = Path(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def get_file_size_mb(self, file_path: str) -> float:
        """Get file size in MB.

        Args:
            file_path: Path to file.

        Returns:
            File size in MB.
        """
        try:
            size_bytes = Path(file_path).stat().st_size
            return round(size_bytes / (1024 ** 2), 2)
        except Exception:
            return 0.0
