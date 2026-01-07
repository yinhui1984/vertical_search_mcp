"""
Unit tests for TaskManager.

Tests task creation, progress updates, status transitions, cleanup, and concurrency.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from core.task_manager import TaskManager, TaskStatus


@pytest.mark.asyncio
async def test_create_task():
    """Test task creation."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    assert task_id
    task = await manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.PENDING
    assert task.query == "test"
    assert task.platform == "weixin"
    assert task.max_results == 10


@pytest.mark.asyncio
async def test_get_task_not_found():
    """Test getting non-existent task."""
    manager = TaskManager()
    task = await manager.get_task("non-existent-id")
    assert task is None


@pytest.mark.asyncio
async def test_update_task_status():
    """Test updating task status."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    await manager.update_task_status(task_id, TaskStatus.RUNNING)
    task = await manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.RUNNING

    results = [{"title": "Test", "url": "http://test.com"}]
    await manager.update_task_status(task_id, TaskStatus.COMPLETED, results=results)
    task = await manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.results == results


@pytest.mark.asyncio
async def test_update_task_progress():
    """Test progress updates."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    await manager.update_task_progress(
        task_id=task_id,
        current=5,
        total=10,
        stage="searching",
        message="Found 5/10 results",
    )

    task = await manager.get_task(task_id)
    assert task is not None
    assert task.progress is not None
    assert task.progress.current == 5
    assert task.progress.total == 10
    assert task.progress.stage == "searching"
    assert task.progress.message == "Found 5/10 results"
    assert task.progress.percentage == 50


@pytest.mark.asyncio
async def test_update_task_progress_percentage():
    """Test progress percentage calculation."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Test 0% (current=0, total=10)
    await manager.update_task_progress(
        task_id=task_id,
        current=0,
        total=10,
        stage="searching",
        message="Starting search",
    )
    task = await manager.get_task(task_id)
    assert task.progress is not None
    assert task.progress.percentage == 0

    # Test 100% (current=10, total=10)
    await manager.update_task_progress(
        task_id=task_id,
        current=10,
        total=10,
        stage="completed",
        message="Search complete",
    )
    task = await manager.get_task(task_id)
    assert task.progress is not None
    assert task.progress.percentage == 100

    # Test edge case: total=0
    await manager.update_task_progress(
        task_id=task_id,
        current=0,
        total=0,
        stage="searching",
        message="No results",
    )
    task = await manager.get_task(task_id)
    assert task.progress is not None
    assert task.progress.percentage == 0


@pytest.mark.asyncio
async def test_status_transitions():
    """Test task status transitions."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # PENDING -> RUNNING
    await manager.update_task_status(task_id, TaskStatus.RUNNING)
    task = await manager.get_task(task_id)
    assert task.status == TaskStatus.RUNNING

    # RUNNING -> COMPLETED
    await manager.update_task_status(task_id, TaskStatus.COMPLETED, results=[])
    task = await manager.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED

    # Create new task for FAILED transition
    task_id2 = await manager.create_task(
        query="test2",
        platform="weixin",
        max_results=10,
    )
    await manager.update_task_status(task_id2, TaskStatus.RUNNING)
    await manager.update_task_status(task_id2, TaskStatus.FAILED, error="Network error")
    task = await manager.get_task(task_id2)
    assert task.status == TaskStatus.FAILED
    assert task.error == "Network error"


@pytest.mark.asyncio
async def test_cancel_task():
    """Test cancelling a running task."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Can't cancel PENDING task
    result = await manager.cancel_task(task_id)
    assert result is False

    # Can cancel RUNNING task
    await manager.update_task_status(task_id, TaskStatus.RUNNING)
    result = await manager.cancel_task(task_id)
    assert result is True
    task = await manager.get_task(task_id)
    assert task.status == TaskStatus.CANCELLED

    # Can't cancel already completed task
    task_id2 = await manager.create_task(
        query="test2",
        platform="weixin",
        max_results=10,
    )
    await manager.update_task_status(task_id2, TaskStatus.COMPLETED, results=[])
    result = await manager.cancel_task(task_id2)
    assert result is False


@pytest.mark.asyncio
async def test_cleanup_old_tasks():
    """Test automatic cleanup of old tasks."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Manually age the task
    task = await manager.get_task(task_id)
    assert task is not None
    task.updated_at = datetime.now() - timedelta(minutes=35)

    # Cleanup tasks older than 30 minutes
    cleaned = await manager.cleanup_old_tasks(max_age_minutes=30)
    assert cleaned == 1

    # Task should be removed
    task = await manager.get_task(task_id)
    assert task is None


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_tasks():
    """Test that recent tasks are not cleaned up."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Task is recent (just created)
    cleaned = await manager.cleanup_old_tasks(max_age_minutes=30)
    assert cleaned == 0

    # Task should still exist
    task = await manager.get_task(task_id)
    assert task is not None


@pytest.mark.asyncio
async def test_list_active_tasks():
    """Test listing active tasks."""
    manager = TaskManager()

    # Clean up any existing tasks first (TaskManager is singleton)
    await manager.cleanup_old_tasks(max_age_minutes=0)

    # Create multiple tasks
    await manager.create_task(
        query="test1",
        platform="weixin",
        max_results=10,
    )
    task_id2 = await manager.create_task(
        query="test2",
        platform="weixin",
        max_results=10,
    )
    task_id3 = await manager.create_task(
        query="test3",
        platform="weixin",
        max_results=10,
    )

    # Mark one as running
    await manager.update_task_status(task_id2, TaskStatus.RUNNING)
    await manager.update_task_progress(
        task_id2, current=5, total=10, stage="searching", message="Progress"
    )

    # Mark one as completed (should not appear in active list)
    await manager.update_task_status(task_id3, TaskStatus.COMPLETED, results=[])

    # List active tasks
    active = await manager.list_active_tasks()
    assert len(active) == 2  # task_id1 (PENDING) and task_id2 (RUNNING)

    # Check task_id2 has progress
    task2_info = next(t for t in active if t["task_id"] == task_id2)
    assert task2_info["status"] == "running"
    assert task2_info["progress"] is not None
    assert task2_info["progress"]["current"] == 5
    assert task2_info["progress"]["total"] == 10


@pytest.mark.asyncio
async def test_concurrent_task_creation():
    """Test concurrent task creation."""
    manager = TaskManager()

    async def create_task(i: int) -> str:
        return await manager.create_task(
            query=f"test{i}",
            platform="weixin",
            max_results=10,
        )

    # Create 10 tasks concurrently
    task_ids = await asyncio.gather(*[create_task(i) for i in range(10)])

    # All tasks should be created
    assert len(task_ids) == 10
    assert len(set(task_ids)) == 10  # All unique

    # All tasks should be retrievable
    for task_id in task_ids:
        task = await manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_concurrent_progress_updates():
    """Test concurrent progress updates."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    async def update_progress(i: int) -> None:
        await manager.update_task_progress(
            task_id=task_id,
            current=i,
            total=10,
            stage="searching",
            message=f"Progress {i}/10",
        )

    # Update progress concurrently
    await asyncio.gather(*[update_progress(i) for i in range(10)])

    # Final state should be valid (last update wins)
    task = await manager.get_task(task_id)
    assert task is not None
    assert task.progress is not None
    assert 0 <= task.progress.current <= 10


@pytest.mark.asyncio
async def test_task_error_handling():
    """Test error handling in task updates."""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Update with error
    error_msg = "Network timeout"
    error_traceback = "Traceback (most recent call last):\n..."
    await manager.update_task_status(
        task_id,
        TaskStatus.FAILED,
        error=error_msg,
        error_traceback=error_traceback,
    )

    task = await manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert task.error == error_msg
    assert task.error_traceback == error_traceback


@pytest.mark.asyncio
async def test_singleton_pattern():
    """Test that TaskManager is a singleton."""
    manager1 = TaskManager()
    manager2 = TaskManager()

    # Should be the same instance
    assert manager1 is manager2

    # Create task in one instance
    task_id = await manager1.create_task(
        query="test",
        platform="weixin",
        max_results=10,
    )

    # Should be accessible from other instance
    task = await manager2.get_task(task_id)
    assert task is not None
    assert task.query == "test"
