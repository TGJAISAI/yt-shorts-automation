"""YouTube upload service using YouTube Data API v3."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import google.auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from app.core.config import Config
from app.core.exceptions import (
    YouTubeUploadError,
    QuotaExceededError,
    AuthenticationError,
    RateLimitError
)
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """Uploads videos to YouTube using the Data API v3."""

    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

    def __init__(self, config: Config):
        """Initialize YouTube uploader.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.upload_config = config.youtube_upload
        self.youtube = None
        self._setup_credentials()

    def _setup_credentials(self):
        """Setup YouTube API credentials."""
        try:
            credentials = Credentials(
                token=None,
                refresh_token=self.config.settings.youtube_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.config.settings.youtube_client_id,
                client_secret=self.config.settings.youtube_client_secret,
                scopes=self.SCOPES
            )

            self.youtube = build('youtube', 'v3', credentials=credentials)
            logger.info("YouTube API client initialized")

        except Exception as e:
            raise AuthenticationError(f"Failed to setup YouTube credentials: {str(e)}")

    @retry_with_backoff(
        max_attempts=3,
        base_delay=5.0,
        exceptions=(RateLimitError,)
    )
    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str] = None,
        category_id: str = None,
        privacy_status: str = None
    ) -> Dict[str, Any]:
        """Upload video to YouTube.

        Args:
            video_path: Path to video file.
            title: Video title (max 100 chars).
            description: Video description.
            tags: List of tags.
            category_id: YouTube category ID.
            privacy_status: Privacy status (public, private, unlisted).

        Returns:
            Dictionary with upload result including video_id and url.

        Raises:
            YouTubeUploadError: If upload fails.
        """
        try:
            logger.info(f"Uploading video: {title}")

            # Validate file exists
            if not Path(video_path).exists():
                raise YouTubeUploadError(f"Video file not found: {video_path}")

            # Prepare metadata
            if tags is None:
                tags = self.upload_config.default_tags
            else:
                # Merge with default tags
                tags = list(set(tags + self.upload_config.default_tags))

            if category_id is None:
                category_id = self.upload_config.category_id

            if privacy_status is None:
                privacy_status = self.upload_config.privacy_status

            # Build description with suffix
            full_description = description
            if self.upload_config.default_description_suffix:
                full_description += self.upload_config.default_description_suffix

            # Prepare request body
            body = {
                'snippet': {
                    'title': title[:100],  # YouTube max title length
                    'description': full_description[:5000],  # YouTube max description length
                    'tags': tags[:500],  # YouTube max tags
                    'categoryId': category_id,
                    'defaultLanguage': self.upload_config.default_language,
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'madeForKids': self.upload_config.made_for_kids,
                    'selfDeclaredMadeForKids': self.upload_config.made_for_kids,
                }
            }

            # Prepare media upload
            media = MediaFileUpload(
                video_path,
                chunksize=1024*1024,  # 1MB chunks
                resumable=True
            )

            # Execute upload
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")

            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            shorts_url = f"https://www.youtube.com/shorts/{video_id}"

            result = {
                'video_id': video_id,
                'video_url': video_url,
                'shorts_url': shorts_url,
                'title': title,
                'uploaded_at': datetime.now().isoformat(),
                'privacy_status': privacy_status
            }

            # Save to upload history
            self._save_upload_history(result)

            logger.info(f"Video uploaded successfully: {video_id}")
            logger.info(f"Shorts URL: {shorts_url}")

            return result

        except HttpError as e:
            error_content = e.content.decode('utf-8') if e.content else str(e)

            if e.resp.status == 403:
                if 'quotaExceeded' in error_content:
                    raise QuotaExceededError("YouTube API quota exceeded")
                else:
                    raise AuthenticationError(f"YouTube API authentication failed: {error_content}")

            elif e.resp.status == 429:
                raise RateLimitError("YouTube API rate limit exceeded")

            else:
                raise YouTubeUploadError(f"YouTube API error: {error_content}")

        except Exception as e:
            if isinstance(e, (YouTubeUploadError, QuotaExceededError, AuthenticationError, RateLimitError)):
                raise
            raise YouTubeUploadError(f"Failed to upload video: {str(e)}")

    def _save_upload_history(self, upload_data: Dict[str, Any]):
        """Save upload to history file.

        Args:
            upload_data: Upload result data.
        """
        try:
            history_file = Path(self.config.settings.data_dir) / "metadata" / "video_history.json"
            history_file.parent.mkdir(parents=True, exist_ok=True)

            # Load existing history
            if history_file.exists():
                with open(history_file, 'r') as f:
                    history = json.load(f)
            else:
                history = []

            # Add new upload
            history.append(upload_data)

            # Save updated history
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)

            logger.info(f"Saved upload to history: {upload_data['video_id']}")

        except Exception as e:
            logger.error(f"Failed to save upload history: {str(e)}")

    def get_upload_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get upload history.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of upload records.
        """
        try:
            history_file = Path(self.config.settings.data_dir) / "metadata" / "video_history.json"

            if not history_file.exists():
                return []

            with open(history_file, 'r') as f:
                history = json.load(f)

            # Return most recent uploads
            return history[-limit:] if limit else history

        except Exception as e:
            logger.error(f"Failed to read upload history: {str(e)}")
            return []

    def get_video_status(self, video_id: str) -> Dict[str, Any]:
        """Get status of an uploaded video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dictionary with video status.

        Raises:
            YouTubeUploadError: If status check fails.
        """
        try:
            request = self.youtube.videos().list(
                part='status,processingDetails,contentDetails',
                id=video_id
            )

            response = request.execute()

            if not response.get('items'):
                raise YouTubeUploadError(f"Video not found: {video_id}")

            video = response['items'][0]

            return {
                'video_id': video_id,
                'upload_status': video.get('status', {}).get('uploadStatus'),
                'privacy_status': video.get('status', {}).get('privacyStatus'),
                'processing_status': video.get('processingDetails', {}).get('processingStatus'),
                'duration': video.get('contentDetails', {}).get('duration'),
            }

        except HttpError as e:
            raise YouTubeUploadError(f"Failed to get video status: {str(e)}")

    def delete_video(self, video_id: str) -> bool:
        """Delete a video from YouTube.

        Args:
            video_id: YouTube video ID.

        Returns:
            True if successful.

        Raises:
            YouTubeUploadError: If deletion fails.
        """
        try:
            logger.warning(f"Deleting video: {video_id}")

            request = self.youtube.videos().delete(id=video_id)
            request.execute()

            logger.info(f"Video deleted: {video_id}")
            return True

        except HttpError as e:
            raise YouTubeUploadError(f"Failed to delete video: {str(e)}")

    def update_video_metadata(
        self,
        video_id: str,
        title: str = None,
        description: str = None,
        tags: List[str] = None
    ) -> bool:
        """Update video metadata.

        Args:
            video_id: YouTube video ID.
            title: New title (optional).
            description: New description (optional).
            tags: New tags (optional).

        Returns:
            True if successful.

        Raises:
            YouTubeUploadError: If update fails.
        """
        try:
            # Get current video details
            request = self.youtube.videos().list(
                part='snippet',
                id=video_id
            )

            response = request.execute()

            if not response.get('items'):
                raise YouTubeUploadError(f"Video not found: {video_id}")

            video = response['items'][0]
            snippet = video['snippet']

            # Update fields if provided
            if title:
                snippet['title'] = title[:100]
            if description:
                snippet['description'] = description[:5000]
            if tags:
                snippet['tags'] = tags[:500]

            # Update video
            request = self.youtube.videos().update(
                part='snippet',
                body={'id': video_id, 'snippet': snippet}
            )

            request.execute()

            logger.info(f"Video metadata updated: {video_id}")
            return True

        except HttpError as e:
            raise YouTubeUploadError(f"Failed to update video metadata: {str(e)}")

    def get_quota_usage(self) -> Dict[str, Any]:
        """Get estimated quota usage information.

        Returns:
            Dictionary with quota information.

        Note:
            This is an estimate based on known quota costs.
            Actual quota usage can only be viewed in Google Cloud Console.
        """
        history = self.get_upload_history()

        # Estimate: 1 upload = ~1600 quota units
        # Default daily quota = 10,000 units
        upload_count = len(history)
        estimated_quota_used = upload_count * 1600

        return {
            'total_uploads': upload_count,
            'estimated_quota_used': estimated_quota_used,
            'default_daily_quota': 10000,
            'estimated_quota_remaining': max(0, 10000 - estimated_quota_used),
            'note': 'Quota estimates are approximate. Check Google Cloud Console for actual usage.'
        }
