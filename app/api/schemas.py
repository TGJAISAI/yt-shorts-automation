"""Pydantic schemas for API requests and responses."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class GenerateVideoRequest(BaseModel):
    """Request schema for video generation."""
    topic: Optional[str] = Field(None, description="Optional specific topic for the video")


class GenerateVideoResponse(BaseModel):
    """Response schema for video generation."""
    job_id: str
    status: str
    title: str
    video_path: str
    video_duration: float
    video_id: str
    video_url: str
    shorts_url: str
    execution_time_seconds: float
    completed_at: str


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str
    detail: Optional[str] = None
    step: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str
    timestamp: str
    version: str


class StatusResponse(BaseModel):
    """Pipeline status response schema."""
    status: str
    disk_usage: Dict[str, Any]
    recent_jobs: List[Dict[str, Any]]
    recent_uploads: List[Dict[str, Any]]
    quota_info: Dict[str, Any]
    image_model: Dict[str, Any]


class VideoInfo(BaseModel):
    """Video information schema."""
    job_id: str
    created_at: str
    modified_at: str
    files: List[str]


class VideosListResponse(BaseModel):
    """Response schema for listing videos."""
    videos: List[VideoInfo]
    total: int


class SchedulerResponse(BaseModel):
    """Scheduler control response schema."""
    message: str
    scheduler_running: bool


class UploadHistoryItem(BaseModel):
    """Upload history item schema."""
    video_id: str
    video_url: str
    shorts_url: str
    title: str
    uploaded_at: str
    privacy_status: str


class UploadHistoryResponse(BaseModel):
    """Upload history response schema."""
    uploads: List[UploadHistoryItem]
    total: int
