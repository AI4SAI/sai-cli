"""Optional terminal workbench over the existing authorized read client."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from rich.text import Text
from rich.table import Table
from rich.console import Group
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Input, Select, Static, TabbedContent, TabPane

from .catalog import ResourceCatalog
from .client import JobQuery, PortalClient, clean_states
from .contracts import JobResult, RunningEstimateResult
from .errors import AuthenticationError, ContractError, SaiCliError
from .render import render_storage_quota_summary, render_native_quota
from .native_quota import NativeQuotaResult
from .overview import AccountOverview
from .overview_view import overview_panel
from .site_jobs import SiteJobAllocationResult, SiteJobResult
from .storage_summary import StorageQuotaSummary


def display(value: object) -> str:
    """Catalog prose may contain line breaks; table cells remain single-line."""
    return "Unknown" if value is None else " ".join(str(value).split())


def allocation_panel(result: SiteJobAllocationResult) -> Group:
    job, freshness = result.job.values, result.freshness
    state = {
        "allocated": "Allocated",
        "not_allocated": "No nodes allocated in this observation",
        "unavailable": "Allocation unavailable for this observation",
    }[result.allocation_status]
    header = Text("\n".join((
        f"Job: {result.job.canonical_id} · {display(job['name'])}",
        f"State: {', '.join(result.scheduler_states)} · Restart count: {display(result.restart_count)}",
        f"Submitted UTC: {display(job['submit_time'])}",
        f"Started UTC: {display(job['start_time'])}",
        f"Source: {freshness.source} · Observed: {freshness.observed_at}",
        f"Age: {freshness.age_seconds}s · Stale: {freshness.stale}",
        state,
    )))
    table = Table(box=None, expand=True, padding=(0, 1))
    for column in ("Node", "Allocated CPUs", "Memory (MiB)"):
        table.add_column(column)
    for node in result.nodes or ():
        table.add_row(Text(node.name), Text(str(node.cpus)), Text(display(node.memory_mib)))
    hint = Text("Auto refresh paused while inspecting allocation. F5 reads a new snapshot; Esc returns.")
    return Group(header, table, hint) if result.nodes else Group(header, hint)


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
    #storage-scroll { height: 1fr; }
    #storage-summary { height: auto; }
    #overview-summary { height: auto; padding: 1 0; }
    .hint { height: auto; color: $text-muted; }
    .compact .controls { height: 1; }
    .compact .controls Input, .compact .controls Button,
    .compact .controls Select, .compact SelectCurrent { height: 1; border: none; padding: 0; }
    .compact TabbedContent { min-height: 8; }
    .compact #details-scroll { min-height: 3; }
    """
    BINDINGS = [
        Binding("f5", "refresh", "Refresh"),
        Binding("f6", "pause", "Pause / resume"),
        Binding("escape", "back", "Back to list"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self, client: PortalClient, query: JobQuery, *, refresh_seconds: int = 10,
        storage_workspace_key: str | None = None,
        overview_account: str | None = None,
        initial_view: str = "resources",
    ):
        super().__init__()
        self.client = client
        self.job_query = query.validated()
        self.refresh_seconds = refresh_seconds
        self.view = initial_view
        self.paused = False
        self.selected_job: str | None = None
        self.job_mode = "detail"
        self.selected_estimate: int | None = None
        self.compared: list[str] = []
        self.catalog: ResourceCatalog | None = None
        self.storage_workspace_key = (storage_workspace_key or "").strip() or None
        self.overview_account = overview_account
        self.storage_source = "summary"
        self.results: dict[str, object] = {}
        self._failed_views: set[str] = set()
        self.usage_page = 0
        self._revision = 0
        self._pending = False
        self._reading = False
        self._workbench_ready = False

    def compose(self) -> ComposeResult:
        yield Static(f"SAI  ·  {self.job_query.site_id}  ·  {self.job_query.cluster_id or 'default cluster'}", id="context", markup=False)
        with Horizontal(classes="controls", id="job-scope-controls"):
            yield Select([(s, s) for s in ("self", "personal-account", "org-account", "project-account")],
                         value=self.job_query.scope, allow_blank=False, id="scope")
            yield Select([("Name", "name"), ("ID", "id")], value="id" if self.job_query.account_id else "name",
                         allow_blank=False, id="selector")
            yield Input(self.job_query.account_name or self.job_query.account_id or "", placeholder="Account", id="account")
        with Horizontal(classes="controls", id="job-filter-controls"):
            yield Input(self.job_query.partition or "", placeholder="Partition", id="partition")
            yield Input(",".join(self.job_query.states), placeholder="States: R,PD", id="states")
            yield Button("Apply", id="apply", variant="primary")
            yield Button("Refresh", id="refresh")
        yield Static("Loading published resources…", id="status", markup=False)
        with TabbedContent(initial=self.view, id="views"):
            with TabPane("概览 / Overview", id="overview"):
                with VerticalScroll():
                    yield Static("加载当前身份摘要…", id="overview-summary", markup=False)
                    yield Button("打开控制台消息", id="overview-messages", disabled=True)
            with TabPane("Resources", id="resources"):
                yield Static("Enter selects up to two partitions to compare. Published capacity is not idle capacity.", classes="hint", markup=False)
                yield DataTable(id="resources-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button("View jobs", id="use-partition")
                    yield Button("Clear comparison", id="clear-comparison")
            with TabPane("Jobs", id="jobs"):
                yield Static(f"At most {self.job_query.limit} jobs. Enter opens authorized detail.", classes="hint", markup=False)
                yield DataTable(id="jobs-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button("View details", id="view-job")
                    yield Button("View allocation", id="view-allocation")
            with TabPane("Running estimates", id="usage"):
                yield Static("Non-final estimates. Published prices and final charges are separate.", classes="hint", markup=False)
                yield DataTable(id="usage-table", cursor_type="row")
                with Horizontal(classes="controls"):
                    yield Button("Previous", id="previous")
                    yield Button("Next", id="next")
            with TabPane("Storage", id="storage"):
                with Horizontal(classes="controls"):
                    yield Select([("Stored quota summary", "summary"), ("Native Lustre quota", "native")],
                                 value="summary", allow_blank=False, id="storage-source")
                with Horizontal(classes="controls"):
                    yield Input(self.storage_workspace_key or "", placeholder="Workspace key", id="storage-workspace")
                    yield Button("Load", id="load-storage", variant="primary")
                yield Static("Choose the source explicitly. Native quota shows authorized subjects, not the whole organization pool.",
                             classes="hint", markup=False)
                with VerticalScroll(id="storage-scroll"):
                    yield Static("Enter a workspace key and choose Load.", id="storage-summary", markup=False)
        with VerticalScroll(id="details-scroll"):
            yield Static("", id="details", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        for name, columns in {
            "resources": ("Partition / storage", "Kind", "CPU/node", "GPUs total", "Price"),
            "jobs": ("Job", "Name", "State", "Partition", "Reason / nodes"),
            "usage": ("Job", "State", "Estimate", "Gross CNY", "Before credit CNY"),
        }.items():
            self.query_one(f"#{name}-table", DataTable).add_columns(*columns)
        self._workbench_ready = True
        if self.view == "overview":
            for name in ("job-scope-controls", "job-filter-controls", "details-scroll"):
                self.query_one(f"#{name}").display = False
        self._update_scope_display()
        self.set_interval(self.refresh_seconds, self._tick)
        self.request_read()

    def on_resize(self) -> None:
        self.screen.set_class(self.size.height < 28, "compact")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if not self._workbench_ready:
            return
        view = event.pane.id or "resources"
        if view == self.view:
            return
        previous_view = self.view
        self._discard_allocation()
        self.view = view
        self.selected_job = None
        self.job_mode = "detail"
        self.selected_estimate = None
        self._revision += 1
        for name in ("job-scope-controls", "job-filter-controls", "details-scroll"):
            self.query_one(f"#{name}").display = view not in {"storage", "overview"}
        if view == "storage":
            self.query_one("#storage-workspace", Input).focus()
        elif view == "overview":
            self.query_one("#overview-summary", Static).scroll_visible()
        elif previous_view in {"storage", "overview"}:
            self.query_one(f"#{view}-table", DataTable).focus()
        self._update_scope_display()
        self.query_one("#details", Static).update("")
        self.request_read()

    def _tick(self) -> None:
        if (not self.paused and not self._reading and self.view not in self._failed_views
                and not (self.view == "usage" and self.selected_estimate is not None)
                and not (self.view == "jobs" and self.job_mode == "allocation" and self.selected_job is not None)):
            self.request_read()

    def request_read(self) -> None:
        if self.view == "storage" and self.storage_workspace_key is None:
            self.query_one("#status", Static).update("Choose a storage workspace, then Load.")
            return
        self._failed_views.discard(self.view)
        self._pending = True
        if not self._reading:
            self._reading = True
            self.run_worker(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while self._pending:
                self._pending = False
                revision, view, query, selected = self._revision, self.view, self.job_query, self.selected_job
                workspace = self.storage_workspace_key
                storage_source = self.storage_source
                job_mode = self.job_mode
                if view == "storage" and workspace is None:
                    continue
                context = workspace if view == "storage" else f"{query.scope} · {query.account_name or query.account_id or 'self'}"
                self.query_one("#status", Static).update(f"Refreshing {view} · {context}")
                try:
                    result = await asyncio.to_thread(self._fetch, view, query, selected, workspace, storage_source, job_mode)
                except SaiCliError as error:
                    if revision == self._revision:
                        self._read_error(view, error)
                except Exception:
                    if revision == self._revision:
                        self._read_error(view, ContractError("The view could not be loaded."))
                else:
                    if revision == self._revision:
                        self.results[view] = result
                        self._present(view, result)
        finally:
            self._reading = False

    def _fetch(self, view: str, query: JobQuery, selected: str | None, workspace: str | None,
               storage_source: str = "summary", job_mode: str = "detail"):
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
            if job_mode == "allocation":
                return self.client.job_allocation(selected, replace(query, partition=None))
            return self.client.show_job(selected, replace(query, partition=None))
        return self.client.list_jobs(query)

    def _clear(self, view: str) -> None:
        self.results.pop(view, None)
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
        if view == "usage":
            self.usage_page = 0
            self.selected_estimate = None
        if view == self.view:
            self.query_one("#details", Static).update("")

    def _read_error(self, view: str, error: SaiCliError) -> None:
        self._failed_views.add(view)
        if isinstance(error, AuthenticationError):
            for name in ("resources", "jobs", "usage", "storage", "overview"):
                self._clear(name)
            self.selected_job = None
            self.job_mode = "detail"
            self._revision += 1
            self._pending = False
            self.paused = True
        else:
            self._clear(view)
        self.query_one("#status", Static).update(f"{error.message} · {error.code} · Refresh to retry")

    def _rows(self, view: str, rows: list[tuple[str, tuple[object, ...]]]) -> None:
        table = self.query_one(f"#{view}-table", DataTable)
        previous = None
        if table.row_count:
            previous = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        table.clear()
        for key, values in rows:
            table.add_row(*(Text(display(value)) for value in values), key=key)
        if previous is not None and previous in [key for key, _ in rows]:
            table.move_cursor(row=table.get_row_index(previous))

    def _present(self, view: str, result: object) -> None:
        status = ""
        if view == "overview" and isinstance(result, AccountOverview):
            self.query_one("#overview-summary", Static).update(overview_panel(result, base_url=self.client.transport.base_url))
            self.query_one("#overview-messages", Button).disabled = False
            status = "当前身份摘要 · 消息展示不会标为已读"
        elif view == "storage" and isinstance(result, StorageQuotaSummary):
            self.query_one("#storage-summary", Static).update(render_storage_quota_summary(result))
            values = result.values
            status = f"Stored quota sample · {values['state']} · observed {display(values['observed_at'])}"
        elif view == "storage" and isinstance(result, NativeQuotaResult):
            self.query_one("#storage-summary", Static).update(render_native_quota(result))
            status = f"Native Lustre quota · queried {result.values['as_of']}"
        elif view == "resources" and isinstance(result, ResourceCatalog):
            self.catalog = result
            data = result.as_dict()
            rows = [(f"compute:{i}", (r["name"], r["resource_kind"], r["cpu_cores_per_node"], r["gpu_count"],
                    r["pricing"]["display"] if r["pricing"] else None)) for i, r in enumerate(data["compute"])]
            rows += [(f"storage:{i}", (r["name"], r["filesystem_type"], "—", "—", r["package_pricing"]["display"]))
                     for i, r in enumerate(data["storage"])]
            self._rows(view, rows)
            self.compared = [name for name in self.compared if any(r["name"] == name for r in data["compute"])]
            self._comparison()
            status = "Published specifications · refreshed" if rows else "No published resources at this site"
        elif isinstance(result, SiteJobAllocationResult):
            job, freshness = result.job, result.freshness
            self._rows("jobs", [("0", (job.canonical_id, *(job.values[k] for k in
                ("name", "state", "partition", "reason_or_nodelist"))))])
            self.query_one("#details", Static).update(allocation_panel(result))
            status = f"Allocation · {freshness.observed_at} · refresh paused"
        elif isinstance(result, (JobResult, SiteJobResult)):
            self._rows(view, [(str(i), (r.canonical_id, *(r.values[k] for k in
                ("name", "state", "partition", "reason_or_nodelist")))) for i, r in enumerate(result.items)])
            if self.selected_job:
                item = result.items[0].values if result.items else {}
                text = f"Job: {result.items[0].canonical_id}\n" + "\n".join(f"{label}: {display(item.get(key))}" for key, label in (
                    ("name", "Name"), ("state_label", "State"),
                    ("reason_or_nodelist", "Reason / nodes"), ("partition", "Partition"),
                    ("qos", "QOS"), ("slurm_user", "User"), ("slurm_account", "Account"),
                    ("nodes", "Nodes"), ("gpus_per_node", "GPU / node"), ("slots", "Slots"),
                    ("submit_time", "Submitted UTC"), ("start_time", "Started UTC"),
                    ("elapsed_seconds", "Elapsed seconds")))
                self.query_one("#details", Static).update(text)
            freshness = result.freshness
            if isinstance(result, SiteJobResult):
                status = (f"{freshness.source} · {freshness.observed_at} · age {freshness.age_seconds}s"
                          f" · {'STALE' if freshness.stale else 'observed'} · more: {result.has_more}")
            else:
                status = f"{freshness.source} · {freshness.queried_at} · at most {self.job_query.limit} jobs"
            if not result.items:
                status += " · No jobs in this scope"
        elif isinstance(result, RunningEstimateResult):
            self.usage_page = min(self.usage_page, max(0, (len(result.items) - 1) // 100))
            start = self.usage_page * 100
            visible = result.items[start:start + 100]
            self._rows(view, [(str(start + i), tuple(r.values[k] for k in
                ("job_id_raw", "state", "estimate_status", "gross_cny", "cash_before_credit_cny"))) for i, r in enumerate(visible)])
            status = (f"Non-final · as of {result.as_of} · {'STALE' if result.freshness.stale else 'observed'}"
                      f" · {len(result.items)} estimates · page {self.usage_page + 1} (local snapshot)")
            self.query_one("#previous", Button).disabled = self.usage_page == 0
            self.query_one("#next", Button).disabled = start + 100 >= len(result.items)
            self.query_one("#details", Static).update("Select an estimate to inspect its source and uncertainty.")
        self.query_one("#status", Static).update(status + (" · auto refresh paused" if self.paused else ""))

    def _comparison(self) -> None:
        if self.catalog is None:
            return
        rows = [r for name in self.compared for r in self.catalog.values["compute"] if r["name"] == name]
        if not rows:
            self.query_one("#details", Static).update("Select one or two partitions to compare published specifications.")
            return
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Specification")
        for row in rows:
            table.add_column(Text(row["title"]))
        for key, label in (("cpu_model", "CPU"), ("cpu_cores_per_node", "Cores / node"),
                           ("gpu_model", "GPU"), ("gpu_count", "GPUs total"), ("node_count", "Nodes")):
            table.add_row(Text(label), *(Text(display(row[key])) for row in rows))
        table.add_row(Text("QOS"), *(Text(", ".join(row["supported_qos"]) or "Unknown") for row in rows))
        table.add_row(Text("Published price"), *(Text(row["pricing"]["display"] if row["pricing"] else "Unknown") for row in rows))
        self.query_one("#details", Static).update(table)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if event.data_table.id == "resources-table" and self.catalog:
            kind, index = key.split(":")
            row = self.catalog.values[kind][int(index)]
            if kind == "compute":
                name = row["name"]
                if name in self.compared:
                    self.compared.remove(name)
                else:
                    self.compared = [*self.compared[-1:], name]
                self._comparison()
            else:
                self.query_one("#details", Static).update(
                    f"{row['name']} · {row['scope_label']}\n{row['description']}\n"
                    + "\n".join(f"{r['label']}: {r['value']}" for r in row["hardware"])
                    + f"\nPackage: {row['package_pricing']['display']}\nUsage: {row['usage_pricing']['display']}"
                    + f"\nMetered settlement enabled: {row['metered_settlement_enabled']}"
                )
        elif event.data_table.id == "jobs-table":
            self._inspect_job("detail", row_key=key)
        elif event.data_table.id == "usage-table":
            result = self.results.get("usage")
            if isinstance(result, RunningEstimateResult):
                self.selected_estimate = int(key)
                self._revision += 1
                self._pending = False
                item = result.items[self.selected_estimate].values
                lines = [f"{label}: {display(item[name])}" for name, label in (
                    ("job_id_raw", "Job"), ("slurm_account", "Account"),
                    ("estimate_status", "Estimate status"), ("gross_cny", "Gross CNY (non-final)"),
                    ("cash_before_credit_cny", "Before-credit CNY"), ("submit_time", "Submitted UTC"),
                    ("start_time", "Started UTC"), ("price_revision", "Price revision"))]
                lines += [f"Observed: {result.freshness.observed_at}", f"As of: {result.as_of}",
                    f"Source: {result.freshness.source} · age {result.freshness.age_seconds}s · stale {result.freshness.stale}",
                    "Uncertainty: " + (", ".join(item["uncertainty"]) or "None reported"),
                    "Auto refresh paused while inspecting this snapshot. Esc returns."]
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
            self.query_one("#status", Static).update(error.message)
            return False
        self.job_query = query
        self.selected_job = None
        self.job_mode = "detail"
        self.selected_estimate = None
        self._revision += 1
        for view in ("resources", "jobs", "usage"):
            self._clear(view)
        self.query_one("#partition", Input).value = query.partition or ""
        self._update_scope_display()
        if refresh:
            self.request_read()
        return True

    def _update_scope_display(self) -> None:
        if self.view == "overview":
            self.query_one("#context", Static).update(f"SAI · {self.job_query.site_id}\n默认工作身份 · 本人资金与未读消息")
            return
        if self.view == "storage":
            self.query_one("#context", Static).update(
                f"SAI · {self.job_query.site_id}\nStorage workspace: {self.storage_workspace_key or 'not selected'}"
            )
            return
        self.query_one("#context", Static).update(
            f"SAI · {self.job_query.site_id} · {self.job_query.cluster_id or 'default cluster'}\n"
            f"Applied: {self.job_query.scope} · {self.job_query.account_name or self.job_query.account_id or 'self'}"
            f" · partition {self.job_query.partition or 'all permitted'} · states {','.join(self.job_query.states) or 'all'}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in {"view-job", "view-allocation"}:
            self._inspect_job("allocation" if event.button.id == "view-allocation" else "detail")
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
        elif event.button.id == "clear-comparison":
            self.compared.clear()
            self._comparison()
        elif event.button.id == "use-partition" and self.compared:
            if self._apply(partition=self.compared[-1], refresh=False):
                self.query_one("#views", TabbedContent).active = "jobs"
                self.query_one("#jobs-table", DataTable).focus()
        elif event.button.id in {"previous", "next"}:
            result = self.results.get("usage")
            if isinstance(result, RunningEstimateResult):
                self.selected_estimate = None
                self.usage_page = max(0, self.usage_page + (1 if event.button.id == "next" else -1))
                self._present("usage", result)

    def _discard_allocation(self) -> None:
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
            self.query_one("#status", Static).update("Select a job to inspect.")
            return
        self._discard_allocation()
        self.selected_job, self.job_mode = selected, mode
        self._revision += 1
        self.query_one("#details", Static).update("")
        self.request_read()

    def on_select_changed(self, event: Select.Changed) -> None:
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
            self.query_one("#status", Static).update("Workspace changed. Choose Load to read its quota sample.")

    def action_refresh(self) -> None:
        self.selected_estimate = None
        if self.view == "jobs" and self.job_mode == "allocation":
            self._revision += 1
            self._discard_allocation()
            self.query_one("#details", Static).update("")
        self.request_read()

    def action_pause(self) -> None:
        self.paused = not self.paused
        self.query_one("#status", Static).update("Auto refresh paused. Existing data is not live." if self.paused else "Auto refresh resumed.")
        if not self.paused:
            self.action_refresh()

    def action_back(self) -> None:
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
