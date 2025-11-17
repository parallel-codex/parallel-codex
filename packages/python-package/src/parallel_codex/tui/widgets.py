"""UI widgets for the Parallel Codex Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Markdown, Static, TextArea


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

    def add_markdown_message(self, text: str) -> None:
        self.mount(MarkdownMessage(text))


class SessionRow(Horizontal):
    """Container that holds up to three visible session panes."""

    def __init__(self) -> None:
        super().__init__(id="session-row")


class PromptTextArea(TextArea):
    """TextArea that emits a Submitted message on Ctrl+Enter.

    This allows multi-line input while providing an explicit submit gesture.
    """

    @dataclass
    class Submitted(Message):
        """Posted when the user submits the prompt via Ctrl+Enter."""

        text_area: "PromptTextArea"
        value: str

        @property
        def control(self) -> "PromptTextArea":
            return self.text_area

    # Inherit all existing TextArea keybindings, plus Ctrl+Enter for submit.
    BINDINGS = [
        *TextArea.BINDINGS,
        Binding("ctrl+enter", "submit", "Submit", show=False),
    ]

    def action_submit(self) -> None:
        """Action invoked by the Ctrl+Enter binding."""

        self.post_message(self.Submitted(self, self.text))

