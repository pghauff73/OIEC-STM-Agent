from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Iterable

from ..activity_projection import project_agent_activity
from ..events import AgentEvent
from ..icpi_prompt import ICPICommandHistory, ICPI_IDLE_PREVIEW, complete_slash_command
from ..state import GuiChatMessage
from ..visual_text import (
    DEFAULT_VISUAL_TEXT_THEME,
    InlineSpan,
    parse_visual_text,
    visual_theme,
    visual_theme_for_label,
    visual_theme_labels,
)


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
        on_preview: Callable[[str], str] | None = None,
        on_suggestions: Callable[[str], tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_send = on_send or (lambda message: None)
        self.on_stop = on_stop or (lambda: None)
        self.on_new_chat = on_new_chat or (lambda: None)
        self.on_preview = on_preview or (lambda text: ICPI_IDLE_PREVIEW)
        self.on_suggestions = on_suggestions or (lambda text: ())
        self.history = ICPICommandHistory()
        self._messages: tuple[GuiChatMessage, ...] = ()
        self._notices: list[tuple[str, str]] = []
        self._chat_status = "idle"
        self._context_start = 0
        self.visual_formatting = tk.BooleanVar(value=True)
        self.visual_theme = tk.StringVar(
            value=visual_theme(DEFAULT_VISUAL_TEXT_THEME).label
        )

        header = ttk.Frame(self, padding=(6, 6, 6, 3))
        header.pack(fill="x")
        ttk.Label(header, text="OIEC-STM-SR-AgentICPI", style="Heading.TLabel").pack(side="left")
        self.context_label = ttk.Label(header, text="Context: 0 messages")
        self.context_label.pack(side="left", padx=12)
        self.status_label = ttk.Label(header, text="IDLE")
        self.status_label.pack(side="right", padx=(8, 0))
        self.new_chat_button = ttk.Button(header, text="New Chat", command=self._new_chat)
        self.new_chat_button.pack(side="right")
        self.visual_toggle = ttk.Checkbutton(
            header,
            text="Visual formatting",
            variable=self.visual_formatting,
            command=self._formatting_changed,
        )
        self.visual_toggle.pack(side="right", padx=(10, 4))
        self.theme_choice = ttk.Combobox(
            header,
            textvariable=self.visual_theme,
            values=visual_theme_labels(),
            state="readonly",
            width=20,
        )
        self.theme_choice.bind("<<ComboboxSelected>>", self._theme_changed)
        self.theme_choice.pack(side="right", padx=(4, 0))
        ttk.Label(header, text="Theme").pack(side="right")

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
        self._plain_text_options = {
            option: self.text.cget(option)
            for option in (
                "background",
                "foreground",
                "selectbackground",
                "selectforeground",
                "insertbackground",
                "relief",
                "borderwidth",
            )
        }
        self._configure_transcript_style()

        activity_frame = ttk.LabelFrame(self, text="Agent Activity (key events)", padding=4)
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
        self.composer.bind("<KeyRelease>", self._composer_changed)
        self.composer.bind("<Control-Up>", self._history_previous)
        self.composer.bind("<Control-Down>", self._history_next)
        self.composer.bind("<Tab>", self._complete_slash)
        composer_frame.columnconfigure(0, weight=1)
        composer_frame.rowconfigure(0, weight=1)
        self.send_button = ttk.Button(composer_frame, text="Send", command=self._send)
        self.send_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        self.stop_button = ttk.Button(composer_frame, text="Stop", command=self._stop, state="disabled")
        self.stop_button.grid(row=1, column=1, padx=(6, 0), pady=(4, 0), sticky="ew")
        self.route_preview = tk.StringVar(value=ICPI_IDLE_PREVIEW)
        ttk.Label(
            composer_frame,
            textvariable=self.route_preview,
            style="Heading.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.suggestion_text = tk.StringVar(value="")
        ttk.Label(
            composer_frame,
            textvariable=self.suggestion_text,
            wraplength=900,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(
            composer_frame,
            text=(
                "Enter sends • Shift+Enter inserts a newline • Ctrl+Up/Down recalls prompt history • "
                "Tab completes / commands • @file[path] binds context • authority remains external"
            ),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def set_visual_preferences(self, enabled: bool, theme_key: str) -> None:
        self.visual_formatting.set(bool(enabled))
        self.visual_theme.set(visual_theme(theme_key).label)
        self._configure_transcript_style()
        self._render()

    def visual_preferences(self) -> dict[str, object]:
        return {
            "chat_visual_formatting": bool(self.visual_formatting.get()),
            "chat_visual_theme": visual_theme_for_label(self.visual_theme.get()).key,
        }

    def _formatting_changed(self) -> None:
        self._configure_transcript_style()
        self._render()

    def _theme_changed(self, event: tk.Event | None = None) -> None:
        del event
        self._configure_transcript_style()
        self._render()

    def _configure_transcript_style(self) -> None:
        visual = bool(self.visual_formatting.get())
        self.theme_choice.configure(state="readonly" if visual else "disabled")
        if not visual:
            self.text.configure(**self._plain_text_options)
            for role, color in (
                ("user", "#72b7ff"),
                ("assistant", "#7bd88f"),
                ("system", "#c8a96b"),
                ("error", "#ff7b72"),
            ):
                self.text.tag_configure(
                    f"role_{role}",
                    foreground=color,
                    background="",
                    font=("TkDefaultFont", 10, "bold"),
                    lmargin1=0,
                    lmargin2=0,
                    rmargin=0,
                    spacing1=0,
                    spacing3=0,
                )
            self.text.tag_configure(
                "content",
                foreground="",
                background="",
                font="",
                lmargin1=8,
                lmargin2=8,
                rmargin=0,
                spacing1=0,
                spacing3=0,
            )
            self.text.tag_configure(
                "context_boundary",
                foreground="#999999",
                background="",
                justify="center",
            )
            return

        theme = visual_theme_for_label(self.visual_theme.get())
        self.text.configure(
            background=theme.background,
            foreground=theme.foreground,
            selectbackground=theme.selection,
            selectforeground=theme.foreground,
            insertbackground=theme.foreground,
            relief="flat",
            borderwidth=0,
        )
        role_surfaces = {
            "user": theme.alternate_surface,
            "assistant": theme.surface,
            "system": theme.background,
            "error": theme.surface,
        }
        role_colors = {
            "user": theme.user,
            "assistant": theme.assistant,
            "system": theme.system,
            "error": theme.error,
        }
        for role in ("user", "assistant", "system", "error"):
            self.text.tag_configure(
                f"message_{role}",
                foreground=theme.foreground,
                background=role_surfaces[role],
                lmargin1=18,
                lmargin2=18,
                rmargin=18,
                spacing1=1,
                spacing3=1,
            )
            self.text.tag_configure(
                f"role_{role}",
                foreground=role_colors[role],
                background=role_surfaces[role],
                font=("TkDefaultFont", 10, "bold"),
                lmargin1=18,
                lmargin2=18,
                rmargin=18,
                spacing1=8,
                spacing3=2,
            )
        self.text.tag_configure(
            "context_boundary",
            foreground=theme.muted,
            background=theme.background,
            justify="center",
            spacing1=6,
            spacing3=6,
        )
        self.text.tag_configure("paragraph", spacing3=3)
        self.text.tag_configure(
            "strong",
            foreground=theme.emphasis,
            font=("TkDefaultFont", 10, "bold"),
        )
        self.text.tag_configure(
            "emphasis",
            foreground=theme.emphasis,
            font=("TkDefaultFont", 10, "italic"),
        )
        self.text.tag_configure(
            "inline_code",
            foreground=theme.code_foreground,
            background=theme.code_background,
            font="TkFixedFont",
        )
        self.text.tag_configure(
            "link",
            foreground=theme.link,
            underline=True,
        )
        self.text.tag_configure(
            "quote",
            foreground=theme.quote,
            lmargin1=34,
            lmargin2=34,
            rmargin=28,
            spacing1=3,
            spacing3=3,
        )
        self.text.tag_configure(
            "quote_marker",
            foreground=theme.quote,
            font=("TkDefaultFont", 11, "bold"),
        )
        self.text.tag_configure(
            "code_label",
            foreground=theme.muted,
            background=theme.code_background,
            font=("TkDefaultFont", 9, "bold"),
            lmargin1=30,
            lmargin2=30,
            rmargin=30,
        )
        self.text.tag_configure(
            "code_block",
            foreground=theme.code_foreground,
            background=theme.code_background,
            font="TkFixedFont",
            lmargin1=30,
            lmargin2=30,
            rmargin=30,
            spacing1=2,
            spacing3=5,
        )
        self.text.tag_configure(
            "list_marker",
            foreground=theme.emphasis,
            font=("TkDefaultFont", 10, "bold"),
        )
        for level in range(5):
            margin = 28 + level * 18
            self.text.tag_configure(
                f"list_{level}",
                lmargin1=margin,
                lmargin2=margin + 18,
                rmargin=24,
                spacing3=2,
            )
        heading_sizes = (17, 15, 13, 12, 11, 10)
        for level, size in enumerate(heading_sizes, start=1):
            self.text.tag_configure(
                f"heading_{level}",
                foreground=theme.heading,
                font=("TkDefaultFont", size, "bold"),
                spacing1=6,
                spacing3=4,
            )
        self.text.tag_configure(
            "divider",
            foreground=theme.divider,
            justify="center",
            spacing1=4,
            spacing3=4,
        )
        for tag in (
            "paragraph",
            "quote",
            "code_label",
            "code_block",
            "list_marker",
            "heading_1",
            "heading_2",
            "heading_3",
            "heading_4",
            "heading_5",
            "heading_6",
            "strong",
            "emphasis",
            "inline_code",
            "link",
        ):
            self.text.tag_raise(tag)

    def _composer_text(self) -> str:
        return self.composer.get("1.0", "end-1c")

    def _replace_composer(self, text: str) -> None:
        self.composer.delete("1.0", "end")
        self.composer.insert("1.0", text)
        self.composer.mark_set("insert", "end-1c")
        self._update_icpi_feedback()

    def _update_icpi_feedback(self) -> None:
        text = self._composer_text()
        try:
            preview = self.on_preview(text)
        except Exception as exc:
            preview = f"BLOCKED · {type(exc).__name__}: {exc}"
        try:
            suggestions = self.on_suggestions(text)
        except Exception:
            suggestions = ()
        self.route_preview.set(preview or ICPI_IDLE_PREVIEW)
        self.suggestion_text.set("   ".join(suggestions))

    def _composer_changed(self, event: tk.Event | None = None) -> None:
        del event
        self._update_icpi_feedback()

    def _history_previous(self, event: tk.Event | None = None) -> str:
        del event
        self._replace_composer(self.history.previous(self._composer_text()))
        return "break"

    def _history_next(self, event: tk.Event | None = None) -> str:
        del event
        self._replace_composer(self.history.next(self._composer_text()))
        return "break"

    def _complete_slash(self, event: tk.Event | None = None) -> str | None:
        del event
        current = self._composer_text()
        completed = complete_slash_command(current)
        if completed == current:
            return None
        self._replace_composer(completed)
        return "break"

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
        self.history.record(message)
        self.composer.delete("1.0", "end")
        self._update_icpi_feedback()

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
        self._context_start = max(0, context_start)
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
        projection = project_agent_activity(event)
        if projection is None:
            return
        kind, detail = projection
        self.activity.insert("", "end", values=(kind, detail))
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
        self._update_icpi_feedback()
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
        self._update_icpi_feedback()
        self.focus_composer()

    @staticmethod
    def _role_details(role: str) -> tuple[str, str]:
        normalized = role.casefold()
        label = {
            "user": "You",
            "assistant": "OIEC-STM-SR-AgentICPI",
            "system": "System",
            "error": "Error",
        }.get(normalized, role.title() or "Message")
        if normalized not in {"user", "assistant", "system", "error"}:
            normalized = "system"
        return normalized, label

    def _insert_inline_spans(
        self,
        spans: tuple[InlineSpan, ...],
        *,
        surface_tag: str,
        block_tag: str,
    ) -> None:
        for span in spans:
            tags = [surface_tag, block_tag]
            if span.style != "body":
                tags.append(span.style)
            self.text.insert("end", span.text, tuple(tags))

    def _insert_visual_content(self, content: str, *, surface_tag: str) -> None:
        blocks = parse_visual_text(content)
        if not blocks:
            self.text.insert("end", "\n", surface_tag)
            return
        for block in blocks:
            if block.kind == "blank":
                self.text.insert("end", "\n", surface_tag)
                continue
            if block.kind == "divider":
                self.text.insert(
                    "end",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                    (surface_tag, "divider"),
                )
                continue
            if block.kind == "code":
                if block.language:
                    self.text.insert(
                        "end",
                        f"CODE · {block.language}\n",
                        (surface_tag, "code_label"),
                    )
                self.text.insert(
                    "end",
                    f"{block.text}\n",
                    (surface_tag, "code_block"),
                )
                continue
            if block.kind == "heading":
                heading_tag = f"heading_{max(1, min(block.level, 6))}"
                self._insert_inline_spans(
                    block.spans,
                    surface_tag=surface_tag,
                    block_tag=heading_tag,
                )
                self.text.insert("end", "\n", (surface_tag, heading_tag))
                continue
            if block.kind == "quote":
                self.text.insert("end", "│ ", (surface_tag, "quote", "quote_marker"))
                self._insert_inline_spans(
                    block.spans,
                    surface_tag=surface_tag,
                    block_tag="quote",
                )
                self.text.insert("end", "\n", (surface_tag, "quote"))
                continue
            if block.kind == "list":
                list_tag = f"list_{max(0, min(block.level, 4))}"
                self.text.insert(
                    "end",
                    f"{block.marker} ",
                    (surface_tag, list_tag, "list_marker"),
                )
                self._insert_inline_spans(
                    block.spans,
                    surface_tag=surface_tag,
                    block_tag=list_tag,
                )
                self.text.insert("end", "\n", (surface_tag, list_tag))
                continue
            self._insert_inline_spans(
                block.spans,
                surface_tag=surface_tag,
                block_tag="paragraph",
            )
            self.text.insert("end", "\n", (surface_tag, "paragraph"))

    def _insert_visual_message(self, role: str, label: str, content: str) -> None:
        surface_tag = f"message_{role}"
        self.text.insert("end", f"{label}\n", (surface_tag, f"role_{role}"))
        self._insert_visual_content(content, surface_tag=surface_tag)
        self.text.insert("end", "\n", surface_tag)

    def _render(self, *, context_start: int | None = None) -> None:
        if context_start is None:
            context_start = self._context_start
        else:
            self._context_start = max(0, context_start)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        visual = bool(self.visual_formatting.get())
        for index, message in enumerate(self._messages):
            if context_start and index == context_start:
                self.text.insert("end", "──────── New model context ────────\n\n", "context_boundary")
            role, label = self._role_details(message.role)
            if visual:
                self._insert_visual_message(role, label, message.content)
            else:
                self.text.insert("end", f"{label}\n", f"role_{role}")
                self.text.insert("end", f"{message.content}\n\n", "content")
        for role, message in self._notices:
            normalized, label = self._role_details(role)
            if visual:
                self._insert_visual_message(normalized, label, message)
            else:
                self.text.insert("end", f"{role}\n", f"role_{normalized}")
                self.text.insert("end", f"{message}\n\n", "content")
        self.text.see("end")
        self.text.configure(state="disabled")
