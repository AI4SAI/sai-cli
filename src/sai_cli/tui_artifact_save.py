"""One destination prompt and one cooperatively cancelled artifact transfer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from threading import Event

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from .errors import AuthenticationError, ForbiddenError, SaiCliError
from .managed_runs import terminal_log
from .tui_messages import Messages


SaveResult = dict[str, object] | SaiCliError | None


class ArtifactSaveScreen(ModalScreen[SaveResult]):
    BINDINGS = [Binding("escape", "cancel", show=False, priority=True)]
    DEFAULT_CSS = """
    ArtifactSaveScreen { align: center middle; }
    #artifact-save-dialog { width: 70; max-width: 100%; height: auto; max-height: 100%;
        padding: 0 1; border: solid $primary; background: $surface; }
    #artifact-save-title { height: 1; text-style: bold; }
    #artifact-save-hint, #artifact-save-status { height: auto; }
    #artifact-save-actions { height: 3; }
    #artifact-save-actions Button { width: 1fr; min-width: 0; }
    """

    def __init__(self, name: str, language: str,
                 save: Callable[[str, Event], Awaitable[dict[str, object]]]):
        super().__init__()
        self.t = Messages(language)
        self.filename = name
        self.save = save
        self.cancelled = Event()
        self.started = False
        self.busy = False
        self.quitting = False
        self._transfer: asyncio.Task[dict[str, object]] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="artifact-save-dialog"):
            yield Static(Text(self.t("save_file") + " · " + terminal_log(self.filename), overflow="ellipsis", no_wrap=True), id="artifact-save-title")
            yield Static(self.t("save_host"), id="artifact-save-hint", markup=False)
            yield Input(value=self.filename, placeholder=self.t("save_destination"), id="artifact-save-path")
            yield Static("", id="artifact-save-status", markup=False)
            with Horizontal(id="artifact-save-actions"):
                yield Button(self.t("save_file"), id="artifact-save-start", variant="primary")
                yield Button(self.t("save_cancel"), id="artifact-save-cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.start_save()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        if not self.busy:
            self.query_one("#artifact-save-status", Static).update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "artifact-save-start":
            self.start_save()
        elif event.button.id == "artifact-save-cancel":
            self.action_cancel()

    def start_save(self) -> None:
        if self.busy:
            return
        output = self.query_one(Input).value
        if not output:
            self.query_one("#artifact-save-status", Static).update(self.t("save_destination"))
            self.query_one(Input).focus()
            return
        self.cancelled.clear()
        self.started = self.busy = True
        self.query_one(Input).disabled = True
        self.query_one("#artifact-save-start", Button).disabled = True
        self.query_one("#artifact-save-status", Static).update(self.t("save_busy"))
        self.query_one("#artifact-save-cancel", Button).focus()
        self.run_worker(self._perform(output), group="artifact-save")

    async def _perform(self, output: str) -> None:
        self._transfer = asyncio.create_task(self.save(output, self.cancelled))
        result: SaveResult = None
        failure = ""
        try:
            result = await asyncio.shield(self._transfer)
        except asyncio.CancelledError:
            self.cancelled.set()
            # Textual worker cancellation must not leave its filesystem worker running.
            try:
                await self._transfer
            except Exception:
                pass
            raise
        except (AuthenticationError, ForbiddenError) as error:
            result = error
        except SaiCliError as error:
            if error.code != "download_cancelled":
                failure = "save_exists" if error.code == "output_exists" else "save_failed"
        except Exception:
            failure = "save_failed"
        finally:
            self.busy = False
        if not self.is_mounted:
            return
        if self.quitting:
            self.app.exit()
        elif result is not None or self.cancelled.is_set() or not failure:
            self.dismiss(result)
        else:
            self.query_one("#artifact-save-status", Static).update(self.t(failure))
            self.query_one(Input).disabled = False
            self.query_one("#artifact-save-start", Button).disabled = False
            self.query_one(Input).focus()

    def action_cancel(self, *, quit_app: bool = False) -> None:
        self.quitting = self.quitting or quit_app
        self.cancelled.set()
        if self.busy:
            self.query_one("#artifact-save-status", Static).update(self.t("save_stopping"))
            self.query_one("#artifact-save-cancel", Button).disabled = True
        elif self.quitting:
            self.app.exit()
        else:
            self.dismiss(None)

    async def on_unmount(self) -> None:
        self.cancelled.set()
        if self._transfer is not None:
            try:
                await asyncio.shield(self._transfer)
            except Exception:
                pass
