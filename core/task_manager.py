"""
Task manager for async search operations.

This module implements a singleton task manager that tracks async search tasks,
their progress, and results. It provides thread-safe task management with
automatic cleanup of expired tasks.
"""

import asyncio
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from core.logger import get_logger


class TaskStatus(Enum):
    """Task status enumeration."""

    PENDING = "pending"  # Created but not started
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Encountered error
    CANCELLED = "cancelled"  # User cancelled


@dataclass
class TaskProgress:
    """Progress information for a running task."""

    current: int  # Current item count (e.g., 15)
    total: int  # Total item count (e.g., 30)
    stage: str  # Current stage: "searching"|"resolving"|"fetching"|"compressing"
    message: str  # Human-readable message: "Fetching content for article 15/30..."
    percentage: int  # Calculated: int(current/total * 100)


@dataclass
class SearchTask:
    """Represents a single search task."""

    task_id: str  # Unique identifier (UUID)
    status: TaskStatus  # Current status
    progress: Optional[TaskProgress] = None  # Progress info (only when running)

    # Request parameters (stored for reference)
    query: str = ""
    platform: str = ""
    max_results: int = 10
    include_content: bool = True

    # Results (only when completed)
    results: Optional[List[Dict[str, Any]]] = None

    # Error info (only when failed)
    error: Optional[str] = None
    error_traceback: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Estimated completion time (optional)
    estimated_completion: Optional[datetime] = None


class TaskManager:
    """
    Singleton task manager for async search operations.

    Responsibilities:
    - Create and track tasks
    - Update task progress
    - Clean up old tasks
    - Thread-safe task access
    """

    _instance: Optional["TaskManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "TaskManager":
        """Create singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize task manager."""
        if not hasattr(self, "initialized"):
            self.tasks: Dict[str, SearchTask] = {}
            self.logger = get_logger("vertical_search.task_manager")
            self.initialized = True

            # Start cleanup task
            asyncio.create_task(self._cleanup_loop())

    async def create_task(
        self,
        query: str,
        platform: str,
        max_results: int = 10,
        include_content: bool = True,
    ) -> str:
        """
        Create a new search task.

        Args:
            query: Search query string
            platform: Platform name (e.g., 'weixin', 'zhihu')
            max_results: Maximum number of results
            include_content: Whether to include full article content

        Returns:
            task_id: Unique identifier for the task
        """
        async with self._lock:
            task_id = str(uuid4())

            task = SearchTask(
                task_id=task_id,
                status=TaskStatus.PENDING,
                progress=None,
                query=query,
                platform=platform,
                max_results=max_results,
                include_content=include_content,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            self.tasks[task_id] = task
            self.logger.info(f"Created task {task_id}: {platform}:{query}")

            return task_id

    async def get_task(self, task_id: str) -> Optional[SearchTask]:
        """
        Get task by ID.

        Args:
            task_id: Task identifier

        Returns:
            SearchTask instance if found, None otherwise
        """
        async with self._lock:
            return self.tasks.get(task_id)

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        results: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ) -> None:
        """
        Update task status.

        Args:
            task_id: Task identifier
            status: New status
            results: Results (if completed)
            error: Error message (if failed)
            error_traceback: Error traceback (if failed)
        """
        async with self._lock:
            if task_id not in self.tasks:
                self.logger.warning(f"Task {task_id} not found")
                return

            task = self.tasks[task_id]
            task.status = status
            task.updated_at = datetime.now()

            if results is not None:
                task.results = results
            if error is not None:
                task.error = error
                task.error_traceback = error_traceback

            self.logger.debug(f"Task {task_id} status updated to {status.value}")

    async def update_task_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        stage: str,
        message: str,
    ) -> None:
        """
        Update task progress.

        Args:
            task_id: Task identifier
            current: Current item count
            total: Total item count
            stage: Current stage
            message: Human-readable message
        """
        async with self._lock:
            if task_id not in self.tasks:
                return

            task = self.tasks[task_id]
            task.progress = TaskProgress(
                current=current,
                total=total,
                stage=stage,
                message=message,
                percentage=int(current / total * 100) if total > 0 else 0,
            )
            task.updated_at = datetime.now()

            self.logger.debug(f"Task {task_id}: {message}")

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was cancelled, False otherwise
        """
        async with self._lock:
            if task_id not in self.tasks:
                return False

            task = self.tasks[task_id]
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.CANCELLED
                task.updated_at = datetime.now()
                self.logger.info(f"Cancelled task {task_id}")
                return True
            return False

    async def cleanup_old_tasks(self, max_age_minutes: int = 30) -> int:
        """
        Clean up tasks older than max_age_minutes.

        Args:
            max_age_minutes: Maximum age in minutes (default: 30)

        Returns:
            Number of tasks cleaned up
        """
        async with self._lock:
            now = datetime.now()
            to_remove = []

            for task_id, task in self.tasks.items():
                age = (now - task.updated_at).total_seconds() / 60
                if age > max_age_minutes:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self.tasks[task_id]

            if to_remove:
                self.logger.info(f"Cleaned up {len(to_remove)} old tasks")

            return len(to_remove)

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            await asyncio.sleep(300)  # 5 minutes
            try:
                await self.cleanup_old_tasks()
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}", exc_info=True)

    async def list_active_tasks(self) -> List[Dict[str, Any]]:
        """
        List all active tasks (not completed/failed/cancelled).

        Returns:
            List of task dictionaries
        """
        async with self._lock:
            active = []
            for task in self.tasks.values():
                if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    active.append(
                        {
                            "task_id": task.task_id,
                            "status": task.status.value,
                            "query": task.query,
                            "platform": task.platform,
                            "created_at": task.created_at.isoformat(),
                            "progress": {
                                "current": task.progress.current,
                                "total": task.progress.total,
                                "stage": task.progress.stage,
                                "percentage": task.progress.percentage,
                            }
                            if task.progress
                            else None,
                        }
                    )
            return active

