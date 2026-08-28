from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from ..mesh_formats import MeshData
from .math3d import RenderCamera
from .renderer import OpenGLCapabilities, OpenGLRenderer, OpenGLUnavailable, RenderFrame


@dataclass
class _Request:
    operation: str
    kwargs: dict[str, Any]
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class OpenGLRenderService:
    """Single-context render service that keeps OpenGL on one daemon thread."""

    def __init__(self, *, backend: str = "", timeout_seconds: float = 45.0) -> None:
        self.backend = backend
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._queue: queue.Queue[_Request] = queue.Queue(maxsize=32)
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="oiec-opengl-renderer",
            daemon=True,
        )
        self._thread.start()

    def _call(self, operation: str, **kwargs: Any) -> Any:
        if self._closed:
            raise OpenGLUnavailable("OpenGL render service is closed")
        request = _Request(operation, kwargs)
        try:
            self._queue.put(request, timeout=self.timeout_seconds)
        except queue.Full as exc:
            raise OpenGLUnavailable("OpenGL render queue is full") from exc
        if not request.event.wait(self.timeout_seconds):
            raise OpenGLUnavailable(f"OpenGL operation timed out: {operation}")
        if request.error is not None:
            if isinstance(request.error, OpenGLUnavailable):
                raise request.error
            raise OpenGLUnavailable(
                f"OpenGL operation failed ({operation}): {type(request.error).__name__}: {request.error}"
            ) from request.error
        return request.result

    def capabilities(self) -> OpenGLCapabilities:
        return self._call("capabilities")

    def render(
        self,
        mesh: MeshData,
        *,
        cache_key: str,
        mode: str = "textured",
        width: int = 512,
        height: int = 512,
        camera: RenderCamera | None = None,
        model_yaw: float = 0.0,
        model_pitch: float = 0.0,
    ) -> RenderFrame:
        return self._call(
            "render",
            mesh=mesh,
            cache_key=cache_key,
            mode=mode,
            width=width,
            height=height,
            camera=camera,
            model_yaw=model_yaw,
            model_pitch=model_pitch,
        )

    def render_three_views(
        self,
        mesh: MeshData,
        *,
        cache_key: str,
        mode: str = "textured",
        size: int = 512,
        model_yaw: float = 0.0,
        model_pitch: float = 0.0,
    ) -> dict[str, RenderFrame]:
        return self._call(
            "render_three_views",
            mesh=mesh,
            cache_key=cache_key,
            mode=mode,
            size=size,
            model_yaw=model_yaw,
            model_pitch=model_pitch,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        request = _Request("shutdown", {})
        try:
            self._queue.put_nowait(request)
            request.event.wait(min(5.0, self.timeout_seconds))
        except queue.Full:
            pass

    def _run(self) -> None:
        renderer: OpenGLRenderer | None = None
        initialization_error: BaseException | None = None
        while True:
            request = self._queue.get()
            try:
                if request.operation == "shutdown":
                    if renderer is not None:
                        renderer.close()
                    request.result = True
                    return
                if renderer is None and initialization_error is None:
                    try:
                        renderer = OpenGLRenderer(backend=self.backend)
                    except BaseException as exc:  # keep one stable failure for the session
                        initialization_error = exc
                if initialization_error is not None:
                    raise initialization_error
                assert renderer is not None
                if request.operation == "capabilities":
                    request.result = renderer.capabilities()
                elif request.operation == "render":
                    request.result = renderer.render(**request.kwargs)
                elif request.operation == "render_three_views":
                    request.result = renderer.render_three_views(**request.kwargs)
                else:
                    raise ValueError(f"unknown OpenGL service operation: {request.operation}")
            except BaseException as exc:
                request.error = exc
            finally:
                request.event.set()
                self._queue.task_done()
