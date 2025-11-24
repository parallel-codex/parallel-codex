"""UI widgets for the Parallel Codex Textual TUI."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static


class UserMessage(Static):
    """Simple widget representing a user-entered message."""

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(text, markup=False, **kwargs)


class MarkdownMessage(Markdown):
    """Markdown-rendered message from Codex."""

    def __init__(self, markdown: str, **kwargs: Any) -> None:
        super().__init__(markdown, **kwargs)


class EventMessage(Static):
    """System/status message emitted by the MCP server."""

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(text, markup=True, **kwargs)


class SessionPane(Vertical):
    """Pane that holds a scrollable history and its own input."""

    label = reactive("Session")
    is_focused = reactive(False)

    class SessionFocused(Message):
        """Emitted when the pane is clicked or otherwise focused."""

        def __init__(self, pane: "SessionPane") -> None:
            super().__init__()
            self.pane = pane

    def __init__(self, name: str) -> None:
        super().__init__(id=name, classes="session-pane")
        self.label = name
        self.border_title = name
        self._title_locked = False
        self._refresh_border_title()

    def compose(self) -> ComposeResult:
        """Compose the scrollable message area and per-session input."""

        yield VerticalScroll(id=f"{self.id}-messages", classes="session-messages")
        yield Input(placeholder="...", id=f"{self.id}-input", classes="session-input")

    def _refresh_border_title(self) -> None:
        self.border_title = f"[bold]{self.label}[/bold]" if self.is_focused else self.label

    def watch_is_focused(self, value: bool) -> None:
        self.set_class(value, "session-pane--focused")
        self._refresh_border_title()

    def _messages_container(self) -> VerticalScroll:
        assert self.id is not None
        return self.query_one(f"#{self.id}-messages", VerticalScroll)

    def _input_widget(self) -> Input | None:
        try:
            assert self.id is not None
            return self.query_one(f"#{self.id}-input", Input)
        except NoMatches:
            return None

    def _append_message(self, widget: Widget) -> None:
        messages = self._messages_container()
        messages.mount(widget)
        messages.scroll_end(animate=False)

    def add_user_message(self, text: str) -> None:
        self.ensure_thread_title(text)
        self._append_message(UserMessage(text, classes="message message-user"))

    def add_markdown_message(self, text: Any) -> None:
        self._append_message(
            MarkdownMessage(
                _normalize_markdown_content(text),
                classes="message message-assistant",
            )
        )

    def add_event_message(self, text: str) -> None:
        self._append_message(EventMessage(text, classes="message message-event"))

    def focus_input(self) -> None:
        """Move keyboard focus into this session's input, if present."""

        input_widget = self._input_widget()
        if input_widget is not None:
            input_widget.focus()

    def ensure_thread_title(self, prompt: str) -> None:
        """Assign a placeholder thread title based on the first user prompt."""

        if self._title_locked:
            return

        generated = _generate_thread_title(prompt)
        if generated:
            self.label = generated
            self._refresh_border_title()
            self._title_locked = True


class SessionRow(Horizontal):
    """Container that holds up to three visible session panes."""

    def __init__(self) -> None:
        super().__init__(id="session-row")


def _normalize_markdown_content(value: Any) -> str:
    """Convert Codex-style content payloads into markdown strings."""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "".join(parts)

    return str(value)


def _generate_thread_title(prompt: str) -> str:
    """Derive a lightweight placeholder title from the first user prompt."""

    collapsed = " ".join(prompt.strip().split())
    if not collapsed:
        return "New session"

    max_len = 48
    if len(collapsed) > max_len:
        collapsed = collapsed[:max_len].rstrip() + "..."
    return collapsed
