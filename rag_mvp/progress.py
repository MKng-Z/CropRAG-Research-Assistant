from dataclasses import dataclass, asdict
from datetime import datetime
from threading import Lock

from rag_mvp.schemas import ProgressResponse


@dataclass
class ProgressState:
    operation: str
    status: str = "idle"
    stage: str = "waiting"
    progress: float = 0.0
    current_item: str | None = None
    completed_steps: int = 0
    total_steps: int = 0
    message: str = ""
    started_at: str | None = None
    updated_at: str | None = None
    error: str | None = None


class ProgressTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._states = {
            "index": ProgressState(operation="index"),
            "graph": ProgressState(operation="graph"),
        }

    def start(self, operation: str, total_steps: int, message: str, stage: str = "starting") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._states[operation] = ProgressState(
                operation=operation,
                status="running",
                stage=stage,
                progress=0.0,
                total_steps=total_steps,
                message=message,
                started_at=now,
                updated_at=now,
            )

    def update(
        self,
        operation: str,
        *,
        stage: str,
        progress: float,
        current_item: str | None = None,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        message: str | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            state = self._states[operation]
            state.stage = stage
            state.progress = max(0.0, min(1.0, progress))
            state.current_item = current_item
            if completed_steps is not None:
                state.completed_steps = completed_steps
            if total_steps is not None:
                state.total_steps = total_steps
            if message is not None:
                state.message = message
            state.updated_at = now

    def finish(self, operation: str, message: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            state = self._states[operation]
            state.status = "completed"
            state.stage = "done"
            state.progress = 1.0
            state.message = message
            state.updated_at = now
            state.error = None

    def fail(self, operation: str, error: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            state = self._states[operation]
            state.status = "failed"
            state.stage = "failed"
            state.message = "Operation failed"
            state.updated_at = now
            state.error = error

    def get(self, operation: str) -> ProgressResponse:
        with self._lock:
            return ProgressResponse(**asdict(self._states[operation]))
