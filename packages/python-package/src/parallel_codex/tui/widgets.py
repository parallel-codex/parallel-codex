"""UI widgets for the Parallel Codex Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, Markdown, Static


class UserMessage(Static):
    """Simple widget representing a user-entered message."""

    pass


class MarkdownMessage(Markdown):
    """Markdown-rendered message from Codex."""

    pass


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
        super().__init__(id=name)
        self.label = name
        self.border_title = name

    def compose(self) -> ComposeResult:
        """Compose the scrollable message area and per-session input."""

        yield VerticalScroll(id=f"{self.id}-messages")
        yield Input(placeholder="...", id=f"{self.id}-input", classes="session-input")

    def watch_is_focused(self, value: bool) -> None:
        self.border_title = f"[bold]{self.label}[/bold]" if value else self.label

    def _messages_container(self) -> VerticalScroll:
        return self.query_one(VerticalScroll)

    def _input_widget(self) -> Input | None:
        try:
            return self.query_one(Input)
        except NoMatches:
            return None

    def add_user_message(self, text: str) -> None:
        self._messages_container().mount(UserMessage(text))

    def add_markdown_message(self, text: Any) -> None:
        self._messages_container().mount(MarkdownMessage(_normalize_markdown_content(text)))

    def focus_input(self) -> None:
        """Move keyboard focus into this session's input, if present."""

        input_widget = self._input_widget()
        if input_widget is not None:
            input_widget.focus()


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
