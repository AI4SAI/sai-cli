"""Optional terminal workbench over the existing authorized read client."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
import time
from webbrowser import Error as BrowserError

from rich.text import Text
from rich.table import Table
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding, BindingsMap
from textual.command import CommandPalette
from textual.containers import Horizontal, VerticalScroll
from textual.events import Resize
from textual.screen import Screen
from textual.theme import Theme, ThemeProvider
from textual.timer import Timer
from textual.widgets import Button, DataTable, Footer, Input, OptionList, Select, Static, TabbedContent, TabPane
from textual.widgets.option_list import Option

from .catalog import ResourceCatalog
from .client import JobQuery, PortalClient, clean_states
from .contracts import JobResult, RunningEstimateResult
from .errors import AuthenticationError, ConfigError, ContractError, ForbiddenError, SaiCliError
from .job_web_context import JobWebContext
from .managed_runs import (
    ManagedReadResult, ManagedRunList, ManagedRunDetail, ManagedRunLogs, ManagedRunArtifacts,
    clean_tasks_workspace, terminal_log, ManagedRunWorkspaces,
)
from .native_quota import NativeQuotaResult
from .overview import AccountOverview
from .overview_view import overview_panel
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .site_placement import SiteJobPlacementResult
from .storage_summary import StorageQuotaSummary
from .tui_messages import Messages
from .tui_views import (
    allocation_panel, placement_panel, resource_panel, display, modified_time_text, task_detail_panel, task_file_panel, task_artifact_option, storage_panel, state_text, task_state,
)



class TaskArtifactList(OptionList):
    BINDINGS = [Binding("ctrl+up", "scroll_up", show=False), Binding("ctrl+down", "scroll_down", show=False)]


class Workbench(App):
    TITLE = "SAI workbench"
    CSS = """
    Screen { layout: vertical; }
    #context { height: 2; padding: 0 1; background: $primary-background; }
    .controls { height: 3; }
    .controls Input { width: 1fr; min-width: 8; }
    .controls Select { width: 1fr; }
    .controls Button { min-width: 8; width: auto; }
    #scope { width: 22; }
    #selector { width: 8; }
    #status { height: 2; padding: 0 1; }
    TabbedContent { height: 2fr; min-height: 9; }
    TabPane { padding: 0 1; }
    DataTable { height: 1fr; min-height: 3; }
    #details-scroll { height: 1fr; min-height: 4; border-top: solid $primary; }
    #details { height: auto; padding: 0 1; }
    #task-artifact-hint { height: auto; padding: 0 1; }
    #task-artifacts { height: 1fr; min-height: 3; border: none; padding: 0 1; }
    #view-placement { height: 1; border: none; padding: 0 1; width: auto; }
    #web-link { width: 1fr; height: 100%; padding: 0 1; content-align: left middle; }
    #storage-scroll { height: 1fr; }
    #storage-summary { height: auto; }
    #overview-summary { height: auto; padding: 1 0; }
    .hint { height: auto; color: $text-muted; }
    .compact .controls { height: 1; }
    .compact .controls Input, .compact .controls Button,
    .compact .controls Select, .compact SelectCurrent { height: 1; border: none; padding: 0; }
    .compact TabbedContent { min-height: 8; }
    .compact #details-scroll { min-height: 3; }
    #task-heading { height: auto; padding: 0 1; text-style: bold; }
    .task-inspection TabbedContent { height: auto; min-height: 0; }
    .task-inspection #details-scroll { height: 1fr; }
    .task-inspection #tasks { height: auto; }
    .task-inspection #tasks-table { height: 3; min-height: 3; }
    .task-inspection #details { padding: 1; }
    .task-inspection #status { height: 1; }
    .task-inspection .controls { height: 1; }
    .task-inspection .controls Button { height: 1; border: none; padding: 0; }
    .placement-inspection TabbedContent { height: auto; min-height: 0; }
    .placement-inspection #jobs { height: auto; }
    .placement-inspection #jobs-table { height: 3; min-height: 3; }
    .placement-inspection #details-scroll { height: 1fr; }
    .resource-inspection TabbedContent { height: auto; min-height: 0; }
    .resource-inspection #resources { height: auto; }
    .resource-inspection #resources-table { height: 4; min-height: 3; }
    .resource-inspection #details-scroll { height: 1fr; }
    DataTable > .datatable--cursor { background: $primary-background; color: $text; }
    Button { background: $surface; }
    """

    def __init__(
        self, client: PortalClient, query: JobQuery, *, refresh_seconds: int = 10,
        storage_workspace_key: str | None = None,
        tasks_workspace_key: str | None = None,
        overview_account: str | None = None,
        initial_view: str = "resources",
        language: str = "en-US",
    ):
        super().__init__()
        self.t = Messages(language)
        self.language = language
        self.title = self.t("app")
        self.register_theme(Theme(name="sai", primary="#64d8d0", secondary="#8fa4b3", accent="#64d8d0",
                                  background="#151c24", surface="#202a34", panel="#26323f", foreground="#e4ebf1",
                                  success="#79b98b", warning="#d8b471", error="#de8b8d"))
        self.theme = "sai"
        # App.bind appends to inherited keys; one native binding map avoids
        # duplicate English defaults winning footer/action resolution.
        bindings = [Binding("ctrl+p", "command_palette", self.t("palette"), show=False, priority=True),
                    Binding("ctrl+c", "help_quit", show=False, system=True)]
        for key, action, label in (("f5", "refresh", "refresh"), ("f6", "pause", "pause"),
                                   ("escape", "back", "back"), ("a", "view_allocation", "allocation"),
                                   ("c", "compare_resource", "add_compare"),
                                   ("w", "open_web", "open_web"), ("ctrl+q", "quit", "quit")):
            bindings.append(Binding(key, action, self.t(label), show=key not in {"f6", "ctrl+q"}, priority=key == "ctrl+q"))
        self._bindings = BindingsMap(bindings)
        self.client = client
        self.job_query = query.validated()
        self.refresh_seconds = refresh_seconds
        self.view = initial_view
        self.paused = False
        self.selected_job: str | None = None
        self.job_mode = "detail"
        self.placement_result: SiteJobPlacementResult | None = None
        self._placement_timer: Timer | None = None
        self.selected_estimate: int | None = None
        self.compared: list[str] = []
        self.selected_resource: str | None = None
        self._selected_resource_row: str | None = None
        self.catalog: ResourceCatalog | None = None
        self.storage_workspace_key = (storage_workspace_key or "").strip() or None
        self.tasks_workspace_key = clean_tasks_workspace(tasks_workspace_key) if tasks_workspace_key else None
        self.selected_run: str | None = None
        self.task_mode = "list"
        self.task_cursor: str | None = None
        self.task_file_page: ManagedRunLogs | ManagedRunArtifacts | None = None
        self.selected_artifact: tuple[ManagedRunArtifacts, str] | None = None
        self.task_projects: ManagedRunWorkspaces | None = None
        self.project_cursor: str | None = None
        self.tasks_workspace_label: str | None = None
        self._task_list_cursor: str | None = None
        self._task_list_row: str | None = None
        self._task_list_scroll = 0.0
        self.overview_account = overview_account
        self.storage_source = "summary"
        self.results: dict[str, object] = {}
        self._failed_views: set[str] = set()
        self.usage_page = 0
        self._revision = 0
        self._pending = False
        self._reading = False
        self._job_detail_revision: int | None = None
        self._web_request: tuple[int, JobQuery, JobResult | SiteJobResult | SiteJobAllocationResult] | None = None
        self._web_url: str | None = None
        self._workbench_ready = False

    def compose(self) -> ComposeResult:
        t = self.t
        yield Static("", id="context", markup=False)
        with Horizontal(classes="controls", id="job-scope-controls"):
            yield Select([(t(s), s) for s in ("self", "personal-account", "org-account", "project-account")],
                         value=self.job_query.scope, allow_blank=False, id="scope")
            yield Select([(t("name"), "name"), (t("id"), "id")], value="id" if self.job_query.account_id else "name",
                         allow_blank=False, id="selector")
            yield Input(self.job_query.account_name or self.job_query.account_id or "", placeholder=t("account"), id="account")
        with Horizontal(classes="controls", id="job-filter-controls"):
            yield Input(self.job_query.partition or "", placeholder=t("partition"), id="partition")
            yield Input(",".join(self.job_query.states), placeholder=t("states_input"), id="states")
            yield Button(t("apply"), id="apply", variant="primary")
            yield Button(t("refresh"), id="refresh")
        yield Static("", id="status", markup=False)
        with TabbedContent(initial=self.view, id="views"):
            with TabPane(t("overview"), id="overview"):
                with VerticalScroll():
                    yield Static(t("overview_loading"), id="overview-summary", markup=False)
                    yield Button(t("messages"), id="overview-messages", disabled=True)
            with TabPane(t("resources"), id="resources"):
                yield Static(t("resources_hint"), classes="hint", markup=False)
                yield DataTable(id="resources-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button(t("add_compare"), id="compare-resource", disabled=True)
                    yield Button(t("view_jobs"), id="use-partition", disabled=True)
                    yield Button(t("clear_compare"), id="clear-comparison", tooltip=t("resource_comparison"))
                with Horizontal(classes="controls"):
                    yield Button(t("prepare_resource"), id="prepare-resource", disabled=True, tooltip=t("prepare_resource_help"))
            with TabPane(t("jobs"), id="jobs"):
                yield Static(t("jobs_hint", limit=self.job_query.limit), id="jobs-hint", classes="hint", markup=False)
                yield DataTable(id="jobs-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button(t("details"), id="view-job")
                    yield Button(t("allocation"), id="view-allocation", tooltip=t("command_allocation") + " (A)")
                    web_button = Button(t("open_web"), id="open-job-web", disabled=True, tooltip=t("web_job") + " (W)")
                    web_button.display = False
                    yield web_button
            with TabPane(t("tasks"), id="tasks"):
                with Horizontal(classes="controls", id="task-project-picker"):
                    yield Select([], prompt=t("choose_project"), id="tasks-project")
                with Horizontal(classes="controls", id="task-project-pages"):
                    yield Button(t("refresh"), id="load-projects", tooltip=t("find_projects"))
                    yield Button(t("first"), id="projects-first")
                    yield Button(t("next"), id="projects-next", disabled=True, tooltip=t("more_projects"))
                yield Static(t("projects_choose"), id="tasks-hint", classes="hint", markup=False)
                yield Static("", id="task-heading", markup=False)
                yield DataTable(id="tasks-table", cursor_type="row")
                with Horizontal(classes="controls", id="task-evidence-actions"):
                    yield Button(t("details"), id="task-detail", disabled=True)
                    yield Button(t("stdout"), id="task-stdout", disabled=True)
                    yield Button(t("stderr"), id="task-stderr", disabled=True)
                    yield Button(t("files"), id="task-files", disabled=True)
                with Horizontal(classes="controls", id="task-page-actions"):
                    yield Button(t("back"), id="task-back")
                    yield Button(t("first"), id="task-start", disabled=True)
                    yield Button(t("next"), id="task-next", disabled=True)
                    yield Button(t("open_web"), id="open-task-web", disabled=True, tooltip=t("web_task") + " (W)")
            with TabPane(t("usage"), id="usage"):
                yield Static(t("usage_hint"), classes="hint", markup=False)
                yield DataTable(id="usage-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button(t("previous"), id="previous")
                    yield Button(t("next"), id="next")
            with TabPane(t("storage"), id="storage"):
                with Horizontal(classes="controls"):
                    yield Select([(t("storage_stored"), "summary"), (t("storage_native"), "native")],
                                 value="summary", allow_blank=False, id="storage-source")
                with Horizontal(classes="controls"):
                    yield Input(self.storage_workspace_key or "", placeholder=t("workspace_input"), id="storage-workspace")
                    yield Button(t("load"), id="load-storage", variant="primary")
                yield Static(t("storage_hint"),
                             classes="hint", markup=False)
                with VerticalScroll(id="storage-scroll"):
                    yield Static(t("storage_choose"), id="storage-summary", markup=False)
        with VerticalScroll(id="details-scroll"):
            web_row = Horizontal(classes="controls", id="web-link-row")
            web_row.display = False
            with web_row:
                yield Static("", id="web-link", markup=False)
                yield Button(t("copy_link"), id="copy-web-link", disabled=True)
            placement_button = Button(t("placement"), id="view-placement", tooltip=t("placement_help"))
            placement_button.display = False
            yield placement_button
            yield Static("", id="details", markup=False)
            artifact_hint = Static("", id="task-artifact-hint", markup=False)
            artifact_hint.display = False
            yield artifact_hint
            artifacts = TaskArtifactList(id="task-artifacts")
            artifacts.display = False
            yield artifacts
        yield Footer()

    def on_mount(self) -> None:
        for name, columns in {
            "resources": ("resource_column", "kind"),
            "jobs": ("job", "name", "state", "partition", "nodes_reason"),
            "tasks": ("title", "state", "last_observed_at", "run"),
            "usage": ("job", "state", "estimate", "gross", "before_credit"),
        }.items():
            self.query_one(f"#{name}-table", DataTable).add_columns(*(self.t(column) for column in columns))
        self._workbench_ready = True
        for name in ("job-scope-controls", "job-filter-controls"):
            self.query_one(f"#{name}").display = self.view in {"jobs", "usage"}
        self.query_one("#details-scroll").display = self.view not in {"storage", "overview"}
        self._update_scope_display()
        self._task_layout()
        self.set_interval(self.refresh_seconds, self._tick)
        self.request_read()

    def on_resize(self, event: Resize) -> None:
        self.screen.set_class(event.size.height < 28 or event.size.width < 80, "compact")
        if self._workbench_ready:
            self.call_after_refresh(self._task_layout)
            if self.view == "resources":
                self.call_after_refresh(self._comparison)

    def _task_layout(self) -> None:
        inspection = self.view == "tasks" and self.selected_run is not None
        wide = self.size.width >= 100 and self.size.height >= 28
        self.screen.set_class(inspection, "task-inspection")
        self.screen.set_class(self.view == "resources" and self._selected_resource_row is not None, "resource-inspection")
        for name in ("task-project-picker", "task-project-pages", "tasks-hint"):
            self.query_one(f"#{name}").display = not inspection
        self.query_one("#tasks-table").display = (not inspection or wide) and self.task_mode != "projects"
        self.query_one("#task-heading").display = inspection
        self.query_one("#task-evidence-actions").display = inspection
        self.query_one("#task-page-actions").display = self.task_mode != "projects"
        self.query_one("#task-back").display = inspection
        self.query_one("#open-task-web").display = inspection
        self.query_one("#task-start").display = self.task_mode != "detail"
        self.query_one("#task-next").display = self.task_mode != "detail"
        if self.view == "tasks":
            self.query_one("#details-scroll").display = inspection
        self.refresh_bindings()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if not self._workbench_ready:
            return
        view = event.pane.id or "resources"
        if view == self.view:
            return
        previous_view = self.view
        self.selected_resource = self._selected_resource_row = None
        self._discard_allocation()
        self._clear_task_files()
        self.view = view
        self.selected_job = None
        self.job_mode = "detail"
        self.selected_estimate = None
        self._revision += 1
        for name in ("job-scope-controls", "job-filter-controls"):
            self.query_one(f"#{name}").display = view in {"jobs", "usage"}
        self.query_one("#details-scroll").display = view not in {"storage", "overview"}
        if view == "storage":
            self.query_one("#storage-workspace", Input).focus()
        elif view == "tasks":
            self.task_mode = "detail" if self.selected_run else "list"
            self.task_cursor = None if self.selected_run else self._task_list_cursor
            self.query_one("#tasks-project", Select).focus()
        elif view == "overview":
            self.query_one("#overview-summary", Static).scroll_visible()
        elif previous_view in {"storage", "overview"}:
            self.query_one(f"#{view}-table", DataTable).focus()
        self._update_scope_display()
        self._task_layout()
        self.query_one("#details", Static).update("")
        self.request_read()

    def _tick(self) -> None:
        self._expire_placement()
        if (not self.paused and not self._reading and self.view not in self._failed_views
                and not (self.view == "resources" and self._selected_resource_row is not None)
                and not (self.view == "usage" and self.selected_estimate is not None)
                and not (self.view == "tasks" and self.task_mode in {"projects", "stdout", "stderr", "files"})
                and not (self.view == "tasks" and self.tasks_workspace_key is None)
                and not (self.view == "jobs" and self.job_mode in {"allocation", "placement"} and self.selected_job is not None)):
            self.request_read()

    def request_read(self) -> None:
        if self.view == "resources":
            self.selected_resource = self._selected_resource_row = None
            self._comparison()
        self._clear_web_link()
        self._update_web_button()
        if self.view == "storage" and self.storage_workspace_key is None:
            self.query_one("#status", Static).update(self.t("storage_choose"))
            return
        if self.view == "tasks" and self.tasks_workspace_key is None:
            self.task_mode = "projects"
        self._task_layout()
        self._failed_views.discard(self.view)
        self._pending = True
        self._start_reader()

    def _start_reader(self) -> None:
        if not self._reading:
            self._reading = True
            self.run_worker(self._read_loop())
        self._update_web_button()
        self._update_task_actions()

    async def _read_loop(self) -> None:
        try:
            while self._pending or self._web_request is not None:
                if self._web_request is not None:
                    revision, query, snapshot = self._web_request
                    self._web_request = None
                    if revision == self._revision:
                        await self._read_web_context(revision, query, snapshot)
                    continue
                self._pending = False
                revision, view, query, selected = self._revision, self.view, self.job_query, self.selected_job
                workspace = self.storage_workspace_key
                storage_source = self.storage_source
                job_mode = self.job_mode
                task_request = (self.tasks_workspace_key, self.task_mode, self.selected_run, self.task_cursor)
                if view == "tasks" and self.task_mode == "projects":
                    task_request = (None, "projects", None, self.project_cursor)
                if view == "storage" and workspace is None:
                    continue
                if view == "tasks" and task_request[0] is None and task_request[1] != "projects":
                    continue
                if view == "tasks":
                    context = self.tasks_workspace_label or task_request[0] or self.t("project")
                elif view == "storage":
                    context = workspace
                elif view == "resources":
                    context = query.site_id
                else:
                    context = f"{self.t(query.scope)} · {query.account_name or query.account_id or self.t('self')}"
                self.query_one("#status", Static).update(self.t("refreshing", view=self.t(view), context=context))
                try:
                    result = await asyncio.to_thread(self._fetch, view, query, selected, workspace, storage_source, job_mode, task_request)
                except SaiCliError as error:
                    if revision == self._revision:
                        self._read_error(view, error)
                except Exception:
                    if revision == self._revision:
                        self._read_error(view, ContractError("The view could not be loaded."))
                else:
                    if revision == self._revision:
                        if view == "tasks" and isinstance(result, ManagedRunWorkspaces):
                            self.task_projects = result
                        elif view == "tasks" and isinstance(result, (ManagedRunLogs, ManagedRunArtifacts)):
                            self.task_file_page = result
                        elif isinstance(result, SiteJobPlacementResult):
                            self._clear_placement()
                            self.placement_result = result
                            self.results[view] = result.allocation
                            self._arm_placement_expiry()
                        else:
                            self.results[view] = result
                        self._present(view, result)
                        if view == "jobs" and selected is not None:
                            self._job_detail_revision = revision
        finally:
            self._reading = False
            if self.is_running:
                self._update_web_button()
                self._update_task_actions()
                self._update_resource_actions()

    def _update_web_button(self) -> None:
        button = self.query_one("#open-job-web", Button)
        result = self.results.get("jobs")
        valid = (isinstance(result, SiteJobAllocationResult) and result.job.canonical_id == self.selected_job) or (
            isinstance(result, (JobResult, SiteJobResult)) and len(result.items) == 1
            and result.items[0].canonical_id == self.selected_job
        )
        button.display = self.view == "jobs" and valid and self._job_detail_revision == self._revision
        button.disabled = self._reading or self._pending or self._web_request is not None
        placement_button = self.query_one("#view-placement", Button)
        placement_button.display = self.view == "jobs" and isinstance(result, SiteJobAllocationResult)
        placement_button.disabled = self._reading or self._pending
        hint = self.t("jobs_actions") if self._can_inspect_job() else self.t("jobs_hint", limit=self.job_query.limit)
        if button.display and not button.disabled:
            hint += self.t("jobs_web_hint")
        self.query_one("#jobs-hint", Static).update(hint)
        self.refresh_bindings()

    def _can_inspect_job(self) -> bool:
        result = self.results.get("jobs")
        return self.view == "jobs" and (isinstance(result, SiteJobAllocationResult) or (
            isinstance(result, (JobResult, SiteJobResult)) and bool(result.items)
        ))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "back":
            return bool(self.selected_job or self.selected_run or self.selected_estimate is not None)
        if action in {"view_allocation", "open_web", "compare_resource"}:
            if self.focused and any(isinstance(widget, (Input, Select)) for widget in self.focused.ancestors_with_self):
                return False
            if action == "view_allocation":
                return self._can_inspect_job()
            if action == "compare_resource":
                return self._resource_candidate() is not None
            if self.view == "resources":
                return self._resource_preparation_url() is not None
            button = self.query_one("#open-task-web" if self.view == "tasks" else "#open-job-web", Button)
            return button.display and not button.disabled
        return super().check_action(action, parameters)

    def action_view_allocation(self) -> None:
        if self._can_inspect_job():
            self._inspect_job("allocation")

    def action_view_placement(self) -> None:
        if self.view == "jobs" and isinstance(self.results.get("jobs"), SiteJobAllocationResult):
            self._inspect_job("placement")

    def _expire_placement(self) -> bool:
        result = self.placement_result
        if result is None or result.inventory is None:
            return False
        expiries = [result.inventory.expires_at]
        expiries.extend(node.registration.valid_until for node in result.nodes if node.registration is not None)
        if min(datetime.fromisoformat(value[:-1] + "+00:00").timestamp() for value in expiries) > time.time():
            return False
        self._clear_placement()
        if self.view == "jobs":
            self._present("jobs", result.allocation)
            self.query_one("#status", Static).update(self.t("placement_expired"))
        return True

    def _clear_placement(self) -> None:
        if self._placement_timer is not None:
            self._placement_timer.stop()
            self._placement_timer = None
        self.placement_result = None

    def _arm_placement_expiry(self) -> None:
        result, revision = self.placement_result, self._revision
        if result is None or result.inventory is None:
            return
        expiries = [result.inventory.expires_at]
        expiries.extend(node.registration.valid_until for node in result.nodes if node.registration is not None)
        deadline = min(datetime.fromisoformat(value[:-1] + "+00:00").timestamp() for value in expiries)

        def expire() -> None:
            if self.placement_result is result and self._revision == revision:
                self._placement_timer = None
                if not self._expire_placement():
                    self._arm_placement_expiry()

        self._placement_timer = self.set_timer(max(0.001, deadline - time.time()), expire)

    def action_open_web(self) -> None:
        if self.view == "resources":
            url = self._resource_preparation_url()
            if url is not None:
                self._show_web_link(url, self.t("prepare_resource"))
            return
        if self.view != "tasks":
            self._open_job_in_web()
            return
        if not self._can_open_task_web():
            return
        result = self.results["tasks"]
        if self.selected_artifact is not None:
            page, artifact_ref = self.selected_artifact
            if self.task_mode != "files" or page is not self.task_file_page:
                self._clear_artifact_selection()
                return
            url = result.web_url(self.client.transport.base_url, artifact_page=page, artifact_ref=artifact_ref)
            self._show_web_link(url, self.t("web_file"))
        else:
            self._show_web_link(result.web_url(self.client.transport.base_url), self.t("web_task"))

    def action_copy_web_link(self) -> None:
        if self.view in {"jobs", "tasks", "resources"} and self._web_url is not None:
            self.copy_to_clipboard(self._web_url)
            self.query_one("#status", Static).update(self.t("copy_ready"))

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield SystemCommand(self.t("theme"), self.t("theme_help"), self.action_change_theme)
        yield SystemCommand(self.t("quit"), self.t("exit_help"), self.action_quit)
        yield SystemCommand(self.t("refresh"), self.t("refresh_help"), self.action_refresh)
        yield SystemCommand(self.t("pause"), self.t("pause_help"), self.action_pause)
        if self.check_action("back", ()):
            yield SystemCommand(self.t("back"), self.t("back_help"), self.action_back)
        yield SystemCommand(self.t("command_tasks"), self.t("command_tasks_help"), self.action_tasks)
        if self.view == "tasks":
            yield SystemCommand(self.t("refresh_projects"), self.t("projects_choose"), self._read_projects)
            if not self.query_one("#projects-next", Button).disabled:
                yield SystemCommand(self.t("more_projects"), self.t("projects_choose"),
                                    lambda: self._read_projects(self.task_projects.values["next_cursor"]))
            if not self.query_one("#task-next", Button).disabled:
                yield SystemCommand(self.t("next"), self.t("more_pages"), lambda: self._task_page(start=False))
        if self.view == "tasks" and isinstance(self.results.get("tasks"), ManagedRunDetail):
            for mode in ("detail", "stdout", "stderr", "files"):
                yield SystemCommand(self.t("command_" + mode), self.t("command_task_help"), lambda mode=mode: self._inspect_task(mode))
        if self._can_inspect_job():
            yield SystemCommand(self.t("command_allocation"), self.t("command_allocation_help"), self.action_view_allocation)
        if self.view == "jobs" and isinstance(self.results.get("jobs"), SiteJobAllocationResult):
            yield SystemCommand(self.t("placement"), self.t("placement_help"), self.action_view_placement)
        button = self.query_one("#open-job-web", Button)
        if button.display and not button.disabled:
            yield SystemCommand(self.t("command_web"), self.t("command_web_help"), self.action_open_web)
        elif self._can_open_task_web():
            yield SystemCommand(self.t("command_web"), self.t("command_web_help"), self.action_open_web)
        if self.view == "resources" and self._resource_preparation_url() is not None:
            yield SystemCommand(self.t("prepare_resource"), self.t("prepare_resource_help"), self.action_open_web)
        if self.view == "resources" and self._resource_candidate() is not None:
            yield SystemCommand(self.t("add_compare"), self.t("resource_comparison"), self.action_compare_resource)
        if self.view in {"jobs", "tasks", "resources"} and self._web_url is not None:
            yield SystemCommand(self.t("command_copy"), self.t("command_copy_help"), self.action_copy_web_link)

    def action_command_palette(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(CommandPalette(id="--command-palette", placeholder=self.t("command_search")))

    def search_themes(self) -> None:
        self.push_screen(CommandPalette(providers=[ThemeProvider], placeholder=self.t("theme_search")))

    def action_help_quit(self) -> None:
        self.notify(self.t("quit_hint"), title=self.t("quit"))

    def _open_job_in_web(self) -> None:
        button = self.query_one("#open-job-web", Button)
        if not button.display or button.disabled:
            return
        snapshot = self.results.get("jobs")
        if not isinstance(snapshot, (JobResult, SiteJobResult, SiteJobAllocationResult)):
            return
        self._clear_web_link()
        self._web_request = (self._revision, replace(self.job_query, cluster_id=snapshot.cluster_id), snapshot)
        self._start_reader()

    def _clear_web_link(self) -> None:
        self._web_url = None
        link = self.query_one("#web-link", Static)
        link.update("")
        self.query_one("#web-link-row", Horizontal).display = False
        self.query_one("#copy-web-link", Button).disabled = True

    def _show_web_link(self, url: str, label: str) -> None:
        self._web_url = url
        self.query_one("#web-link", Static).update(Text(label, style=f"link {url}"))
        row = self.query_one("#web-link-row", Horizontal)
        row.display = True
        self.query_one("#copy-web-link", Button).disabled = False
        self.call_after_refresh(row.scroll_visible, animate=False)
        self.query_one("#status", Static).update(self.t("web_ready"))
        try:
            self.open_url(url)
        except (OSError, BrowserError):
            self.query_one("#status", Static).update(self.t("web_copy"))

    async def _read_web_context(self, revision: int, query: JobQuery,
                                snapshot: JobResult | SiteJobResult | SiteJobAllocationResult) -> None:
        job = snapshot.job if isinstance(snapshot, SiteJobAllocationResult) else snapshot.items[0]
        link_ready = False
        self.query_one("#status", Static).update(self.t("web_resolving"))
        try:
            target = await asyncio.to_thread(self.client.job_web_context, job.canonical_id, query)
            if revision != self._revision:
                return
            if not isinstance(target, JobWebContext):
                raise ContractError("The job Web context is invalid.")
            observed = snapshot.freshness.queried_at if isinstance(snapshot, JobResult) else snapshot.freshness.observed_at
            submitted = job.values["submit_time"]
            restart = snapshot.restart_count if isinstance(snapshot, SiteJobAllocationResult) else None
            url = target.web_url(self.client.transport.base_url, observed_at=observed,
                                 submit_time=submitted, restart_count=restart)
            if target.changed_since(submit_time=submitted, restart_count=restart):
                self.query_one("#status", Static).update(self.t("web_changed"))
                return
            link_ready = True
            self._show_web_link(url, self.t("web_job"))
        except SaiCliError as error:
            if revision == self._revision:
                if isinstance(error, AuthenticationError) or (
                    isinstance(error, ForbiddenError) and error.code != "job_navigation_workspace_denied"
                ):
                    self._read_error("jobs", error)
                else:
                    self.query_one("#status", Static).update(f"{self.t('web_failed')} · {error.code}")
        except Exception:
            if revision == self._revision:
                self.query_one("#status", Static).update(self.t("web_ready" if link_ready else "web_failed"))

    def action_tasks(self) -> None:
        self.query_one("#views", TabbedContent).active = "tasks"

    def _read_projects(self, cursor: str | None = None) -> None:
        if self.view != "tasks":
            return
        self._revision += 1
        self._clear("tasks")
        self.tasks_workspace_key = None
        self.tasks_workspace_label = None
        self._task_list_cursor = self._task_list_row = None
        self._task_list_scroll = 0.0
        self.task_mode = "projects"
        self.project_cursor = cursor
        self.task_projects = None
        with self.prevent(Select.Changed):
            self.query_one("#tasks-project", Select).set_options([])
        self._update_scope_display()
        self.request_read()

    def _apply_task_project(self, key: str) -> None:
        if self.task_projects is None:
            return
        item = next((item for item in self.task_projects.values["items"] if item["workspace_key"] == key), None)
        if item is None:
            return
        self._revision += 1
        self._clear("tasks")
        self.tasks_workspace_key = key
        self.tasks_workspace_label = self._project_labels()[key]
        self._task_list_cursor = self._task_list_row = None
        self._task_list_scroll = 0.0
        self._update_scope_display()
        self.request_read()
        self.query_one("#tasks-table", DataTable).focus()

    def _clear_task_files(self) -> None:
        self._clear_artifact_selection()
        self.task_file_page = None
        self.query_one("#task-artifacts", OptionList).clear_options()
        self.query_one("#task-artifacts").display = False
        self.query_one("#task-artifact-hint").display = False
        if self.view == "tasks":
            result = self.results.get("tasks")
            self.query_one("#details", Static).update(task_detail_panel(result, self.language) if isinstance(result, ManagedRunDetail) else "")
        self._update_task_actions()

    def _clear_artifact_selection(self) -> None:
        previous = self.selected_artifact
        self.selected_artifact = None
        self._clear_web_link()
        if previous is not None:
            page, artifact_ref = previous
            options = self.query_one("#task-artifacts", OptionList)
            if page is self.task_file_page and any(option.id == artifact_ref for option in options.options):
                item = next(item for item in page.values["items"] if item["artifact_ref"] == artifact_ref)
                options.replace_option_prompt(artifact_ref, task_artifact_option(item, self.language))
        self.query_one("#task-artifact-hint", Static).update(self.t("files_choose"))
        self.query_one("#open-task-web", Button).tooltip = self.t("web_task") + " (W)"

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if (event.option_list.id == "task-artifacts" and self.selected_artifact is not None
                and any(option is event.option for option in event.option_list.options)):
            if event.option.id != self.selected_artifact[1]:
                self._clear_artifact_selection()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if (event.option_list.id != "task-artifacts" or self.view != "tasks" or self.task_mode != "files"
                or not self._can_open_task_web() or not isinstance(self.task_file_page, ManagedRunArtifacts)
                or not any(option is event.option for option in event.option_list.options)):
            return
        page, reference = self.task_file_page, event.option.id
        if reference is None:
            return
        detail = self.results["tasks"]
        page.require_selection(detail, reference)
        self._clear_artifact_selection()
        self.selected_artifact = (page, reference)
        item = next(item for item in page.values["items"] if item["artifact_ref"] == reference)
        event.option_list.replace_option_prompt(reference, task_artifact_option(item, self.language, selected=True))
        self.query_one("#task-artifact-hint", Static).update(self.t("file_continue"))
        self._update_task_actions()

    def _project_labels(self) -> dict[str, str]:
        if self.task_projects is None:
            return {}
        items = self.task_projects.values["items"]
        labels = [item["label"] + (f" · {item['organization_label']}" if item["organization_label"] else "") for item in items]
        return {item["workspace_key"]: label + (f" · {item['workspace_key']}" if labels.count(label) > 1 else "")
                for item, label in zip(items, labels)}

    def _update_task_actions(self) -> None:
        result = self.results.get("tasks")
        busy = self._reading or self._pending
        rows = isinstance(result, ManagedRunList) and bool(result.values["items"])
        detail = isinstance(result, ManagedRunDetail) and result.values["run"]["run_ref"] == self.selected_run
        for name in ("detail", "stdout", "stderr", "files"):
            button = self.query_one(f"#task-{name}", Button)
            button.disabled = not (detail or (name == "detail" and rows))
            button.variant = "primary" if self.selected_run and self.task_mode == name else "default"
        page = result if self.task_mode == "list" else self.task_file_page
        more = page is not None and bool(page.values.get("has_more") if isinstance(page, ManagedRunList)
            else page.values["truncated"] if isinstance(page, ManagedRunLogs) else not page.values["complete"])
        self.query_one("#task-next", Button).disabled = busy or not more or page.values.get("next_cursor") is None
        self.query_one("#task-start", Button).disabled = busy or not self.tasks_workspace_key or self.task_mode == "detail"
        self.query_one("#open-task-web", Button).disabled = not self._can_open_task_web()
        self.query_one("#open-task-web", Button).tooltip = self.t("web_file" if self.selected_artifact else "web_task") + " (W)"
        self.query_one("#projects-next", Button).disabled = busy or self.task_projects is None or not self.task_projects.values["has_more"]
        self.query_one("#projects-first", Button).disabled = busy or self.project_cursor is None
        self.query_one("#load-projects", Button).disabled = busy
        self._task_layout()
        self.refresh_bindings()

    def _can_open_task_web(self) -> bool:
        result = self.results.get("tasks")
        return (self.view == "tasks" and not self._reading and not self._pending
                and isinstance(result, ManagedRunDetail) and result.values["run"]["run_ref"] == self.selected_run
                and result.values["workspace_key"] == self.tasks_workspace_key
                and result.values["site_id"] == self.job_query.site_id)

    def _inspect_task(self, mode: str, *, run_ref: str | None = None) -> None:
        if self.view != "tasks" or self.tasks_workspace_key is None:
            return
        result = self.results.get("tasks")
        if isinstance(result, ManagedRunList):
            if mode != "detail" or not result.values["items"]:
                return
            table = self.query_one("#tasks-table", DataTable)
            run_ref = run_ref or table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            if not any(run["run_ref"] == run_ref for run in result.values["items"]):
                return
            self._task_list_cursor = self.task_cursor
            self._task_list_row = run_ref
            self._task_list_scroll = table.scroll_y
        elif isinstance(result, ManagedRunDetail):
            run_ref = result.values["run"]["run_ref"]
        else:
            return
        self.selected_run = run_ref
        self.task_mode, self.task_cursor = mode, None
        self._revision += 1
        self._clear_task_files()
        self.request_read()
        self.query_one("#details-scroll", VerticalScroll).scroll_home(animate=False)
        self.query_one(f"#task-{mode}", Button).focus()

    def _task_page(self, *, start: bool) -> None:
        if self.view != "tasks" or self.task_mode == "detail" or self.tasks_workspace_key is None:
            return
        button = self.query_one("#task-start" if start else "#task-next", Button)
        if button.disabled:
            return
        page = self.results.get("tasks") if self.task_mode == "list" else self.task_file_page
        if not start and page is None:
            return
        self.task_cursor = None if start else page.values["next_cursor"]
        self._revision += 1
        self._clear_task_files()
        if self.task_mode == "list":
            self._task_list_row = None
            self._task_list_scroll = 0.0
            self.results.pop("tasks", None)
            self.query_one("#tasks-table", DataTable).clear()
        self.request_read()

    def _fetch(self, view: str, query: JobQuery, selected: str | None, workspace: str | None,
               storage_source: str = "summary", job_mode: str = "detail", task_request: tuple = ()):
        if view == "tasks":
            task_workspace, mode, run, cursor = task_request
            if mode == "projects":
                return self.client.list_run_workspaces(site_id=query.site_id, limit=50, cursor=cursor)
            scope = {"workspace_key": task_workspace, "site_id": query.site_id}
            if mode == "list":
                return self.client.list_managed_runs(**scope, limit=50, cursor=cursor)
            if mode == "detail":
                return self.client.managed_run(run, **scope)
            if mode in {"stdout", "stderr"}:
                return self.client.managed_run_logs(run, **scope, stream=mode, cursor=cursor, max_bytes=65536)
            return self.client.managed_run_artifacts(run, **scope, cursor=cursor, limit=100)
        if view == "overview":
            return self.client.account_overview(query.site_id, account=self.overview_account)
        if view == "resources":
            return self.client.resource_catalog(query.site_id)
        if view == "storage":
            if storage_source == "native":
                return self.client.storage_native_quota(workspace_key=workspace, site_id=query.site_id)
            return self.client.storage_quota_summary(workspace_key=workspace, site_id=query.site_id)
        if view == "usage":
            return self.client.running_estimates(query)
        if selected:
            if job_mode == "placement":
                return self.client.job_placement(selected, replace(query, partition=None))
            if job_mode == "allocation":
                return self.client.job_allocation(selected, replace(query, partition=None))
            return self.client.show_job(selected, replace(query, partition=None))
        return self.client.list_jobs(query)

    def _clear(self, view: str) -> None:
        self.results.pop(view, None)
        if view == "tasks":
            self._clear_web_link()
            self.selected_run = None
            self.task_mode = "list"
            self.task_cursor = None
            self._clear_task_files()
            self.query_one("#task-heading", Static).update("")
        if view == "jobs":
            self._clear_placement()
            self.screen.remove_class("placement-inspection")
            self.query_one("#view-placement", Button).display = False
            self._job_detail_revision = None
            self.query_one("#open-job-web", Button).display = False
            self._clear_web_link()
        if view == "overview":
            self.query_one("#overview-summary", Static).update("")
            self.query_one("#overview-messages", Button).disabled = True
        elif view == "storage":
            self.query_one("#storage-summary", Static).update("")
        else:
            self.query_one(f"#{view}-table", DataTable).clear()
        if view == "resources":
            self.catalog = None
            self.compared.clear()
            self.selected_resource = self._selected_resource_row = None
            self._clear_web_link()
            self._update_resource_actions()
        if view == "usage":
            self.usage_page = 0
            self.selected_estimate = None
        if view == self.view:
            self.query_one("#details", Static).update("")

    def _read_error(self, view: str, error: SaiCliError) -> None:
        self._failed_views.add(view)
        if view == "jobs" and self.job_mode == "placement" and not isinstance(error, (AuthenticationError, ForbiddenError)):
            self._clear_placement()
            result = self.results.get("jobs")
            if isinstance(result, SiteJobAllocationResult):
                self._present("jobs", result)
            self.query_one("#status", Static).update(f"{self.t('read_failed')} · {error.code}")
            return
        was_projects = view == "tasks" and self.task_mode == "projects"
        if view == "tasks" and isinstance(error, ForbiddenError) and error.code == "run_file_read_denied":
            self._clear_task_files()
            self.query_one("#status", Static).update(f"{self.t('file_denied')} · {error.code}")
            return
        if view == "tasks":
            self.task_projects = None
            self.tasks_workspace_label = None
            if isinstance(error, (ForbiddenError, AuthenticationError)):
                self.tasks_workspace_key = None
                self._task_list_cursor = self._task_list_row = None
            with self.prevent(Select.Changed):
                self.query_one("#tasks-project", Select).set_options([])
        if isinstance(error, AuthenticationError):
            for name in ("resources", "jobs", "usage", "storage", "overview", "tasks"):
                self._clear(name)
            self.selected_job = None
            self.job_mode = "detail"
            self._revision += 1
            self._pending = False
            self.paused = True
            self.task_projects = None
            self.tasks_workspace_label = None
            self.tasks_workspace_key = None
            self._task_list_cursor = self._task_list_row = None
            with self.prevent(Select.Changed):
                self.query_one("#tasks-project", Select).set_options([])
        else:
            self._clear(view)
        if was_projects:
            self.task_mode = "projects"
            self.query_one("#tasks-hint", Static).update(self.t(
                "projects_cursor_failed" if self.project_cursor is not None and isinstance(error, ConfigError)
                else "projects_failed"))
        self._update_scope_display()
        self._update_task_actions()
        message = ("session_expired" if isinstance(error, AuthenticationError) else
                   "access_denied" if isinstance(error, ForbiddenError) else
                   "configuration_needed" if isinstance(error, ConfigError) else "read_failed")
        self.query_one("#status", Static).update(f"{self.t(message)} · {error.code}")

    def _rows(self, view: str, rows: list[tuple[str, tuple[object, ...]]]) -> None:
        table = self.query_one(f"#{view}-table", DataTable)
        previous = None
        if table.row_count:
            previous = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        table.clear()
        for key, values in rows:
            table.add_row(*(value if isinstance(value, Text) else Text(display(value, self.language)) for value in values), key=key)
        if previous is not None and previous in [key for key, _ in rows]:
            table.move_cursor(row=table.get_row_index(previous))

    def _present(self, view: str, result: object) -> None:
        self.screen.set_class(self.view == "jobs" and self.placement_result is not None, "placement-inspection")
        status = ""
        if view == "tasks" and isinstance(result, ManagedRunWorkspaces):
            labels = self._project_labels()
            choices = [(Text(label), key) for key, label in labels.items()]
            if self.tasks_workspace_key in labels:
                self.tasks_workspace_label = labels[self.tasks_workspace_key]
            with self.prevent(Select.Changed):
                self.query_one("#tasks-project", Select).set_options(choices)
            self.query_one("#tasks-hint", Static).update(self.t("projects_choose" if choices else "projects_empty"))
            status = self.t("project_page", count=len(choices), more=self.t("more_suffix") if result.values["has_more"] else "")
            self._update_scope_display()
            self._update_task_actions()
        elif view == "tasks" and isinstance(result, ManagedReadResult):
            data = result.values
            if isinstance(result, (ManagedRunList, ManagedRunDetail)):
                runs = data["items"] if isinstance(result, ManagedRunList) else [data["run"]]
                self._rows("tasks", [(row["run_ref"], (
                    terminal_log(row["title"]) if row["title"] is not None else self.t("untitled"),
                    task_state(row["status"], self.t), row["last_observed_at"], row["run_ref"],
                )) for row in runs])
                if isinstance(result, ManagedRunList):
                    self.query_one("#tasks-hint", Static).update(self.t("task_hint" if runs else "task_empty"))
                    self.query_one("#details", Static).update("")
                    table = self.query_one("#tasks-table", DataTable)
                    if self._task_list_row and any(run["run_ref"] == self._task_list_row for run in runs):
                        table.move_cursor(row=table.get_row_index(self._task_list_row))
                        table.scroll_to(y=self._task_list_scroll, animate=False)
                else:
                    run = data["run"]
                    self.query_one("#details", Static).update(task_detail_panel(result, self.language))
                    heading = Text(terminal_log(run['title']) if run['title'] is not None else self.t('untitled'))
                    heading.append(" · ").append_text(task_state(run["status"], self.t))
                    self.query_one("#task-heading", Static).update(heading)
                status = self.t("task_records", time=data["queried_at"])
            elif isinstance(result, ManagedRunArtifacts):
                self._clear_artifact_selection()
                options = self.query_one("#task-artifacts", OptionList)
                options.clear_options().add_options([
                    Option(task_artifact_option(item, self.language), id=item["artifact_ref"])
                    for item in data["items"]
                ])
                options.display = bool(data["items"])
                self.query_one("#task-artifact-hint").display = bool(data["items"])
                self.query_one("#details", Static).update(
                    self.t("last_page" if data["complete"] else "more_pages") if data["items"]
                    else self.t("files_empty")
                )
                if data["items"]:
                    options.focus()
                status = self.t("file_status", mode=self.t(self.task_mode), time=data["observed_at"])
            else:
                self.query_one("#details", Static).update(task_file_panel(result, self.language))
                status = self.t("file_status", mode=self.t(self.task_mode), time=data["observed_at"])
            self._update_task_actions()
        elif view == "overview" and isinstance(result, AccountOverview):
            self.query_one("#overview-summary", Static).update(overview_panel(result, base_url=self.client.transport.base_url, language=self.language))
            self.query_one("#overview-messages", Button).disabled = False
            status = self.t("overview_status")
        elif view == "storage" and isinstance(result, StorageQuotaSummary):
            self.query_one("#storage-summary", Static).update(storage_panel(result, self.language))
            values = result.values
            status = self.t("storage_sample", state=state_text(values['state'], self.t), time=display(values['observed_at'], self.language))
        elif view == "storage" and isinstance(result, NativeQuotaResult):
            self.query_one("#storage-summary", Static).update(storage_panel(result, self.language))
            status = self.t("storage_native_status", time=result.values['as_of'])
        elif view == "resources" and isinstance(result, ResourceCatalog):
            self.catalog = result
            data = result.as_dict()
            rows = [(f"compute:{i}", (r["title"], r["resource_kind"])) for i, r in enumerate(data["compute"])]
            rows += [(f"storage:{i}", (r["name"], r["filesystem_type"]))
                     for i, r in enumerate(data["storage"])]
            self._rows(view, rows)
            self.compared = [name for name in self.compared if any(r["name"] == name for r in data["compute"])]
            self._comparison()
            self._update_scope_display()
            status = self.t("resource_status" if rows else "resource_empty")
        elif isinstance(result, SiteJobPlacementResult):
            self._present(view, result.allocation)
            if self._expire_placement():
                return
            self.query_one("#details", Static).update(placement_panel(result, self.language))
            status = f"{self.t('placement')} · {result.allocation.freshness.observed_at} · {self.t('auto_paused')}"
        elif isinstance(result, SiteJobAllocationResult):
            job, freshness = result.job, result.freshness
            self._rows("jobs", [("0", (job.canonical_id, *(job.values[k] for k in
                ("name", "state", "partition", "reason_or_nodelist"))))])
            self.query_one("#details", Static).update(allocation_panel(result, self.language))
            status = f"{self.t('allocation')} · {freshness.observed_at} · {self.t('auto_paused')}"
        elif isinstance(result, (JobResult, SiteJobResult)):
            self._rows(view, [(str(i), (r.canonical_id, *(r.values[k] for k in
                ("name", "state", "partition", "reason_or_nodelist")))) for i, r in enumerate(result.items)])
            if self.selected_job:
                item = result.items[0].values if result.items else {}
                text = f"{self.t('job')}: {self.selected_job}\n" + "\n".join(f"{self.t(label)}: {display(item.get(key), self.language)}" for key, label in (
                    ("name", "name"), ("state_label", "state"),
                    ("reason_or_nodelist", "nodes_reason"), ("partition", "partition"),
                    ("qos", "qos"), ("slurm_user", "user"), ("slurm_account", "account"),
                    ("nodes", "nodes"), ("gpus_per_node", "gpu_node"), ("slots", "slots"),
                    ("submit_time", "submitted"), ("start_time", "started"),
                    ("elapsed_seconds", "elapsed")))
                self.query_one("#details", Static).update(text)
            freshness = result.freshness
            if isinstance(result, SiteJobResult):
                status = (f"{freshness.source} · {freshness.observed_at} · " + self.t("age", seconds=freshness.age_seconds)
                          + f" · {self.t('stale' if freshness.stale else 'fresh')} · "
                          + self.t("has_more", value=self.t("yes" if result.has_more else "no")))
            else:
                status = f"{freshness.source} · {freshness.queried_at} · " + self.t("jobs_hint", limit=self.job_query.limit)
            if not result.items:
                status += " · " + self.t("empty_jobs")
        elif isinstance(result, RunningEstimateResult):
            self.usage_page = min(self.usage_page, max(0, (len(result.items) - 1) // 100))
            start = self.usage_page * 100
            visible = result.items[start:start + 100]
            self._rows(view, [(str(start + i), (r.values["job_id_raw"], r.values["state"],
                state_text(r.values["estimate_status"], self.t), r.values["gross_cny"], r.values["cash_before_credit_cny"]))
                for i, r in enumerate(visible)])
            status = (self.t("usage_status", time=result.as_of, page=self.usage_page + 1)
                      + " · " + self.t("stale" if result.freshness.stale else "fresh"))
            self.query_one("#previous", Button).disabled = self.usage_page == 0
            self.query_one("#next", Button).disabled = start + 100 >= len(result.items)
            self.query_one("#details", Static).update(self.t("usage_choose"))
        self.query_one("#status", Static).update(status + (" · " + self.t("auto_paused") if self.paused else ""))

    def _comparison(self) -> None:
        if self.catalog is None:
            return
        if self._selected_resource_row is not None and self._selected_resource_row.startswith("storage:"):
            row = self.catalog.values["storage"][int(self._selected_resource_row.split(":")[1])]
            self.query_one("#details", Static).update(
                f"{row['name']} · {row['scope_label']}\n{row['description']}\n"
                + "\n".join(f"{r['label']}: {r['value']}" for r in row["hardware"])
                + f"\n{self.t('package')}: {row['package_pricing']['display']}\n{self.t('usage_price')}: {row['usage_pricing']['display']}"
                + f"\n{self.t('metering')}: {self.t('yes' if row['metered_settlement_enabled'] else 'no')}"
            )
            self._update_resource_actions()
            return
        rows = [r for name in self.compared for r in self.catalog.values["compute"] if r["name"] == name]
        candidates = [row for row in self.catalog.values["compute"] if row["name"] == self.selected_resource]
        self.query_one("#details", Static).update(resource_panel(candidates[0] if len(candidates) == 1 else None,
                                                                 rows, self.language, self.size.width))
        self._update_resource_actions()

    def _resource_candidate(self) -> dict | None:
        if (self.view != "resources" or self._reading or self._pending or self.catalog is None
                or self.results.get("resources") is not self.catalog
                or self.catalog.values["site_id"] != self.job_query.site_id):
            return None
        rows = [row for row in self.catalog.values["compute"] if row["name"] == self.selected_resource]
        return rows[0] if len(rows) == 1 else None

    def _resource_preparation_url(self) -> str | None:
        row = self._resource_candidate()
        if row is None:
            return None
        try:
            return self.catalog.preparation_url(self.client.transport.base_url, row["name"])
        except ConfigError:
            return None

    def _update_resource_actions(self) -> None:
        candidate = self._resource_candidate()
        self.query_one("#compare-resource", Button).disabled = candidate is None
        self.query_one("#compare-resource", Button).label = self.t("remove_compare" if self.selected_resource in self.compared else "add_compare")
        self.query_one("#prepare-resource", Button).disabled = self._resource_preparation_url() is None
        self.query_one("#use-partition", Button).disabled = self._resource_preparation_url() is None
        self.query_one("#clear-comparison", Button).disabled = not self.compared
        self._task_layout()

    def action_compare_resource(self) -> None:
        candidate = self._resource_candidate()
        if candidate is None:
            return
        name = candidate["name"]
        if name in self.compared:
            self.compared.remove(name)
        elif len(self.compared) < 2:
            self.compared.append(name)
        else:
            self.query_one("#status", Static).update(self.t("compare_full"))
            return
        self._comparison()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if (event.data_table.id == "resources-table" and self.view == "resources"
                and self.catalog and not self._reading and not self._pending):
            kind, index = key.split(":")
            row = self.catalog.values[kind][int(index)]
            self._clear_web_link()
            self._selected_resource_row = key
            if kind == "compute":
                self.selected_resource = row["name"]
                self._comparison()
                if self._resource_preparation_url() is None:
                    self.query_one("#status", Static).update(self.t("resource_reference_invalid"))
            else:
                self.selected_resource = None
                self._comparison()
            self.call_after_refresh(self.query_one("#details-scroll", VerticalScroll).scroll_home, animate=False)
        elif event.data_table.id == "jobs-table":
            self._inspect_job("detail", row_key=key)
        elif event.data_table.id == "tasks-table":
            self._inspect_task("detail", run_ref=key)
        elif event.data_table.id == "usage-table":
            result = self.results.get("usage")
            if isinstance(result, RunningEstimateResult):
                self.selected_estimate = int(key)
                self._revision += 1
                self._pending = False
                item = result.items[self.selected_estimate].values
                lines = [f"{self.t(label)}: " + (state_text(item[name], self.t) if name == "estimate_status"
                         else display(item[name], self.language)) for name, label in (
                    ("job_id_raw", "job"), ("slurm_account", "account"),
                    ("estimate_status", "estimate"), ("gross_cny", "gross"),
                    ("cash_before_credit_cny", "before_credit"), ("submit_time", "submitted"),
                    ("start_time", "started"), ("price_revision", "price_revision"))]
                lines += [self.t("observed", time=result.freshness.observed_at), f"{self.t('as_of')}: {result.as_of}",
                    f"{self.t('source')}: {result.freshness.source} · " + self.t("age", seconds=result.freshness.age_seconds)
                    + " · " + self.t("stale" if result.freshness.stale else "fresh"),
                    self.t("uncertainty") + ": " + (", ".join(item["uncertainty"]) or self.t("none_reported")),
                    self.t("snapshot_paused")]
                self.query_one("#details", Static).update("\n".join(lines))

    def _apply(self, *, partition: str | None = None, refresh: bool = True) -> bool:
        account = self.query_one("#account", Input).value.strip() or None
        by_id = self.query_one("#selector", Select).value == "id"
        try:
            query = replace(self.job_query, scope=str(self.query_one("#scope", Select).value),
                account_name=None if by_id else account, account_id=account if by_id else None,
                partition=partition if partition is not None else self.query_one("#partition", Input).value,
                states=clean_states(self.query_one("#states", Input).value)).validated()
        except SaiCliError as error:
            self.query_one("#status", Static).update(f"{self.t('invalid_filters')} · {error.code}")
            return False
        self.job_query = query
        self.selected_job = None
        self.job_mode = "detail"
        self.selected_estimate = None
        self._revision += 1
        for view in ("jobs", "usage"):
            self._clear(view)
        self.query_one("#partition", Input).value = query.partition or ""
        self._update_scope_display()
        if refresh:
            self.request_read()
        return True

    def _update_scope_display(self) -> None:
        if self.view == "resources":
            site = self.catalog.values["site_label"] if self.catalog is not None else self.job_query.site_id
            self.query_one("#context", Static).update(f"SAI · {site}\n{self.t('catalog_context')}")
            return
        if self.view == "tasks":
            project = self.tasks_workspace_label or (self.t("project_by_key", key=self.tasks_workspace_key)
                        if self.tasks_workspace_key else self.t("choose_project"))
            self.query_one("#context", Static).update(
                f"SAI · {self.job_query.site_id}\n{project}")
            return
        if self.view == "overview":
            self.query_one("#context", Static).update(f"SAI · {self.job_query.site_id}\n{self.t('overview_context')}")
            return
        if self.view == "storage":
            self.query_one("#context", Static).update(
                f"SAI · {self.job_query.site_id}\n{self.t('storage_context', workspace=self.storage_workspace_key or self.t('choose'))}"
            )
            return
        self.query_one("#context", Static).update(
            f"SAI · {self.job_query.site_id} · {self.job_query.cluster_id or self.t('default_cluster')}\n"
            + self.t("applied_scope", scope=self.t(self.job_query.scope),
                     account=self.job_query.account_name or self.job_query.account_id or self.t('self'))
            + f" · {self.t('partition')} {self.job_query.partition or self.t('all')}"
            + f" · {self.t('state')} {','.join(self.job_query.states) or self.t('all')}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in {"load-projects", "projects-first"}:
            self._read_projects()
        elif event.button.id == "projects-next" and self.task_projects is not None:
            self._read_projects(self.task_projects.values["next_cursor"])
        elif event.button.id == "task-back":
            self.action_back()
        elif event.button.id in {"task-detail", "task-stdout", "task-stderr", "task-files"}:
            self._inspect_task(event.button.id.removeprefix("task-"))
        elif event.button.id in {"task-start", "task-next"}:
            self._task_page(start=event.button.id == "task-start")
        elif event.button.id == "view-placement":
            self.action_view_placement()
        elif event.button.id in {"view-job", "view-allocation"}:
            if event.button.id == "view-allocation":
                self.action_view_allocation()
            else:
                self._inspect_job("detail")
        elif event.button.id in {"open-job-web", "open-task-web"}:
            self.action_open_web()
        elif event.button.id == "copy-web-link":
            self.action_copy_web_link()
        elif event.button.id == "overview-messages":
            result = self.results.get("overview")
            if isinstance(result, AccountOverview):
                self.open_url(result.messages_url(self.client.transport.base_url))
        elif event.button.id == "load-storage":
            self.storage_workspace_key = self.query_one("#storage-workspace", Input).value.strip() or None
            self._revision += 1
            self._clear("storage")
            self._update_scope_display()
            self.request_read()
        elif event.button.id == "apply":
            self._apply()
        elif event.button.id == "refresh":
            self.action_refresh()
        elif event.button.id == "prepare-resource":
            self.action_open_web()
        elif event.button.id == "compare-resource":
            self.action_compare_resource()
        elif event.button.id == "clear-comparison":
            self.compared.clear()
            self._comparison()
        elif event.button.id == "use-partition":
            candidate = self._resource_candidate()
            if candidate is not None and self._resource_preparation_url() is not None:
                self.job_query = replace(self.job_query, partition=candidate["name"]).validated()
                self.query_one("#partition", Input).value = self.job_query.partition
                self._clear("jobs")
                self.query_one("#views", TabbedContent).active = "jobs"
                self.query_one("#jobs-table", DataTable).focus()
        elif event.button.id in {"previous", "next"}:
            result = self.results.get("usage")
            if isinstance(result, RunningEstimateResult):
                self.selected_estimate = None
                self.usage_page = max(0, self.usage_page + (1 if event.button.id == "next" else -1))
                self._present("usage", result)

    def _discard_allocation(self) -> None:
        self._clear_placement()
        if isinstance(self.results.get("jobs"), SiteJobAllocationResult):
            self._clear("jobs")

    def _inspect_job(self, mode: str, *, row_key: str | None = None) -> None:
        result = self.results.get("jobs")
        selected = self.selected_job
        if isinstance(result, (JobResult, SiteJobResult)):
            table = self.query_one("#jobs-table", DataTable)
            if row_key is None and table.row_count:
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            if row_key is not None:
                selected = result.items[int(row_key)].canonical_id
        elif isinstance(result, SiteJobAllocationResult):
            selected = result.job.canonical_id
        if selected is None:
            self.query_one("#status", Static).update(self.t("select_job"))
            return
        if mode != "placement":
            self._discard_allocation()
        else:
            self._clear_placement()
        self.selected_job, self.job_mode = selected, mode
        self._revision += 1
        if mode == "placement" and isinstance(result, SiteJobAllocationResult):
            self._present("jobs", result)
        else:
            self.query_one("#details", Static).update("")
        self.request_read()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tasks-project" and self._workbench_ready:
            if isinstance(event.value, str) and event.value != self.tasks_workspace_key:
                self._apply_task_project(event.value)
            return
        if event.select.id != "storage-source" or not self._workbench_ready:
            return
        if event.value not in {"summary", "native"} or event.value == self.storage_source:
            return
        self.storage_source = event.value
        self._revision += 1
        self._clear("storage")
        if self.view == "storage":
            self.request_read()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "storage-workspace" or not self._workbench_ready:
            return
        if event.value.strip() == (self.storage_workspace_key or ""):
            return
        self.storage_workspace_key = None
        self._clear("storage")
        if self.view == "storage":
            self._revision += 1
            self._pending = False
            self._update_scope_display()
            self.query_one("#status", Static).update(self.t("storage_changed"))

    def action_refresh(self) -> None:
        self.selected_estimate = None
        if self.view == "tasks":
            self._revision += 1
            self._clear_task_files()
        if self.view == "jobs":
            self._revision += 1
            if self.job_mode == "placement":
                self._clear_placement()
                result = self.results.get("jobs")
                if isinstance(result, SiteJobAllocationResult):
                    self._present("jobs", result)
            if self.job_mode == "allocation":
                self._discard_allocation()
                self.query_one("#details", Static).update("")
        self.request_read()

    def action_pause(self) -> None:
        self.paused = not self.paused
        self.query_one("#status", Static).update(self.t("auto_paused" if self.paused else "auto_resumed"))
        if not self.paused:
            self.action_refresh()

    def action_back(self) -> None:
        if self.view == "tasks" and self.selected_run:
            self._revision += 1
            self._clear("tasks")
            self.task_cursor = self._task_list_cursor
            self.request_read()
            self.query_one("#tasks-table", DataTable).focus()
            return
        if self.selected_estimate is not None:
            self.selected_estimate = None
            self.query_one("#details", Static).update("")
            self.request_read()
        if self.selected_job:
            self._discard_allocation()
            self.selected_job = None
            self.job_mode = "detail"
            self._revision += 1
            self.query_one("#details", Static).update("")
            self.request_read()
