from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from ..events import AgentEvent, AgentEventType
from ..replay_models import state_at
from ..state import GuiTask
from ..widgets.json_view import JsonView


class ReplayView(ttk.Frame):
    PLAY_INTERVAL_MS = 400

    def __init__(
        self,
        master: tk.Misc,
        event_supplier: Callable[[], Iterable[AgentEvent]],
        on_cursor: Callable[[int], None],
        on_plan_replay: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.event_supplier = event_supplier
        self.on_cursor = on_cursor
        self.on_plan_replay = on_plan_replay
        self.events: list[AgentEvent] = []
        self.cursor = -1
        self.playing = False
        self.reduced_motion = False
        self.plan_id = ""
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Play", command=self.play).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Pause", command=self.pause).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Step", command=self.step).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Jump to Action", command=self.jump_action).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Jump to Failure", command=self.jump_failure).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Governed Plan Replay", command=self.replay_plan).pack(side="right", padx=2)
        self.position = ttk.Label(self, text="No events")
        self.position.pack(fill="x", padx=4)
        self.scale = ttk.Scale(self, from_=0, to=0, command=self._scaled)
        self.scale.pack(fill="x", padx=4)
        self.details = JsonView(self)
        self.details.pack(fill="both", expand=True)
        self.refresh()

    def set_task(self, task: GuiTask | None) -> None:
        self.plan_id = (
            task.execution_plan_ids[-1]
            if task is not None and task.execution_plan_ids
            else ""
        )

    def refresh(self) -> None:
        self.events = list(self.event_supplier())
        self.scale.configure(to=max(0, len(self.events) - 1))
        self.cursor = len(self.events) - 1
        self._show()

    def play(self) -> None:
        if self.reduced_motion:
            self.step()
            return
        if not self.events:
            return
        if self.cursor >= len(self.events) - 1:
            self.cursor = -1
        self.playing = True
        self._tick()

    def pause(self) -> None:
        self.playing = False

    def step(self) -> None:
        if self.cursor < len(self.events) - 1:
            self.cursor += 1
            self._show()

    def jump_action(self) -> None:
        self._jump({AgentEventType.ACTION_STARTED, AgentEventType.ACTION_FINISHED})

    def jump_failure(self) -> None:
        self._jump({AgentEventType.FAILURE_DETECTED, AgentEventType.UI_ERROR})

    def replay_plan(self) -> None:
        if self.plan_id and self.on_plan_replay is not None:
            self.on_plan_replay(self.plan_id)

    def _jump(self, types: set[AgentEventType]) -> None:
        for index in range(self.cursor + 1, len(self.events)):
            if self.events[index].event_type in types:
                self.cursor = index
                self._show()
                return

    def _tick(self) -> None:
        if not self.playing:
            return
        if self.cursor >= len(self.events) - 1:
            self.playing = False
            return
        self.cursor += 1
        self._show()
        self.after(self.PLAY_INTERVAL_MS, self._tick)

    def _scaled(self, value: str) -> None:
        if not self.events:
            return
        self.cursor = min(len(self.events) - 1, max(0, int(float(value))))
        self._show(update_scale=False)

    def _show(self, *, update_scale: bool = True) -> None:
        if not self.events or self.cursor < 0:
            self.position.configure(text="No events")
            self.details.set_value({})
            self.on_cursor(-1)
            return
        if update_scale:
            self.scale.set(self.cursor)
        event = self.events[self.cursor]
        projection = state_at(self.events, self.cursor)
        self.position.configure(
            text=f"Event {self.cursor + 1}/{len(self.events)} — {event.event_type.value}"
        )
        self.details.set_value(
            {
                "event": event.to_dict(),
                "projection_digest": projection.digest,
                "selected_task_id": projection.selected_task_id,
                "selected_object_id": projection.selected_object_id,
                "worker_status": projection.worker_status,
                "reexecutes_core": False,
            }
        )
        self.on_cursor(self.cursor)

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = bool(enabled)
        if self.reduced_motion:
            self.pause()
