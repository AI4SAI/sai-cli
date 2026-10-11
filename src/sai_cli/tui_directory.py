"""A native Textual directory chooser for one explicit local quota read."""
from collections.abc import Iterable
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Static

from .local_quota import _path_text


class Directories(DirectoryTree):
    def process_label(self, label: str | Text) -> Text:
        return Text(_path_text(label.plain if isinstance(label, Text) else label))

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return (path for path in paths if path.is_dir())


class QuotaDirectory(ModalScreen[str | None]):
    BINDINGS = [("escape", "back", "Back"), ("backspace", "parent", "Parent")]
    CSS = """
    QuotaDirectory { align: center middle; }
    #directory-picker { width: 90%; height: 90%; background: $surface; border: solid $accent; }
    #directory-title, #directory-path { height: auto; padding: 0 1; }
    #directory-tree { height: 1fr; }
    #directory-actions { height: 3; }
    #directory-actions Button { min-width: 10; width: 1fr; }
    """

    def __init__(self, path: str, *, language: str):
        super().__init__()
        self.path = Path(path)
        self.chinese = language == "zh-CN"

    def compose(self) -> ComposeResult:
        with Vertical(id="directory-picker"):
            yield Static("选择配额目录" if self.chinese else "Choose quota directory", id="directory-title")
            yield Static(Text(_path_text(str(self.path))), id="directory-path")
            yield Directories(self.path, id="directory-tree")
            with Horizontal(id="directory-actions"):
                yield Button("上级目录" if self.chinese else "Parent", id="directory-parent")
                yield Button("查询配额" if self.chinese else "Read quota", id="directory-use", variant="primary")

    def on_mount(self) -> None:
        self.query_one(DirectoryTree).focus()

    @on(DirectoryTree.DirectorySelected)
    def select_directory(self, event: DirectoryTree.DirectorySelected) -> None:
        self.path = event.path
        self.query_one("#directory-path", Static).update(Text(_path_text(str(self.path))))

    @on(Button.Pressed, "#directory-parent")
    def action_parent(self) -> None:
        self.path = Path(self.query_one(DirectoryTree).path).parent
        self.query_one(DirectoryTree).path = self.path
        self.query_one("#directory-path", Static).update(Text(_path_text(str(self.path))))
        self.query_one(DirectoryTree).focus()

    @on(Button.Pressed, "#directory-use")
    def choose(self) -> None:
        self.dismiss(str(self.path))

    def action_back(self) -> None:
        self.dismiss(None)
