# Iteration 10: Async Task Design for Long-Running Searches

## Executive Summary

**Problem**: Current synchronous search can take 2-5 minutes for 30 results with content, causing AI client timeouts (typically 30-60 seconds).

**Solution**: Implement async task pattern - split long operations into:
1. Quick task start (returns task_id < 1s)
2. Status polling (returns progress/results < 1s each)
3. Background execution (managed by server)

**Benefits**:
- No client timeouts (every tool call < 30s)
- AI can actively show progress to users
- Better user experience (visible progress)
- Scalable for even longer tasks

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Client (Claude)                        │
│                                                                  │
│  1. start_vertical_search(query, ...) → {task_id: "abc123"}    │
│  2. get_search_status(task_id) → {status: "running", 5/30}     │
│  3. get_search_status(task_id) → {status: "running", 15/30}    │
│  4. get_search_status(task_id) → {status: "completed", [...]}  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ MCP Protocol (JSON-RPC 2.0)
                       │ Each call < 30s
┌──────────────────────▼───────────────────────────────────────────┐
│                        MCP Server                                 │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Task Manager (Singleton)                     │  │
│  │                                                            │  │
│  │  - create_task() → task_id                                │  │
│  │  - get_task(task_id) → status/progress/results           │  │
│  │  - update_task(task_id, progress)                         │  │
│  │  - cleanup_old_tasks() (auto-run every 5min)             │  │
│  │                                                            │  │
│  │  Task Storage (In-Memory Dict):                           │  │
│  │    "abc123": {                                             │  │
│  │      status: "running",                                    │  │
│  │      progress: {current: 15, total: 30, stage: "fetching"}│  │
│  │      results: null,                                        │  │
│  │      created_at: "2026-01-06T10:00:00Z",                  │  │
│  │      updated_at: "2026-01-06T10:02:15Z"                   │  │
│  │    }                                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Background Task (asyncio.create_task)             │  │
│  │                                                            │  │
│  │  async def _execute_search_task(task_id, params):         │  │
│  │    1. Update status to "running"                          │  │
│  │    2. Call SearchManager.search(progress_callback)        │  │
│  │    3. For each progress update:                           │  │
│  │       - Update task progress in TaskManager               │  │
│  │    4. On completion:                                       │  │
│  │       - Update status to "completed"                      │  │
│  │       - Store results in task                             │  │
│  │    5. On error:                                            │  │
│  │       - Update status to "failed"                         │  │
│  │       - Store error message                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. SearchTask Data Model

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"      # Created but not started
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Encountered error
    CANCELLED = "cancelled"  # User cancelled

@dataclass
class TaskProgress:
    """Progress information for a running task"""
    current: int          # Current item count (e.g., 15)
    total: int           # Total item count (e.g., 30)
    stage: str           # Current stage: "searching"|"resolving"|"fetching"|"compressing"
    message: str         # Human-readable message: "Fetching content for article 15/30..."
    percentage: int      # Calculated: int(current/total * 100)

@dataclass
class SearchTask:
    """Represents a single search task"""
    task_id: str                    # Unique identifier (UUID)
    status: TaskStatus              # Current status
    progress: Optional[TaskProgress] # Progress info (only when running)
    
    # Request parameters (stored for reference)
    query: str
    platform: str
    max_results: int
    time_filter: Optional[str]
    include_content: bool
    
    # Results (only when completed)
    results: Optional[List[Dict]] = None
    
    # Error info (only when failed)
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Estimated completion time (optional)
    estimated_completion: Optional[datetime] = None
```

### 2. TaskManager Class

```python
import asyncio
from typing import Dict, Optional
from uuid import uuid4
import logging

class TaskManager:
    """
    Singleton task manager for async search operations
    
    Responsibilities:
    - Create and track tasks
    - Update task progress
    - Clean up old tasks
    - Thread-safe task access
    """
    
    _instance: Optional['TaskManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.tasks: Dict[str, SearchTask] = {}
            self.logger = logging.getLogger(__name__)
            self.initialized = True
            
            # Start cleanup task
            asyncio.create_task(self._cleanup_loop())
    
    async def create_task(
        self,
        query: str,
        platform: str,
        max_results: int,
        time_filter: Optional[str] = None,
        include_content: bool = True
    ) -> str:
        """
        Create a new search task
        
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
                time_filter=time_filter,
                include_content=include_content,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            self.tasks[task_id] = task
            self.logger.info(f"Created task {task_id}: {platform}:{query}")
            
            return task_id
    
    async def get_task(self, task_id: str) -> Optional[SearchTask]:
        """Get task by ID"""
        async with self._lock:
            return self.tasks.get(task_id)
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        results: Optional[List[Dict]] = None,
        error: Optional[str] = None,
        error_traceback: Optional[str] = None
    ) -> None:
        """Update task status"""
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
    
    async def update_task_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        stage: str,
        message: str
    ) -> None:
        """Update task progress"""
        async with self._lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task.progress = TaskProgress(
                current=current,
                total=total,
                stage=stage,
                message=message,
                percentage=int(current / total * 100) if total > 0 else 0
            )
            task.updated_at = datetime.now()
            
            self.logger.debug(f"Task {task_id}: {message}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
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
        """Clean up tasks older than max_age_minutes"""
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
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while True:
            await asyncio.sleep(300)  # 5 minutes
            try:
                await self.cleanup_old_tasks()
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
    
    async def list_active_tasks(self) -> List[Dict]:
        """List all active tasks (not completed/failed/cancelled)"""
        async with self._lock:
            active = []
            for task in self.tasks.values():
                if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    active.append({
                        "task_id": task.task_id,
                        "status": task.status.value,
                        "query": task.query,
                        "platform": task.platform,
                        "created_at": task.created_at.isoformat(),
                        "progress": {
                            "current": task.progress.current,
                            "total": task.progress.total,
                            "stage": task.progress.stage,
                            "percentage": task.progress.percentage
                        } if task.progress else None
                    })
            return active
```

### 3. Background Task Execution

```python
async def _execute_search_task(
    task_id: str,
    manager: UnifiedSearchManager,
    task_manager: TaskManager
) -> None:
    """
    Execute search task in background
    
    This runs as an asyncio.create_task() and updates progress via TaskManager
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Get task details
        task = await task_manager.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
        
        # Update status to running
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING)
        
        # Define progress callback
        def progress_callback(stage: str, message: str, current: int, total: int):
            # This runs synchronously in the search code, so we need to create a task
            asyncio.create_task(
                task_manager.update_task_progress(
                    task_id=task_id,
                    current=current,
                    total=total,
                    stage=stage,
                    message=message
                )
            )
        
        # Execute search with progress callback
        results = await manager.search(
            platform=task.platform,
            query=task.query,
            max_results=task.max_results,
            time_filter=task.time_filter,
            include_content=task.include_content,
            progress_callback=progress_callback
        )
        
        # Update task with results
        await task_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            results=results
        )
        
        logger.info(f"Task {task_id} completed: {len(results)} results")
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        
        # Update task with error
        await task_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=str(e),
            error_traceback=traceback.format_exc()
        )
```

---

## MCP Tools API

### Tool 1: start_vertical_search

**Purpose**: Start an async search task, returns immediately with task_id

**Parameters**:
```json
{
  "query": {
    "type": "string",
    "description": "Search query string",
    "required": true
  },
  "platform": {
    "type": "string",
    "enum": ["weixin", "zhihu"],
    "description": "Platform to search",
    "required": true
  },
  "max_results": {
    "type": "integer",
    "description": "Maximum number of results (1-30)",
    "default": 10
  },
  "time_filter": {
    "type": "string",
    "enum": ["day", "week", "month", "year"],
    "description": "Filter results by time"
  },
  "include_content": {
    "type": "boolean",
    "description": "Whether to fetch and compress article content",
    "default": true
  }
}
```

**Response** (< 1 second):
```json
{
  "task_id": "abc123-def456-789",
  "status": "started",
  "estimated_time": "2-3 minutes for 30 results with content",
  "message": "Search task started. Use get_search_status to check progress."
}
```

**Implementation**:
```python
async def _handle_start_vertical_search(params: Dict) -> Dict:
    """Handle start_vertical_search tool call"""
    
    # Validate parameters
    query = params.get("query")
    platform = params.get("platform")
    max_results = params.get("max_results", 10)
    time_filter = params.get("time_filter")
    include_content = params.get("include_content", True)
    
    if not query or not platform:
        raise ValueError("query and platform are required")
    
    # Create task
    task_manager = TaskManager()
    task_id = await task_manager.create_task(
        query=query,
        platform=platform,
        max_results=max_results,
        time_filter=time_filter,
        include_content=include_content
    )
    
    # Start background execution
    asyncio.create_task(
        _execute_search_task(task_id, manager, task_manager)
    )
    
    # Return immediately
    return {
        "task_id": task_id,
        "status": "started",
        "estimated_time": _estimate_time(max_results, include_content),
        "message": "Search task started. Use get_search_status to check progress."
    }
```

---

### Tool 2: get_search_status

**Purpose**: Check task progress and get results when ready

**Parameters**:
```json
{
  "task_id": {
    "type": "string",
    "description": "Task ID from start_vertical_search",
    "required": true
  }
}
```

**Response - Running** (< 1 second):
```json
{
  "task_id": "abc123",
  "status": "running",
  "progress": {
    "current": 15,
    "total": 30,
    "stage": "fetching_content",
    "message": "Fetching content for article 15/30...",
    "percentage": 50
  },
  "elapsed_time": "45 seconds",
  "message": "Task still running. Call again in 10-15 seconds."
}
```

**Response - Completed** (< 1 second):
```json
{
  "task_id": "abc123",
  "status": "completed",
  "results": [
    {
      "title": "Article Title",
      "url": "https://mp.weixin.qq.com/...",
      "content": "Compressed article content...",
      ...
    }
  ],
  "total_results": 30,
  "elapsed_time": "2 minutes 15 seconds"
}
```

**Response - Failed**:
```json
{
  "task_id": "abc123",
  "status": "failed",
  "error": "Network timeout while fetching content",
  "elapsed_time": "1 minute 30 seconds"
}
```

**Implementation**:
```python
async def _handle_get_search_status(params: Dict) -> Dict:
    """Handle get_search_status tool call"""
    
    task_id = params.get("task_id")
    if not task_id:
        raise ValueError("task_id is required")
    
    task_manager = TaskManager()
    task = await task_manager.get_task(task_id)
    
    if not task:
        return {
            "task_id": task_id,
            "status": "not_found",
            "error": "Task not found. It may have expired (tasks expire after 30 minutes)."
        }
    
    elapsed = (datetime.now() - task.created_at).total_seconds()
    
    if task.status == TaskStatus.RUNNING:
        return {
            "task_id": task_id,
            "status": "running",
            "progress": {
                "current": task.progress.current,
                "total": task.progress.total,
                "stage": task.progress.stage,
                "message": task.progress.message,
                "percentage": task.progress.percentage
            } if task.progress else None,
            "elapsed_time": f"{int(elapsed)} seconds",
            "message": "Task still running. Call again in 10-15 seconds."
        }
    
    elif task.status == TaskStatus.COMPLETED:
        return {
            "task_id": task_id,
            "status": "completed",
            "results": task.results,
            "total_results": len(task.results) if task.results else 0,
            "elapsed_time": f"{int(elapsed)} seconds"
        }
    
    elif task.status == TaskStatus.FAILED:
        return {
            "task_id": task_id,
            "status": "failed",
            "error": task.error,
            "elapsed_time": f"{int(elapsed)} seconds"
        }
    
    else:  # PENDING or CANCELLED
        return {
            "task_id": task_id,
            "status": task.status.value,
            "elapsed_time": f"{int(elapsed)} seconds"
        }
```

---

### Tool 3: cancel_search (Optional)

**Purpose**: Cancel a running search task

**Parameters**:
```json
{
  "task_id": {
    "type": "string",
    "description": "Task ID to cancel",
    "required": true
  }
}
```

**Response**:
```json
{
  "task_id": "abc123",
  "status": "cancelled",
  "message": "Task cancelled successfully"
}
```

---

## AI Usage Flow Example

```python
# Typical AI conversation flow:

User: "Search for 'web3 trends 2026' on WeChat, 30 results with content"

AI (calls tool 1):
>>> start_vertical_search(query="web3 trends 2026", platform="weixin", max_results=30, include_content=True)
<<< {task_id: "abc123", status: "started", estimated_time: "2-3 minutes"}

AI (responds to user):
"I've started searching for 'web3 trends 2026' on WeChat (30 results). This will take about 2-3 minutes. Let me check the progress..."

AI (calls tool 2 after 10s):
>>> get_search_status(task_id="abc123")
<<< {status: "running", progress: {current: 5, total: 30, stage: "searching", percentage: 17}}

AI (updates user):
"Search is running... Found 5 out of 30 results so far (17% complete). Still searching..."

AI (calls tool 2 after another 10s):
>>> get_search_status(task_id="abc123")
<<< {status: "running", progress: {current: 15, total: 30, stage: "fetching_content", percentage: 50}}

AI (updates user):
"Now fetching article content... 15/30 articles processed (50% complete)..."

AI (calls tool 2 after another 10s):
>>> get_search_status(task_id="abc123")
<<< {status: "running", progress: {current: 25, total: 30, stage: "compressing", percentage: 83}}

AI (updates user):
"Almost done! Compressing content... 25/30 articles (83%)..."

AI (calls tool 2 after another 10s):
>>> get_search_status(task_id="abc123")
<<< {status: "completed", results: [{...}, {...}, ...], total_results: 30}

AI (presents results to user):
"Search complete! Found 30 articles about web3 trends in 2026. Here's a summary of the key trends..."
```

---

## Backward Compatibility

### Keep Original Tool (Deprecated)

```python
# Original tool: search_vertical (synchronous mode)
# Keep for backward compatibility but add warnings

{
  "name": "search_vertical",
  "description": "[DEPRECATED] Synchronous search - may timeout for large requests. Use start_vertical_search + get_search_status instead.",
  "inputSchema": { ... }  # Same as before
}
```

### Or: Add async_mode Parameter

```python
# Add async_mode parameter to existing tool

{
  "name": "search_vertical",
  "inputSchema": {
    "query": {...},
    "platform": {...},
    "async_mode": {
      "type": "boolean",
      "description": "If true, returns task_id immediately. If false, waits for results (may timeout).",
      "default": false
    }
  }
}

# Implementation:
if params.get("async_mode"):
    return await _handle_start_vertical_search(params)
else:
    return await _handle_sync_search(params)  # Original behavior
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_task_manager.py

async def test_create_task():
    """Test task creation"""
    manager = TaskManager()
    task_id = await manager.create_task(
        query="test",
        platform="weixin",
        max_results=10
    )
    
    assert task_id
    task = await manager.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.query == "test"

async def test_update_progress():
    """Test progress updates"""
    manager = TaskManager()
    task_id = await manager.create_task(...)
    
    await manager.update_task_progress(
        task_id=task_id,
        current=5,
        total=10,
        stage="searching",
        message="Found 5/10 results"
    )
    
    task = await manager.get_task(task_id)
    assert task.progress.current == 5
    assert task.progress.percentage == 50

async def test_cleanup_old_tasks():
    """Test automatic cleanup"""
    manager = TaskManager()
    task_id = await manager.create_task(...)
    
    # Manually age the task
    task = await manager.get_task(task_id)
    task.updated_at = datetime.now() - timedelta(minutes=35)
    
    cleaned = await manager.cleanup_old_tasks(max_age_minutes=30)
    assert cleaned == 1
    assert await manager.get_task(task_id) is None
```

### Integration Tests

```python
# tests/integration/test_async_search.py

async def test_async_search_workflow():
    """Test complete async search workflow"""
    
    # Start task
    response = await call_mcp_tool("start_vertical_search", {
        "query": "test",
        "platform": "weixin",
        "max_results": 5
    })
    
    task_id = response["task_id"]
    assert response["status"] == "started"
    
    # Poll status
    max_attempts = 20
    for i in range(max_attempts):
        response = await call_mcp_tool("get_search_status", {"task_id": task_id})
        
        if response["status"] == "completed":
            assert "results" in response
            assert len(response["results"]) <= 5
            break
        elif response["status"] == "failed":
            pytest.fail(f"Task failed: {response['error']}")
        else:
            # Still running, wait and retry
            await asyncio.sleep(2)
    else:
        pytest.fail("Task did not complete in time")

async def test_concurrent_tasks():
    """Test multiple concurrent tasks"""
    
    # Start 3 tasks
    task_ids = []
    for i in range(3):
        response = await call_mcp_tool("start_vertical_search", {
            "query": f"test {i}",
            "platform": "weixin",
            "max_results": 3
        })
        task_ids.append(response["task_id"])
    
    # Wait for all to complete
    completed = 0
    max_attempts = 30
    
    for _ in range(max_attempts):
        for task_id in task_ids:
            response = await call_mcp_tool("get_search_status", {"task_id": task_id})
            if response["status"] == "completed":
                completed += 1
        
        if completed == 3:
            break
        
        await asyncio.sleep(2)
    
    assert completed == 3
```

---

## Performance Benchmarks

### Expected Timings

| Operation | Expected Time | Acceptable Range |
|-----------|---------------|------------------|
| start_vertical_search | < 1 second | 0.1-2 seconds |
| get_search_status (running) | < 1 second | 0.1-1 second |
| get_search_status (completed) | < 1 second | 0.5-2 seconds |
| Full search (10 results, no content) | 30-45 seconds | 20-60 seconds |
| Full search (30 results + content) | 2-3 minutes | 1-5 minutes |

### Load Testing

```python
async def test_high_load():
    """Test 10 concurrent long searches"""
    
    tasks = []
    for i in range(10):
        task = call_mcp_tool("start_vertical_search", {
            "query": f"test {i}",
            "platform": "weixin",
            "max_results": 10,
            "include_content": True
        })
        tasks.append(task)
    
    responses = await asyncio.gather(*tasks)
    
    # All should start quickly
    for response in responses:
        assert response["status"] == "started"
    
    # Monitor completion
    # ... (similar to concurrent test)
```

---

## Migration Guide for AI

### Old Way (Synchronous - May Timeout)

```python
# AI makes one call and waits (may timeout after 30-60s)
response = search_vertical(
    query="web3 trends",
    platform="weixin",
    max_results=30,
    include_content=True
)
# May fail with timeout error!
```

### New Way (Async - No Timeout)

```python
# Step 1: Start task (< 1s)
response = start_vertical_search(
    query="web3 trends",
    platform="weixin",
    max_results=30,
    include_content=True
)
task_id = response["task_id"]

# Step 2-N: Poll status every 10-15s
while True:
    response = get_search_status(task_id=task_id)
    
    if response["status"] == "completed":
        results = response["results"]
        break
    elif response["status"] == "failed":
        # Handle error
        break
    else:
        # Show progress to user
        # Wait 10-15 seconds before next poll
        await sleep(10)
```

---

## Error Handling

### Task Not Found

```python
response = get_search_status(task_id="invalid-id")
# Returns:
{
  "status": "not_found",
  "error": "Task not found. It may have expired (tasks expire after 30 minutes)."
}
```

### Task Failed

```python
response = get_search_status(task_id="abc123")
# Returns:
{
  "status": "failed",
  "error": "Network timeout while fetching content for article 15/30",
  "elapsed_time": "90 seconds"
}
```

### Graceful Degradation

```python
# If background task fails, log error but don't crash server
try:
    await _execute_search_task(task_id, manager, task_manager)
except Exception as e:
    logger.error(f"Task {task_id} failed: {e}", exc_info=True)
    await task_manager.update_task_status(
        task_id=task_id,
        status=TaskStatus.FAILED,
        error=str(e)
    )
```

---

## Documentation Updates

### README.md

```markdown
## Async Search for Long Tasks

For searches that may take >1 minute (e.g., 30 results with content), use the async API:

### Quick Example

```python
# Start search
response = start_vertical_search(
    query="web3 trends 2026",
    platform="weixin",
    max_results=30,
    include_content=True
)
task_id = response["task_id"]

# Poll for results
while True:
    status = get_search_status(task_id=task_id)
    
    if status["status"] == "completed":
        results = status["results"]
        break
    elif status["status"] == "running":
        print(f"Progress: {status['progress']['percentage']}%")
        time.sleep(10)  # Wait 10 seconds before next check
```

### When to Use Async vs Sync

- **Use Async** (`start_vertical_search` + `get_search_status`):
  - max_results > 10
  - include_content = True
  - Any search that might take >1 minute

- **Use Sync** (`search_vertical`):
  - max_results <= 10
  - include_content = False
  - Quick searches that return in <30 seconds
```

---

## Implementation Checklist

### Phase 1: Core Components (Day 1 Morning)

- [ ] Create `core/task_manager.py`
  - [ ] SearchTask dataclass
  - [ ] TaskStatus enum
  - [ ] TaskProgress dataclass
  - [ ] TaskManager class
  - [ ] Background cleanup loop
  
- [ ] Create unit tests (`tests/unit/test_task_manager.py`)
  - [ ] Test task creation
  - [ ] Test progress updates
  - [ ] Test status transitions
  - [ ] Test cleanup

### Phase 2: MCP Integration (Day 1 Afternoon)

- [ ] Add tools to `mcp_server.py`
  - [ ] `start_vertical_search`
  - [ ] `get_search_status`
  - [ ] `cancel_search` (optional)
  
- [ ] Implement background execution
  - [ ] `_execute_search_task` function
  - [ ] Progress callback integration
  
- [ ] Add integration tests (`tests/integration/test_async_search.py`)
  - [ ] Test full workflow
  - [ ] Test concurrent tasks
  - [ ] Test error handling

### Phase 3: Progress Callbacks (Day 2 Morning)

- [ ] Add progress callback to SearchManager
- [ ] Add progress callback to ContentProcessor
- [ ] Add progress callback to URLResolver
- [ ] Test progress updates at each stage

### Phase 4: Testing & Documentation (Day 2 Afternoon)

- [ ] End-to-end tests
- [ ] Load tests (10 concurrent tasks)
- [ ] Update README.md
- [ ] Update design docs
- [ ] Create migration guide

---

## Success Criteria

✅ **All tool calls return in < 5 seconds**
- Measured: Time from request to response for each tool
- Target: < 5 seconds (90th percentile)

✅ **Long searches complete successfully**
- Measured: Success rate for 30 results + content
- Target: > 95% success rate

✅ **Progress updates are accurate**
- Measured: Progress percentage matches actual completion
- Target: ±5% accuracy

✅ **No memory leaks**
- Measured: Memory usage over 100 concurrent tasks
- Target: Stable memory, old tasks cleaned up

✅ **Concurrent tasks don't interfere**
- Measured: 10 concurrent tasks all complete
- Target: 100% completion rate

---

## Future Enhancements

### Persistent Storage (Optional)

Replace in-memory dict with Redis/SQLite for:
- Task survival across server restarts
- Better scalability
- Task history/analytics

### Webhooks (Optional)

```python
# Instead of polling, client provides callback URL
start_vertical_search(
    ...,
    webhook_url="https://client.com/callback"
)

# Server POSTs to webhook when complete
POST https://client.com/callback
{
  "task_id": "abc123",
  "status": "completed",
  "results": [...]
}
```

### Priority Queue (Optional)

```python
start_vertical_search(
    ...,
    priority="high"  # high/normal/low
)
```

---

## Appendix: Comparison with Other Solutions

### Why Not Use MCP Progress Notifications?

**Problem**: Progress notifications don't reset client timeout

```python
# Progress notification approach (DOESN'T WORK):
1. start_search_vertical()
2. send_progress_notification("searching...")
3. send_progress_notification("fetching...")
# Client times out after 30-60s even with notifications!
```

**Why**: Notifications are one-way, don't affect the RPC call timeout

### Why Not Use isIncomplete?

**Problem**: Still a single long RPC call

```python
# isIncomplete approach (DOESN'T WORK):
1. search_vertical() starts
2. Return {isIncomplete: true, message: "Searching..."}
3. Continue searching...
4. Return {isIncomplete: false, results: [...]}
# Client times out waiting for final response!
```

**Why**: The client waits for the complete response, not intermediate ones

### Why Async Tasks Work

**Key Difference**: Each RPC call completes quickly

```python
# Async approach (WORKS):
1. start_search() → returns in <1s → RPC complete ✓
2. get_status() → returns in <1s → RPC complete ✓
3. get_status() → returns in <1s → RPC complete ✓
4. get_status() → returns results in <1s → RPC complete ✓
# No timeout because each call is fast!
```

**Why**: Multiple short calls instead of one long call

---

**End of Design Document**
