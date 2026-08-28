from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Iterable

from ..events import AgentEvent
from ..state import GuiChatMessage


class ConversationView(ttk.Frame):
    MAX_NOTICES = 100
    MAX_ACTIVITY_ROWS = 250

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_send: Callable[[str], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_new_chat: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_send = on_send or (lambda message: None)
        self.on_stop = on_stop or (lambda: None)
        self.on_new_chat = on_new_chat or (lambda: None)
        self._messages: tuple[GuiChatMessage, ...] = ()
        self._notices: list[tuple[str, str]] = []
        self._chat_status = "idle"

        header = ttk.Frame(self, padding=(6, 6, 6, 3))
        header.pack(fill="x")
        ttk.Label(header, text="Governed Agent Chat", style="Heading.TLabel").pack(side="left")
        self.context_label = ttk.Label(header, text="Context: 0 messages")
        self.context_label.pack(side="left", padx=12)
        self.status_label = ttk.Label(header, text="IDLE")
        self.status_label.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="New Chat", command=self._new_chat).pack(side="right")

        transcript_frame = ttk.Frame(self)
        transcript_frame.pack(fill="both", expand=True, padx=6)
        self.text = ScrolledText(
            transcript_frame,
            wrap="word",
            state="disabled",
            padx=12,
            pady=10,
            spacing1=3,
            spacing3=8,
        )
        self.text.pack(fill="both", expand=True)
        self.text.tag_configure("role_user", foreground="#72b7ff", font=("TkDefaultFont", 10, "bold"))
        self.text.tag_configure("role_assistant", foreground="#7bd88f", font=("TkDefaultFont", 10, "bold"))
        self.text.tag_configure("role_system", foreground="#c8a96b", font=("TkDefaultFont", 10, "bold"))
        self.text.tag_configure("role_error", foreground="#ff7b72", font=("TkDefaultFont", 10, "bold"))
        self.text.tag_configure("content", lmargin1=8, lmargin2=8)
        self.text.tag_configure("context_boundary", foreground="#999999", justify="center")

        activity_frame = ttk.LabelFrame(self, text="Agent Activity", padding=4)
        activity_frame.pack(fill="x", padx=6, pady=(5, 3))
        self.activity = ttk.Treeview(
            activity_frame,
            columns=("kind", "detail"),
            show="headings",
            height=5,
        )
        self.activity.heading("kind", text="Event")
        self.activity.heading("detail", text="Detail")
        self.activity.column("kind", width=130, stretch=False)
        self.activity.column("detail", width=600, stretch=True)
        activity_scroll = ttk.Scrollbar(activity_frame, orient="vertical", command=self.activity.yview)
        self.activity.configure(yscrollcommand=activity_scroll.set)
        self.activity.pack(side="left", fill="x", expand=True)
        activity_scroll.pack(side="right", fill="y")

        composer_frame = ttk.Frame(self, padding=(6, 3, 6, 6))
        composer_frame.pack(fill="x")
        self.composer = tk.Text(composer_frame, height=5, wrap="word", undo=True)
        self.composer.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.composer.bind("<Return>", self._return_pressed)
        composer_frame.columnconfigure(0, weight=1)
        composer_frame.rowconfigure(0, weight=1)
        self.send_button = ttk.Button(composer_frame, text="Send", command=self._send)
        self.send_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        self.stop_button = ttk.Button(composer_frame, text="Stop", command=self._stop, state="disabled")
        self.stop_button.grid(row=1, column=1, padx=(6, 0), pady=(4, 0), sticky="ew")
        ttk.Label(
            composer_frame,
            text=(
                "Enter sends • Shift+Enter inserts a newline • @img references attach registered "
                "images • mutations still require authority and evidence"
            ),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _return_pressed(self, event: tk.Event) -> str | None:
        if event.state & 0x0001:
            return None
        self._send()
        return "break"

    def _send(self) -> None:
        message = self.composer.get("1.0", "end-1c").strip()
        if not message or self._chat_status != "idle":
            return
        try:
            self.on_send(message)
        except Exception as exc:
            self.append("Error", f"{type(exc).__name__}: {exc}")
            return
        self.composer.delete("1.0", "end")

    def _stop(self) -> None:
        if self._chat_status not in {"running", "stopping"}:
            return
        try:
            self.on_stop()
        except Exception as exc:
            self.append("Error", f"{type(exc).__name__}: {exc}")

    def _new_chat(self) -> None:
        if self._chat_status != "idle":
            return
        try:
            self.on_new_chat()
        except Exception as exc:
            self.append("Error", f"{type(exc).__name__}: {exc}")

    def append(self, role: str, message: str) -> None:
        self._notices.append((role, message))
        self._notices = self._notices[-self.MAX_NOTICES :]
        self._render()

    def set_state(
        self,
        messages: Iterable[GuiChatMessage],
        *,
        status: str,
        context_start: int,
    ) -> None:
        self._messages = tuple(messages)
        self._chat_status = status
        active_count = max(0, len(self._messages) - max(0, context_start))
        self.context_label.configure(
            text=f"Context: {active_count} / {len(self._messages)} messages"
        )
        self.status_label.configure(text=status.upper())
        running = status in {"running", "stopping"}
        self.send_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.composer.configure(state="disabled" if running else "normal")
        self._render(context_start=context_start)

    def append_activity(self, event: AgentEvent) -> None:
        payload = dict(event.payload)
        trace_type = str(payload.get("trace_type", event.event_type.value))
        trace_payload = payload.get("trace_payload", payload)
        if isinstance(trace_payload, dict):
            name = trace_payload.get("name") or trace_payload.get("step") or trace_payload.get("status")
            detail = f"{name}: {trace_payload}" if name not in {None, ""} else str(trace_payload)
        else:
            detail = str(trace_payload)
        if len(detail) > 2_000:
            detail = detail[:2_000] + "[truncated]"
        self.activity.insert("", "end", values=(trace_type, detail))
        children = self.activity.get_children()
        if len(children) > self.MAX_ACTIVITY_ROWS:
            self.activity.delete(*children[: len(children) - self.MAX_ACTIVITY_ROWS])
        latest = self.activity.get_children()
        if latest:
            self.activity.see(latest[-1])

    def focus_composer(self) -> None:
        if self._chat_status == "idle":
            self.composer.focus_set()

    def set_draft(self, text: str) -> None:
        if self._chat_status != "idle":
            return
        self.composer.delete("1.0", "end")
        self.composer.insert("1.0", text)
        self.focus_composer()

    def insert_text(self, text: str) -> None:
        if self._chat_status != "idle" or not text:
            return
        current = self.composer.get("1.0", "end-1c")
        if current and not current.endswith((" ", "\n")):
            self.composer.insert("end", " ")
        self.composer.insert("end", text)
        self.composer.insert("end", " ")
        self.composer.see("end")
        self.focus_composer()

    def _render(self, *, context_start: int = 0) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for index, message in enumerate(self._messages):
            if context_start and index == context_start:
                self.text.insert("end", "──────── New model context ────────\n\n", "context_boundary")
            role = message.role.casefold()
            label = {
                "user": "You",
                "assistant": "OIEC-STM-Agent",
                "system": "System",
                "error": "Error",
            }.get(role, message.role.title() or "Message")
            tag = f"role_{role}" if role in {"user", "assistant", "system", "error"} else "role_system"
            self.text.insert("end", f"{label}\n", tag)
            self.text.insert("end", f"{message.content}\n\n", "content")
        for role, message in self._notices:
            normalized = role.casefold()
            tag = f"role_{normalized}" if normalized in {"user", "assistant", "system", "error"} else "role_system"
            self.text.insert("end", f"{role}\n", tag)
            self.text.insert("end", f"{message}\n\n", "content")
        self.text.see("end")
        self.text.configure(state="disabled")
