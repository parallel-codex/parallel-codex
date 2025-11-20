"""UI widgets for the Parallel Codex Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, Markdown, Static


class UserMessage(Static):
    """Simple widget representing a user-entered message."""

    pass


class MarkdownMessage(Markdown):
    """Markdown-rendered message from Codex."""

    pass


class SessionPane(VerticalScroll):
    """Scrollable pane that renders the history for a single session."""

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

    def watch_is_focused(self, value: bool) -> None:
        self.border_title = f"[bold]{self.label}[/bold]" if value else self.label

    def add_user_message(self, text: str) -> None:
        self.mount(UserMessage(text))

    def add_markdown_message(self, text: Any) -> None:
        self.mount(MarkdownMessage(_normalize_markdown_content(text)))


class SessionRow(Horizontal):
    """Container that holds up to three visible session panes."""

    def __init__(self) -> None:
        super().__init__(id="session-row")


class PromptTextArea(Input):
    """Single-line input that emits a Submitted message.

    This uses Textual's ``Input`` widget internally to avoid
    issues observed with ``TextArea`` rendering in some environments.
    """

    def __init__(self, *args, placeholder: str | None = None, **kwargs) -> None:
        super().__init__(*args, placeholder=placeholder or "", **kwargs)

    @dataclass
    class Submitted(Message):
        """Posted when the user submits the prompt via Ctrl+Enter."""

        text_area: "PromptTextArea"
        value: str

        @property
        def control(self) -> "PromptTextArea":
            return self.text_area

    # Inherit all existing Input keybindings, plus Ctrl+Enter for submit.
    BINDINGS = [
        *Input.BINDINGS,
        Binding("ctrl+enter", "submit", "Submit", show=False),
    ]

    def action_submit(self) -> None:
        """Action invoked by the Ctrl+Enter binding."""

        self.post_message(self.Submitted(self, self.value))


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
