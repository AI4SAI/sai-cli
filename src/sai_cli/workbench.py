"""One terminal journey from the researcher's work to authorized results."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from threading import Event
import time
from urllib.parse import urlencode, urljoin
from webbrowser import Error as BrowserError

from rich.text import Text
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import ActiveBinding, Binding
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets.option_list import Option

from .artifact_content import ManagedRunArtifactContent
from .catalog import ResourceCatalog
from .client import JobQuery, PortalClient
from .contracts import JobCostResult, JobResult
from .errors import AuthenticationError, ContractError, ForbiddenError, NotFoundError, SaiCliError
from .managed_runs import (
    ManagedRunArtifacts, ManagedRunDetail, ManagedRunList, ManagedRunLogs,
    ManagedRunWorkspaces, MyManagedRunList, terminal_log,
)
from .native_quota import NativeQuotaResult
from .overview import AccountOverview
from .overview_view import overview_panel
from .run_cost import ManagedRunCost, cost_lines
from .run_placement import ManagedRunPlacement
from .run_stats import ManagedRunStats, stats_lines
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary, StorageWorkspaces
from .tui_artifact_save import ArtifactSaveScreen, SaveResult
from .tui_views import allocation_panel, job_cost_panel, placement_panel, resource_panel, storage_panel, task_detail_panel, task_file_panel
from .workbench_auth import DeviceLoginScreen
from .workbench_copy import WorkbenchText, natural_state, short_time, work_row


@dataclass(frozen=True)
class Work:
    kind: str
    reference: str
    title: str
    workspace: str | None = None
    label: str = ""
    state: str = ""


@dataclass(frozen=True)
class ReadRequest:
    revision: int
    mode: str
    query: JobQuery
    work: Work | None
    cursor: str | None
    artifact: tuple[ManagedRunArtifacts, str] | None
    storage: tuple[str, str] | None


@dataclass(frozen=True)
class Position:
    mode: str
    cursor: str | None
    scroll: float = 0


class ActionMenu(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", show=False)]
    DEFAULT_CSS = """
    ActionMenu { align: center middle; }
    #work-menu { width: 58; max-width: 95%; height: auto; max-height: 90%; background: $surface; padding: 1; }
    #work-menu-title { height: 1; text-style: bold; }
    #work-menu-options { height: auto; max-height: 20; border: none; }
    """

    def __init__(self, title: str, choices: dict[str, str]):
        super().__init__()
        self.title_text, self.choices = title, choices

    def compose(self) -> ComposeResult:
        with Vertical(id="work-menu"):
            yield Static(self.title_text, id="work-menu-title", markup=False)
            yield OptionList(*(Option(label, id=key) for key, label in self.choices.items()), id="work-menu-options")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorkScreen(Screen):
    @property
    def active_bindings(self) -> dict[str, ActiveBinding]:
        bindings = super().active_bindings
        for key, active in tuple(bindings.items()):
            if active.node is self.app and active.binding.action in {"refresh", "quit"}:
                label = self.app.t(active.binding.action)
                bindings[key] = ActiveBinding(active.node, replace(active.binding, description=label), active.enabled, label)
        return bindings


class Workbench(App, inherit_bindings=False):
    """Client calls serialize, while every navigation invalidates old responses."""

    BINDINGS = [Binding("escape", "back", show=False), Binding("f5", "refresh", "Refresh"),
                Binding("ctrl+p", "command_palette", show=False, priority=True),
                Binding("ctrl+q", "quit", "Quit", priority=True)]
    CSS = """
    Screen { background: $background; }
    #work-header { height: auto; max-height: 3; padding: 1 2 0 2; text-style: bold; }
    #work-context { height: auto; max-height: 2; padding: 0 2; color: $text-muted; }
    #work-status { height: auto; max-height: 3; padding: 0 2; }
    #work-body { height: 1fr; padding: 1 1 0 1; }
    #work-list, #work-files, #work-choices { height: 1fr; border: none; padding: 0 1; }
    #work-reading { height: 1fr; padding: 0 1; }
    #work-evidence { height: auto; }
    #work-actions { height: 3; padding: 0 1; }
    #work-actions Button { width: 1fr; min-width: 0; }
    #work-link { height: auto; max-height: 2; padding: 0 2; }
    .short #work-header { padding-top: 0; }
    .short #work-body { padding-top: 0; }
    .short #work-actions { height: 1; }
    .short #work-actions Button { height: 1; border: none; padding: 0; }
    OptionList > .option-list--option-highlighted { background: $primary-background; text-style: bold; }
    """

    def __init__(self, client: PortalClient, query: JobQuery, *, language: str = "zh-CN",
                 refresh_seconds: int = 10, storage_workspace_key: str | None = None,
                 overview_account: str | None = None):
        super().__init__()
        self.client, self.job_query = client, query.validated()
        self.language, self.t = language, WorkbenchText(language)
        self.refresh_seconds = refresh_seconds
        self.overview_account, self.storage_key = overview_account, storage_workspace_key
        self.register_theme(Theme(name="sai-work", primary="#64d8d0", secondary="#8fa4b3", accent="#64d8d0",
            background="#151c24", surface="#202a34", panel="#26323f", foreground="#e4ebf1",
            success="#79b98b", warning="#d8b471", error="#de8b8d"))
        self.theme = "sai-work"
        self.mode = "home"
        self.selected: Work | None = None
        self.detail: ManagedRunDetail | JobResult | SiteJobResult | SiteJobAllocationResult | None = None
        self.result: object | None = None
        self.artifact: tuple[ManagedRunArtifacts, str] | None = None
        self.storage: tuple[str, str] | None = None
        self.cursor: str | None = None
        self.home_cursor: str | None = None
        self.home_highlight: str | None = None
        self.home_scroll = 0.0
        self.home_items: dict[str, Work] = {}
        self.compared: list[str] = []
        self.file_highlight: str | None = None
        self.file_cursor: str | None = None
        self.positions: dict[str, Position] = {}
        self.return_to: Position | None = None
        self.context_return: Position | None = None
        self.page_history: dict[str, list[str | None]] = {}
        self._revision = 0
        self._pending: ReadRequest | None = None
        self._reading = False
        self._client_lock = asyncio.Lock()
        self._save_screen: ArtifactSaveScreen | None = None
        self._login_screen: DeviceLoginScreen | None = None
        self._placement_timer: Timer | None = None
        self._placement_expired = False
        self._web_url: str | None = None
        self._error = ""
        self._restore_scroll = 0.0
        self._focus_on_load = True
        self._work_ready = False
        self.paused = False
        self.auth_expired = False

    def compose(self) -> ComposeResult:
        yield Static("", id="work-header", markup=False)
        yield Static("", id="work-context", markup=False)
        yield Static("", id="work-status", markup=False)
        with Vertical(id="work-body"):
            yield OptionList(id="work-list")
            yield OptionList(id="work-files")
            yield OptionList(id="work-choices")
            with VerticalScroll(id="work-reading", can_focus=True):
                yield Static("", id="work-evidence", markup=False)
        yield Static("", id="work-link", markup=False)
        with Horizontal(id="work-actions"):
            yield Button(self.t("back"), id="work-back")
            yield Button(self.t("open"), id="work-primary", variant="primary")
            yield Button(self.t("more"), id="work-more")
        yield Footer()

    def on_mount(self) -> None:
        self._work_ready = True
        self.title = self.t("app")
        self.set_interval(max(1, self.refresh_seconds), self._tick)
        self._read()

    def get_default_screen(self) -> Screen:
        return WorkScreen(id="_default")

    def on_resize(self) -> None:
        if self._work_ready:
            self.call_after_refresh(self._render)

    def _tick(self) -> None:
        if self.mode == "home" and isinstance(self.result, dict) and any(isinstance(value, SaiCliError) for value in self.result.values()):
            return
        if (not self.paused and not self._reading and not self._pending and not self._error
                and self._save_screen is None and self._login_screen is None and self.mode in {"home", "run", "native"}):
            self.action_refresh()

    def _remember(self) -> None:
        if not self._work_ready:
            return
        if self.mode == "home":
            listing = self.query_one("#work-list", OptionList)
            self.home_highlight = self._highlight(listing)
            self.home_scroll = listing.scroll_y
        elif self.mode in {"files", "content", "stdout", "stderr"}:
            self.positions[self.mode] = Position(self.mode, self.cursor, self.query_one("#work-reading").scroll_y)
            if self.mode == "files":
                self.file_highlight = self._highlight(self.query_one("#work-files", OptionList))

    @staticmethod
    def _highlight(options: OptionList) -> str | None:
        return options.get_option_at_index(options.highlighted).id if options.highlighted is not None else None

    def _navigate(self, mode: str, *, cursor: str | None = None, restore: bool = False) -> None:
        self._remember()
        position = self.positions.get(mode) if restore else None
        self.mode, self.cursor = mode, position.cursor if position else cursor
        self._restore_scroll = position.scroll if position else 0
        self._focus_on_load = True
        self._read()

    def _read(self) -> None:
        self._stop_placement_timer()
        self._placement_expired = False
        self._revision += 1
        self.result, self._web_url, self._error = None, None, ""
        self.query_one("#work-evidence", Static).update("")
        for name in ("work-list", "work-files", "work-choices"):
            self.query_one("#" + name, OptionList).clear_options()
        self.home_items = {}
        self.compared.clear()
        self._pending = ReadRequest(self._revision, self.mode, self.job_query, self.selected, self.cursor, self.artifact, self.storage)
        self._render()
        if not self._reading:
            self._reading = True
            self.run_worker(self._read_loop(), group="work-reads")

    async def _read_loop(self) -> None:
        try:
            while self._pending is not None:
                request, self._pending = self._pending, None
                try:
                    async with self._client_lock:
                        result = await asyncio.to_thread(self._fetch, request)
                except SaiCliError as error:
                    if request.revision == self._revision:
                        self._failed(error)
                except Exception:
                    if request.revision == self._revision:
                        self._failed(ContractError())
                else:
                    if request.revision == self._revision:
                        self.auth_expired = False
                        self._accept(result)
        finally:
            self._reading = False
            if self.is_running:
                self._render()

    def _fetch(self, request: ReadRequest) -> object:
        mode, work = request.mode, request.work
        if mode == "home":
            results: dict[str, object] = {}
            for source in ("recent", "live"):
                try:
                    if source == "live":
                        results[source] = self.client.list_jobs(request.query)
                    elif request.query.workspace_key is None and request.query.scope != "self":
                        results[source] = None
                    elif request.query.workspace_key is None:
                        results[source] = self.client.list_my_managed_runs(site_id=request.query.site_id, limit=50, cursor=request.cursor)
                    else:
                        names = self.client.list_run_workspaces(site_id=request.query.site_id, workspace_key=request.query.workspace_key)
                        choice = next((row for row in names.values["items"] if row["workspace_key"] == request.query.workspace_key), None)
                        if choice is None:
                            raise ForbiddenError("The selected account is not readable")
                        results["scope"] = choice
                        results[source] = self.client.list_managed_runs(site_id=request.query.site_id,
                            workspace_key=request.query.workspace_key, limit=50, cursor=request.cursor)
                except AuthenticationError:
                    raise
                except SaiCliError as error:
                    results[source] = error
            return results
        if mode == "catalog":
            return self.client.resource_catalog(request.query.site_id)
        if mode == "overview":
            return self.client.account_overview(request.query.site_id, account=self.overview_account)
        if mode == "storage_choices":
            return self.client.list_storage_workspaces(site_id=request.query.site_id, cursor=request.cursor,
                workspace_key=self.storage_key)
        if mode == "workspaces":
            return self.client.list_run_workspaces(site_id=request.query.site_id, cursor=request.cursor)
        if mode in {"storage", "storage_native"}:
            if request.storage is None:
                raise ContractError()
            reader = self.client.storage_native_quota if mode == "storage_native" else self.client.storage_quota_summary
            return reader(site_id=request.query.site_id, workspace_key=request.storage[0])
        if work is None:
            raise ContractError()
        if work.kind == "native":
            query = replace(request.query, partition=None, states=())
            reader = {"native": self.client.show_job, "evidence": self.client.show_job,
                      "allocation": self.client.job_allocation, "cost": self.client.job_cost,
                      "placement": self.client.job_placement}.get(mode)
            if reader is None:
                raise ContractError()
            return reader(work.reference, query)
        scope = dict(workspace_key=work.workspace, site_id=request.query.site_id)
        if mode in {"run", "evidence"}:
            return self.client.managed_run(work.reference, **scope)
        if mode in {"stdout", "stderr"}:
            return self.client.managed_run_logs(work.reference, **scope, stream=mode, cursor=request.cursor, max_bytes=65536)
        if mode == "files":
            return self.client.managed_run_artifacts(work.reference, **scope, cursor=request.cursor, limit=100)
        if mode == "content" and request.artifact is not None:
            old_page, reference = request.artifact
            page = self.client.managed_run_artifacts(work.reference, **scope, cursor=old_page.request_cursor, limit=100)
            old = next(item for item in old_page.values["items"] if item["artifact_ref"] == reference)
            current = next((item for item in page.values["items"] if item["artifact_ref"] == reference), None)
            if current is None or current["relative_path"] != old["relative_path"]:
                raise NotFoundError("The selected output changed")
            content = self.client.managed_run_artifact_content(work.reference, **scope,
                artifact_ref=reference, artifact_cursor=page.request_cursor, cursor=request.cursor)
            if content.values["relative_path"] != current["relative_path"]:
                raise ContractError()
            return page, content
        reader = {"cost": self.client.managed_run_cost, "stats": self.client.managed_run_stats,
                  "placement": self.client.managed_run_placement}.get(mode)
        if reader is None:
            raise ContractError()
        return reader(work.reference, **scope)

    def _accept(self, result: object) -> None:
        self._stop_placement_timer()
        self._placement_expired = False
        self.result = result
        if self.mode == "home":
            self._home_rows(result)
        elif isinstance(result, ManagedRunDetail):
            self.detail = result
            if self.mode == "run":
                status = result.values["run"]["status"]
                if status == "completed":
                    self._navigate("files", restore=True)
                    return
                if status in {"failed", "needs_attention"}:
                    self._navigate("stderr", restore=True)
                    return
        elif self.mode == "content" and isinstance(result, tuple):
            page, content = result
            self.result = content
            if content.values["status"] in {"missing", "changed"}:
                self.artifact = None
                self.positions.pop("content", None)
            else:
                self.artifact = (page, content.values["artifact_ref"])
        elif isinstance(result, (JobResult, SiteJobResult, SiteJobAllocationResult)):
            self.detail = result
        elif isinstance(result, ManagedRunArtifacts):
            self.file_cursor = result.request_cursor
            files = self.query_one("#work-files", OptionList)
            files.add_options(Option(Text(terminal_log(row["relative_path"]), overflow="fold"), id=row["artifact_ref"])
                              for row in result.values["items"])
            self._restore_highlight(files, self.file_highlight)
        elif isinstance(result, (ResourceCatalog, StorageWorkspaces, ManagedRunWorkspaces)):
            choices = self.query_one("#work-choices", OptionList)
            if isinstance(result, ResourceCatalog):
                choices.add_options(Option(Text(row["title"] + ("\n" + row["summary"] if row["summary"] else "")), id=row["name"])
                                    for row in result.values["compute"])
            else:
                choices.add_options(Option(Text(row["label"] + (" · " + row["organization_label"] if row["organization_label"] else "")), id=row["workspace_key"])
                                    for row in result.values["items"])
            self._restore_highlight(choices, None)
        listing_id = ("work-list" if self.mode == "home" else "work-files" if self.mode == "files"
                      else "work-choices" if self.mode in {"storage_choices", "workspaces"} else None)
        if listing_id:
            listing = self.query_one("#" + listing_id, OptionList)
            if self.page_history.get(self.mode):
                listing.add_option(Option(self.t("previous"), id="nav:previous"))
            if self._next_cursor() is not None:
                listing.add_option(Option(self.t("next"), id="nav:next"))
        self._arm_placement_expiry()
        self._render()
        self.call_after_refresh(self._focus_content, self._revision)

    def _home_rows(self, result: dict[str, object]) -> None:
        listing = self.query_one("#work-list", OptionList)
        for source in ("live", "recent"):
            data = result[source]
            heading = self.t("scoped_live" if source == "live" and self.job_query.scope != "self" else source)
            listing.add_option(Option(Text(heading, style="bold #64d8d0"), disabled=True, id="heading-" + source))
            if isinstance(data, SaiCliError):
                listing.add_option(Option(self.t(source + "_failed"), disabled=True))
                continue
            if data is None:
                listing.add_option(Option(self.t("legacy_history"), disabled=True))
                continue
            if source == "live":
                rows = data.items
                for item in rows:
                    key = "native:" + item.canonical_id
                    self.home_items[key] = Work("native", item.canonical_id, item.values["name"] or self.t("untitled"), state=item.values["state"])
                    listing.add_option(Option(work_row(item.values["name"], item.values["state"], "", self.t), id=key))
                if isinstance(data, SiteJobResult) and data.has_more:
                    listing.add_option(Option(self.t("more_live"), disabled=True))
            else:
                rows = data.values["items"]
                for row in rows:
                    scope = result.get("scope", {})
                    label = row.get("workspace_label", scope.get("label", ""))
                    organization = row.get("organization_label", scope.get("organization_label"))
                    label = label + (" · " + organization if organization else "")
                    workspace = row.get("workspace_key", self.job_query.workspace_key)
                    key = "run:" + row["run_ref"]
                    self.home_items[key] = Work("run", row["run_ref"], row["title"] or self.t("untitled"), workspace, label, row["status"])
                    listing.add_option(Option(work_row(row["title"], row["status"], label, self.t), id=key))
            if not rows:
                listing.add_option(Option(self.t("no_" + source), disabled=True))
        self._restore_highlight(listing, self.home_highlight)

    @staticmethod
    def _restore_highlight(options: OptionList, identifier: str | None) -> None:
        if identifier is not None and any(option.id == identifier for option in options.options):
            options.highlighted = options.get_option_index(identifier)
        elif any(not option.disabled for option in options.options):
            options.highlighted = next(index for index, option in enumerate(options.options) if not option.disabled)

    def _focus_content(self, revision: int) -> None:
        if revision != self._revision or self._save_screen is not None or self.screen is not self.default_screen:
            return
        target = self.query_one("#" + ("work-list" if self.mode == "home" else "work-files" if self.mode == "files"
            else "work-choices" if self.mode in {"catalog", "storage_choices", "workspaces"} else "work-reading"))
        if target.display:
            if self._focus_on_load:
                target.focus()
            target.scroll_to(y=self.home_scroll if self.mode == "home" else self._restore_scroll, animate=False, immediate=True)

    def _failed(self, error: SaiCliError) -> None:
        self._stop_placement_timer()
        self._placement_expired = False
        self.result, self._web_url = None, None
        independent = (isinstance(error, ForbiddenError) and
            ((self.mode in {"files", "content", "stdout", "stderr"} and error.code == "run_file_read_denied")
             or (self.mode == "cost" and error.code in {"run_cost_read_denied", "job_cost_read_denied", "identity_scope_denied"})
             or self.mode in {"storage_choices", "storage", "storage_native", "overview", "catalog", "workspaces"}
             or self.mode == "placement" and error.code == "run_placement_not_enabled"))
        if isinstance(error, AuthenticationError) or isinstance(error, ForbiddenError) and not independent:
            self.auth_expired = isinstance(error, AuthenticationError)
            self.detail, self.selected, self.artifact, self.return_to, self.storage = None, None, None, None, None
            self.context_return = None
            self.home_items.clear()
            self.positions.clear()
            self.page_history.clear()
            self.home_cursor = self.cursor = self.home_highlight = self.file_cursor = self.file_highlight = None
            self.mode = "home"
            self.paused = True
            self._error = self.t("expired" if self.auth_expired else "denied")
        else:
            self._error = self.t("files_denied" if independent and self.mode in {"files", "content", "stdout", "stderr"}
                else "cost_denied" if independent and self.mode == "cost" else "denied" if independent
                else "missing" if isinstance(error, NotFoundError) else "unavailable")
            if self.mode in {"files", "content", "stdout", "stderr"}:
                self.artifact = None
                self.positions.clear()
                self.file_highlight = None
        for name in ("work-list", "work-files", "work-choices"):
            self.query_one("#" + name, OptionList).clear_options()
        self.query_one("#work-evidence", Static).update("")
        self._render()

    def _render(self) -> None:
        if not self._work_ready:
            return
        busy = self.result is None and not self._error
        self.default_screen.set_class(self.size.height < 28, "short")
        title = self.selected.title if self.selected and self.mode not in {"home", "catalog", "resource", "storage_choices", "storage", "storage_native", "overview", "workspaces"} else self.t(
            "home" if self.mode == "home" and self.job_query.scope == "self" else "scoped_home" if self.mode == "home" else "catalog" if self.mode == "resource" else self.mode)
        self.query_one("#work-header", Static).update(Text(title, overflow="fold"))
        label = self.selected.label if self.selected and self.mode != "home" else ""
        if self.mode == "home" and isinstance(self.result, dict):
            label = self.result.get("scope", {}).get("label", "")
            if not label and self.job_query.scope != "self":
                label = self.job_query.account_name or ""
        context = self.job_query.site_id + (" · " + label if label else "")
        if isinstance(self.detail, ManagedRunDetail) and self.selected and self.mode not in {"home", "catalog", "resource", "overview", "storage_choices", "storage", "storage_native", "workspaces"}:
            context += " · " + natural_state(self.detail.values["run"]["status"], self.t)
        self.query_one("#work-context", Static).update(Text(context, overflow="fold"))
        self.query_one("#work-status", Static).update(self._error or (self.t("loading") if busy else
            self.t("placement_expired") if self._placement_expired else
            self.t("paused") if self.paused and self.mode in {"home", "run", "native"} else ""))
        show_home = self.mode == "home" and any(not row.disabled for row in self.query_one("#work-list", OptionList).options) and not self._error
        show_files = self.mode == "files" and isinstance(self.result, ManagedRunArtifacts) and bool(self.query_one("#work-files", OptionList).option_count)
        show_choices = self.mode in {"catalog", "storage_choices", "workspaces"} and isinstance(self.result, (ResourceCatalog, StorageWorkspaces, ManagedRunWorkspaces)) and bool(
            self.result.values["compute"] if isinstance(self.result, ResourceCatalog) else self.result.values["items"])
        self.query_one("#work-list").display = show_home
        self.query_one("#work-files").display = show_files
        self.query_one("#work-choices").display = show_choices
        self.query_one("#work-reading").display = not (show_home or show_files or show_choices)
        if not busy and not self._error:
            self.query_one("#work-evidence", Static).update(self._evidence())
        primary, enabled = self._primary()
        button = self.query_one("#work-primary", Button)
        button.label, button.disabled = primary, not enabled or self._reading or self._pending is not None
        self.query_one("#work-back", Button).display = self.mode != "home"
        self.query_one("#work-more", Button).disabled = self._save_screen is not None
        link = self.query_one("#work-link", Static)
        link.display = self._web_url is not None
        link.update(Text(self.t("web_ready"), style=f"link {self._web_url}") if self._web_url else "")
        self.refresh_bindings()

    def _evidence(self) -> object:
        result = self.result
        if self.mode == "home":
            if isinstance(result, dict) and any(isinstance(result.get(key), SaiCliError) for key in ("recent", "live")):
                return Text("\n".join(self.t(key + "_failed") for key in ("recent", "live") if isinstance(result.get(key), SaiCliError)))
            if self.job_query.scope != "self" and self.job_query.workspace_key is None:
                return Text(self.t("legacy_history"))
            return Text(self.t("empty"))
        if isinstance(result, tuple) and self.mode == "resource":
            catalog, row = result
            compared = [item for name in self.compared for item in catalog.values["compute"] if item["name"] == name]
            return resource_panel(row, compared, self.language, self.size.width)
        if isinstance(result, ManagedRunDetail):
            if self.mode == "evidence":
                return task_detail_panel(result, self.language)
            return Text(self.t("run_hint") + "\n\n" + self.t("updated", time=short_time(result.values["run"]["last_observed_at"])) )
        if isinstance(result, (ManagedRunLogs, ManagedRunArtifactContent)):
            return task_file_panel(result, self.language)
        if isinstance(result, ManagedRunArtifacts):
            return Text(self.t("files_empty"))
        if isinstance(result, ManagedRunCost):
            return Text("\n".join(cost_lines(result, self.language)))
        if isinstance(result, ManagedRunStats):
            return Text("\n".join(stats_lines(result, self.language)))
        if isinstance(result, ManagedRunPlacement):
            return placement_panel(result.placement, self.language)
        if isinstance(result, SiteJobPlacementResult):
            return placement_panel(result, self.language)
        if isinstance(result, SiteJobAllocationResult):
            return allocation_panel(result, self.language)
        if isinstance(result, JobCostResult):
            return job_cost_panel(result, self.language)
        if isinstance(result, (JobResult, SiteJobResult)):
            job = result.items[0]
            content = natural_state(job.values["state"], self.t) + "\n\n" + self.t("native_hint")
            if self.mode == "evidence":
                content += "\n\n" + "\n".join(f"{self.t(label)}: {value}" for label, value in
                    (("job", job.canonical_id), ("partition", job.values["partition"]), ("account", job.values["slurm_account"])))
            return Text(content)
        if isinstance(result, AccountOverview):
            return overview_panel(result, language=self.language, base_url=self.client.transport.base_url)
        if isinstance(result, (StorageQuotaSummary, NativeQuotaResult)):
            return storage_panel(result, self.language, workspace_label=self.storage[1] if self.storage else None)
        if isinstance(result, ResourceCatalog):
            return Text(self.t("catalog_empty"))
        if isinstance(result, StorageWorkspaces):
            return Text(self.t("storage_empty"))
        if isinstance(result, ManagedRunWorkspaces):
            return Text(self.t("workspaces_empty"))
        return Text("")

    def _primary(self) -> tuple[str, bool]:
        if self.auth_expired:
            return self.t("login"), self._login_screen is None
        if self._error:
            return self.t("retry"), True
        if self.mode in {"home", "files", "storage_choices", "workspaces"}:
            widget = self.query_one("#" + ("work-list" if self.mode == "home" else "work-files" if self.mode == "files" else "work-choices"), OptionList)
            selected = self._highlight(widget)
            if selected in {"nav:next", "nav:previous"}:
                return self.t(selected.split(":")[1]), True
        if self.mode == "home":
            if not self.home_items and isinstance(self.result, dict) and any(isinstance(value, SaiCliError) for value in self.result.values()):
                return self.t("retry"), True
            if not self.home_items and self.job_query.scope != "self" and self.job_query.workspace_key is None:
                return self.t("workspaces"), self.result is not None
            if self.home_items:
                work = self.home_items.get(self._highlight(self.query_one("#work-list", OptionList)))
                action = "results" if work and work.kind == "run" and work.state == "completed" else "logs" if (
                    work and work.kind == "run" and work.state in {"failed", "needs_attention"}) else "view_status"
                return self.t(action), work is not None
            return self.t("start"), self.result is not None
        if self.mode in {"files", "storage_choices", "catalog", "workspaces"}:
            widget = self.query_one("#work-files" if self.mode == "files" else "#work-choices", OptionList)
            if self.mode == "files" and isinstance(self.result, ManagedRunArtifacts) and not self.result.values["items"]:
                return self.t("logs"), True
            return self.t("open"), widget.highlighted is not None
        if self.mode == "content":
            return self.t("save_file"), self._can_save()
        if self.mode == "resource":
            return self.t("prepare"), isinstance(self.result, tuple)
        if self.mode == "overview":
            return self.t("messages"), isinstance(self.result, AccountOverview)
        if self.mode == "native":
            return self.t("allocation"), self.detail is not None
        if self.selected and self.selected.kind == "run" and self.mode in {"run", "stdout", "stderr", "cost", "stats", "placement", "evidence"}:
            return self.t("results"), self.detail is not None
        return self.t("back"), self.mode != "home"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if self._reading or self._pending or self._save_screen is not None:
            return
        key = event.option.id
        if key in {"nav:next", "nav:previous"}:
            self._page(previous=key == "nav:previous")
        elif event.option_list.id == "work-list" and self.mode == "home" and key in self.home_items:
            self._remember()
            self.selected = self.home_items[key]
            self.detail, self.artifact, self.return_to, self.context_return = None, None, None, None
            self.positions.clear()
            self.page_history = {"home": self.page_history.get("home", [])}
            self.file_cursor = self.file_highlight = None
            self._navigate("run" if self.selected.kind == "run" else "native")
        elif event.option_list.id == "work-files" and self.mode == "files" and isinstance(self.result, ManagedRunArtifacts):
            self.result.require_selection(self.detail, key)
            self.file_highlight = key
            self.artifact = self.result, key
            self.positions.pop("content", None)
            self._navigate("content")
        elif event.option_list.id == "work-choices":
            self._choose(key)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if self._work_ready and event.option_list.id in {"work-list", "work-files", "work-choices"}:
            self._render()

    def _choose(self, key: str | None) -> None:
        if isinstance(self.result, ResourceCatalog):
            row = next((row for row in self.result.values["compute"] if row["name"] == key), None)
            if row:
                self._revision += 1
                self.result = self.result, row
                self.mode = "resource"
                self._render()
                self._focus_content(self._revision)
        elif isinstance(self.result, StorageWorkspaces):
            row = next((row for row in self.result.values["items"] if row["workspace_key"] == key), None)
            if row:
                self.storage = key, row["label"]
                self._navigate("storage")
        elif isinstance(self.result, ManagedRunWorkspaces):
            row = next((row for row in self.result.values["items"] if row["workspace_key"] == key), None)
            if row:
                self._change_account(row["workspace_key"])

    def _change_account(self, workspace: str | None) -> None:
        self.job_query = replace(self.job_query, workspace_key=workspace, account_name=None, account_id=None,
            scope=workspace.split(":", 1)[0] + "-account" if workspace else "self").validated()
        self.selected = self.detail = self.artifact = self.return_to = self.context_return = None
        self.positions.clear()
        self.page_history.clear()
        self.home_cursor = self.home_highlight = self.file_cursor = self.file_highlight = None
        self._navigate("home")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "work-back":
            self.action_back()
        elif event.button.id == "work-primary":
            self.action_primary()
        elif event.button.id == "work-more":
            self.action_more()

    def action_primary(self) -> None:
        if self._reading or self._pending or self._login_screen is not None:
            return
        if self.auth_expired:
            self.action_login()
        elif self._error:
            self.action_refresh()
        elif self.mode == "home" and not self.home_items:
            if isinstance(self.result, dict) and any(isinstance(value, SaiCliError) for value in self.result.values()):
                self.action_refresh()
            elif self.job_query.scope != "self" and self.job_query.workspace_key is None:
                self._tool("workspaces")
            else:
                self.action_start()
        elif self.mode in {"home", "files", "catalog", "storage_choices", "workspaces"}:
            if self.mode == "files" and isinstance(self.result, ManagedRunArtifacts) and not self.result.values["items"]:
                self._navigate("stdout", restore=True)
                return
            widget = self.query_one("#" + ("work-list" if self.mode == "home" else "work-files" if self.mode == "files" else "work-choices"), OptionList)
            widget.action_select()
        elif self.mode == "content":
            self.action_save()
        elif self.mode == "resource":
            catalog, row = self.result
            self._show_link(catalog.preparation_url(self.client.transport.base_url, row["name"]))
        elif self.mode == "overview" and isinstance(self.result, AccountOverview):
            self._show_link(self.result.messages_url(self.client.transport.base_url))
        elif self.mode == "native":
            self._command("allocation")
        elif self.selected and self.selected.kind == "run" and self.mode in {"run", "stdout", "stderr", "cost", "stats", "placement", "evidence"}:
            self._navigate("files", cursor=self.file_cursor)
        else:
            self.action_back()

    def action_back(self) -> None:
        if not self._work_ready or self._save_screen is not None or self._login_screen is not None:
            return
        if self.mode == "content":
            self._navigate("files", cursor=self.file_cursor)
        elif self.mode == "resource" and isinstance(self.result, tuple):
            catalog, row = self.result
            self._revision += 1
            self.mode, self._web_url = "catalog", None
            self.query_one("#work-choices", OptionList).clear_options()
            self._accept(catalog)
            self._restore_highlight(self.query_one("#work-choices", OptionList), row["name"])
        elif self.mode in {"storage", "storage_native"}:
            self._navigate("storage_choices")
        elif self.return_to is not None and self.mode in {"catalog", "overview", "storage_choices", "workspaces"}:
            position, self.return_to = self.return_to, None
            self._navigate(position.mode, cursor=position.cursor, restore=True)
        elif self.context_return is not None and self.mode in {"cost", "stats", "allocation", "placement", "evidence"}:
            position, self.context_return = self.context_return, None
            self._navigate(position.mode, cursor=position.cursor, restore=True)
        elif self.mode != "home":
            self.selected, self.detail, self.artifact = None, None, None
            self.positions.clear()
            self._navigate("home", cursor=self.home_cursor)

    def action_refresh(self) -> None:
        if self.auth_expired or self._save_screen is not None or self._login_screen is not None:
            return
        self._remember()
        if self.mode == "resource":
            self._navigate("catalog")
        elif self.mode == "content" and self.artifact is None:
            self._navigate("files", cursor=self.file_cursor)
        else:
            self._focus_on_load = False
            self._read()

    def _next_cursor(self) -> str | None:
        result = self.result.get("recent") if self.mode == "home" and isinstance(self.result, dict) else self.result
        if isinstance(result, (MyManagedRunList, ManagedRunList, StorageWorkspaces, ManagedRunWorkspaces, ManagedRunArtifacts, ManagedRunArtifactContent, ManagedRunLogs)):
            values = result.values
            if values.get("has_more", values.get("truncated", not values.get("complete", True))):
                return values.get("next_cursor")
        return None

    def _page(self, *, first: bool = False, previous: bool = False) -> None:
        history = self.page_history.setdefault(self.mode, [])
        if self._reading or previous and not history:
            return
        following = history.pop() if previous else None if first else self._next_cursor()
        if following is None and not (first or previous):
            return
        if first:
            history.clear()
        elif not previous:
            history.append(self.cursor)
        if self.mode == "home":
            self.home_cursor = following
        self._navigate(self.mode, cursor=following)
        if self.mode == "home":
            self.home_highlight = None
            self.home_scroll = 0

    def _tool(self, mode: str) -> None:
        if self.return_to is None:
            self._remember()
            self.return_to = Position(self.mode, self.cursor)
        self._navigate(mode)

    def _commands(self) -> dict[str, str]:
        if self._login_screen is not None or self._save_screen is not None:
            return {}
        commands = {"refresh": self.t("refresh"), "start": self.t("start"), "catalog": self.t("catalog"),
                    "storage_choices": self.t("storage"), "overview": self.t("overview"), "workspaces": self.t("workspaces")}
        if self.job_query.scope != "self":
            commands["all_work"] = self.t("all_work")
        if self.mode != "home":
            commands["back"] = self.t("back")
        if self.mode in {"home", "run", "native"} and not self.auth_expired:
            commands["pause"] = self.t("resume" if self.paused else "pause")
        if self._next_cursor() is not None:
            commands["next"] = self.t("next")
        if self.cursor is not None:
            commands["first"] = self.t("first")
        if self.page_history.get(self.mode):
            commands["previous"] = self.t("previous")
        if self.selected and self.detail is not None and self.mode not in {"home", "catalog", "resource", "storage_choices", "storage", "storage_native", "overview", "workspaces"}:
            if self.selected.kind == "run":
                commands.update({key: self.t(label) for key, label in (("files", "results"), ("stdout", "logs"),
                    ("stderr", "stderr"), ("cost", "cost"), ("stats", "stats"), ("placement", "placement"), ("evidence", "evidence"))})
                commands["web"] = self.t("web")
            else:
                commands.update({key: self.t(key) for key in ("allocation", "cost", "placement", "evidence")})
        if self.mode == "storage":
            commands["storage_native"] = self.t("storage_native")
        if self.mode == "resource" and isinstance(self.result, tuple):
            selected = self.result[1]["name"]
            if selected in self.compared or len(self.compared) < 2:
                commands["compare"] = self.t("remove_compare" if selected in self.compared else "add_compare")
            if self.compared:
                commands["clear_compare"] = self.t("clear_compare")
        if self._can_save():
            commands["save"] = self.t("save_file")
        if self._web_url:
            commands["copy"] = self.t("copy")
        if self.auth_expired:
            commands = {"login": self.t("login")}
        return commands

    def _command(self, command: str | None) -> None:
        if command is None or command not in self._commands():
            return
        if command in {"refresh", "back", "save", "login", "start"}:
            getattr(self, "action_" + command)()
        elif command in {"catalog", "overview", "storage_choices", "workspaces"}:
            self._tool(command)
        elif command == "all_work":
            self._change_account(None)
        elif command == "pause":
            self.paused = not self.paused
            self._render()
        elif command in {"compare", "clear_compare"}:
            name = self.result[1]["name"]
            if command == "clear_compare":
                self.compared.clear()
            elif name in self.compared:
                self.compared.remove(name)
            else:
                self.compared.append(name)
            self._render()
        elif command in {"next", "first", "previous"}:
            self._page(first=command == "first", previous=command == "previous")
        elif command == "copy":
            self.copy_to_clipboard(self._web_url)
            self.query_one("#work-status", Static).update(self.t("copied"))
        elif command == "web" and isinstance(self.detail, ManagedRunDetail):
            options = dict(artifact_page=self.artifact[0], artifact_ref=self.artifact[1]) if self.artifact and self.mode == "content" else {
                "cost": self.mode == "cost", "stats": self.mode == "stats", "placement": self.mode == "placement"}
            self._show_link(self.detail.web_url(self.client.transport.base_url, **options))
        else:
            if command in {"cost", "stats", "allocation", "placement", "evidence"} and self.context_return is None:
                self.context_return = Position(self.mode, self.cursor)
            elif command in {"files", "stdout", "stderr"}:
                self.context_return = None
            self._navigate(command, cursor=self.file_cursor if command == "files" else None, restore=command in {"stdout", "stderr"})

    def action_more(self) -> None:
        if self._save_screen is None and self._login_screen is None:
            self.push_screen(ActionMenu(self.t("menu_title"), self._commands()), self._command)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        for command, label in self._commands().items():
            yield SystemCommand(label, label, lambda command=command: self._command(command))
        yield SystemCommand(self.t("quit"), self.t("quit"), self.action_quit)

    def action_command_palette(self) -> None:
        if self._save_screen is None and self._login_screen is None and not CommandPalette.is_open(self):
            self.push_screen(CommandPalette(placeholder=self.t("menu_title")))

    def _show_link(self, url: str) -> None:
        self._web_url = url
        self._render()
        try:
            self.open_url(url)
        except (OSError, BrowserError):
            pass

    def action_start(self) -> None:
        selectors = {"site_id": self.job_query.site_id}
        if self.job_query.workspace_key is not None:
            selectors["workspace_key"] = self.job_query.workspace_key
        self._show_link(urljoin(self.client.transport.base_url, "/v1/account/pilot/entry") + "?" + urlencode(selectors))

    def _can_save(self) -> bool:
        return (self.mode == "content" and isinstance(self.detail, ManagedRunDetail)
                and isinstance(self.result, ManagedRunArtifactContent) and self.result.values["status"] in {"available", "unsupported"}
                and self.artifact is not None and self._save_screen is None and not self._reading and self._pending is None)

    def action_save(self) -> None:
        if not self._can_save():
            return
        page, reference = self.artifact
        page.require_selection(self.detail, reference)
        item = next(row for row in page.values["items"] if row["artifact_ref"] == reference)
        revision, work = self._revision, self.selected

        async def save(output: str, cancelled: Event) -> dict[str, object]:
            async with self._client_lock:
                return await asyncio.to_thread(self.client.download_managed_run_artifact, work.reference,
                    workspace_key=work.workspace, site_id=self.job_query.site_id, artifact_ref=reference,
                    artifact_cursor=page.request_cursor, output=output, cancelled=cancelled.is_set)

        def finished(result: SaveResult) -> None:
            self._save_screen = None
            if revision != self._revision or self.selected != work:
                return
            if isinstance(result, SaiCliError):
                self._failed(result)
            else:
                self._render()
                message = self.t("save_complete", path=terminal_log(str(result["output"]))) if result else self.t("save_cancelled")
                self.query_one("#work-status", Static).update(message)

        self._save_screen = ArtifactSaveScreen(item["relative_path"].rsplit("/", 1)[-1], self.language, save)
        self.push_screen(self._save_screen, finished)

    def _placement_deadline(self) -> float | None:
        value = self.result.placement if isinstance(self.result, ManagedRunPlacement) else self.result
        if not isinstance(value, SiteJobPlacementResult) or value.inventory is None:
            return None
        deadlines = [value.inventory.expires_at, *(node.registration.valid_until for node in value.nodes if node.registration)]
        return min(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() for stamp in deadlines)

    def _stop_placement_timer(self) -> None:
        if self._placement_timer is not None:
            self._placement_timer.stop()
            self._placement_timer = None

    def _arm_placement_expiry(self) -> None:
        self._stop_placement_timer()
        deadline = self._placement_deadline()
        if deadline is None:
            return
        snapshot, revision = self.result, self._revision

        def expire() -> None:
            if self.result is not snapshot or self._revision != revision:
                return
            self._placement_timer = None
            if not self._expire_placement():
                self._arm_placement_expiry()

        if deadline <= time.time():
            self._expire_placement()
        else:
            self._placement_timer = self.set_timer(max(.001, deadline - time.time()), expire)

    def _expire_placement(self) -> bool:
        deadline = self._placement_deadline()
        if deadline is None or deadline > time.time():
            return False
        value = self.result.placement if isinstance(self.result, ManagedRunPlacement) else self.result
        self._stop_placement_timer()
        self.result = value.allocation
        self._placement_expired = True
        self._render()
        return True

    def on_unmount(self) -> None:
        self._stop_placement_timer()

    async def action_quit(self) -> None:
        if self._login_screen is not None:
            self._login_screen.action_cancel(quit_app=True)
        elif self._save_screen is not None:
            self._save_screen.action_cancel(quit_app=True)
        else:
            self.exit()

    def action_login(self) -> None:
        if not self.auth_expired or self._login_screen is not None or self._reading or self._pending:
            return

        def finished(success: bool) -> None:
            self._login_screen = None
            if success:
                self.auth_expired, self.paused = False, False
                self._navigate("home")
            else:
                self._render()

        self._login_screen = DeviceLoginScreen(provider=self.client.token_provider, language=self.language)
        self.push_screen(self._login_screen, finished)
