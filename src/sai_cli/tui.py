"""One native query at a time, with optional SAI business reads on demand."""
from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import time

from rich.text import Text
from textual import on
from textual.events import Resize
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Select, Static, Tab, Tabs

from .errors import AuthenticationError, SaiCliError
from .render import follow_up_command
from .tui_queries import Queries, Read


LABELS = {
    "zh-CN": {"jobs": "作业", "gpu": "GPU", "cpu": "CPU", "quota": "配额", "account": "账户",
        "mine": "我的作业", "identity": "当前身份", "all": "全部分区", "here": "当前目录", "home": "Home",
        "current": "当前账户", "refresh": "刷新", "cost": "费用", "quit": "退出",
        "pause": "暂停", "resume": "继续", "paused": "已暂停", "auto": "自动 {seconds}s", "allocated_total": "分配/总",
        "gpu_free": "GPU\n空闲/总", "gpu_slots": "GPU\n卡位", "cpu_count": "CPU\n分配/总", "memory": "GiB\n分配/总", "no_nodes": "当前分区没有节点", "node_name": "节点",
        "loading": "读取中…", "empty": "当前范围没有作业", "local": "本站", "central": "SAI 账户",
        "login": "账户查询需要登录：退出后运行 {command}", "failure": "读取失败，按 r 重试",
        "time": "运行 / 等待", "name": "名称", "state": "状态", "partition": "分区", "node": "节点 / 原因",
        "truncated": "仅显示前 500 条", "detail": "详情", "back": "返回", "snapshot": "更新", "read_only": "查看账户", "estimate_title": "预估费用 · 未结算", "standard_price": "标准价", "cash_price": "现金价", "unknown": "暂不可用", "stale": "旧观察，请刷新", "partial": "部分预估", "not_started": "尚未开始", "unavailable": "预估暂不可用"},
    "en-US": {"jobs": "Jobs", "gpu": "GPU", "cpu": "CPU", "quota": "Quota", "account": "Account",
        "mine": "My jobs", "identity": "Login account", "all": "All partitions", "here": "Working directory", "home": "Home",
        "current": "Current account", "refresh": "Refresh", "cost": "Estimate", "quit": "Quit",
        "pause": "Pause", "resume": "Resume", "paused": "Paused", "auto": "Auto {seconds}s", "allocated_total": "alloc/all",
        "gpu_free": "GPU\nfree/all", "gpu_slots": "GPU\nslots", "cpu_count": "CPU\nalloc/all", "memory": "GiB\nalloc/all", "no_nodes": "No nodes in this partition", "node_name": "Node",
        "loading": "Reading…", "empty": "No jobs in this scope", "local": "Local", "central": "SAI account",
        "login": "Sign in after exiting: {command}", "failure": "Read failed; press r to retry",
        "time": "Run / wait", "name": "Name", "state": "State", "partition": "Partition", "node": "Nodes / reason",
        "truncated": "First 500 jobs only", "detail": "Details", "back": "Back", "snapshot": "Updated", "read_only": "Viewing account", "estimate_title": "Estimate · not settled", "standard_price": "Standard", "cash_price": "Cash", "unknown": "Unavailable", "stale": "Stale observation; refresh", "partial": "Partial estimate", "not_started": "Not started", "unavailable": "Estimate unavailable"},
}


class QueryApp(App):
    TITLE = "SAI"
    ENABLE_COMMAND_PALETTE = False
    REFRESH_SECONDS = {"jobs": 5, "gpu": 10, "cpu": 10, "quota": 30, "account": 60}
    CSS = """
    Screen { background: ansi_default; color: ansi_default; }
    #heading { height: auto; max-height: 2; margin: 0 2; text-style: bold; }
    Tabs { margin: 0 1; }
    #controls { height: 3; margin: 0 1; }
    Select { width: 1fr; }
    #body { height: 1fr; margin: 0 2; }
    #job-table, #resource-table { height: 1fr; display: none; }
    DataTable { scrollbar-gutter: stable; }
    DataTable > .datatable--header { background: ansi_default; color: ansi_default; }
    DataTable:focus > .datatable--cursor { background: ansi_black; color: ansi_bright_white; }
    #job-context { height: auto; max-height: 5; margin-top: 1; display: none; }
    #answer { height: 1fr; }
    #body.resources #answer { height: auto; max-height: 4; }
    #content { height: auto; }
    #detail { height: auto; max-height: 60%; display: none; padding: 1 2; overflow-y: auto; }
    #detail.job-detail { height: 1fr; max-height: 100%; }
    #notice { height: auto; margin: 0 2; }
    Footer { background: $surface; }
    """
    BINDINGS = [Binding("1", "view('jobs')", show=False), Binding("2", "view('gpu')", show=False),
                Binding("3", "view('cpu')", show=False), Binding("4", "view('quota')", show=False),
                Binding("5", "view('account')", show=False)]

    def __init__(self, queries: Queries, *, language: str = "zh-CN", initial: str | None = None):
        super().__init__(ansi_color=True)
        self.theme = "ansi-dark"
        self.queries, self.words = queries, LABELS[language]
        self.language = language
        self.view = initial or queries.views[0]
        if self.view not in queries.views:
            from .errors import ConfigError
            raise ConfigError("This query needs its native Slurm or Lustre command on this host.")
        self.selection = "identity" if self.view == "jobs" and queries.account else ""
        self.snapshot = None
        self._version = 0
        self._pending: tuple[int, Read] | None = None
        self._reading = False
        self._active_request: Read | None = None
        self._job_ids: list[str] = []
        self._selected_job = None
        self._selected_node = None
        self._detail_node = None
        self._detail_request: Read | None = None
        self._detail_observed_at: str | None = None
        self._allocation_detail: dict | None = None
        self._expanded_allocation = False
        self._selections: dict[str, str] = {}
        self._native_accounts: list[str] = []
        self._discover_accounts = False
        self._last_read_at = time.monotonic()
        self._paused = False
        self._focus_after_read = False
        self._focus_before_read = None
        self._options: list[tuple[str, str]] = []
        self._bindings.bind("enter", "inspect", self.words["detail"], priority=True)
        for key in ("refresh", "cost", "back", "quit"):
            self.bind({"refresh": "r", "cost": "c", "back": "escape", "quit": "q"}[key], key, description=self.words[key])
        self.bind("p", "pause", description=self.words["pause"])
        self.bind("i", "allocation_details", description="硬件" if self.language == "zh-CN" else "Hardware")

    def compose(self) -> ComposeResult:
        yield Static("SAI", id="heading", markup=False)
        yield Tabs(*(Tab(self.words[view], id=view) for view in self.queries.views), active=self.view)
        with Horizontal(id="controls"):
            yield Select([(self.words["current"], "")], allow_blank=False, id="selection")
        with Vertical(id="body"):
            yield DataTable(id="job-table", cursor_type="row", zebra_stripes=True)
            yield DataTable(id="resource-table", cursor_type="row", zebra_stripes=True, header_height=2,
                            cursor_foreground_priority="renderable")
            yield Static(id="job-context", markup=False)
            with VerticalScroll(id="answer"):
                yield Static(id="content", markup=False)
        with VerticalScroll(id="detail"):
            yield Static(id="detail-content", markup=False)
        yield Static(id="notice", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_footer()
        self._configure()
        self.action_refresh()
        self.watch(self.query_one("#selection", Select), "expanded", self._selector_opened, init=False)
        self.set_interval(1, self._poll_current_view)

    def _poll_current_view(self) -> None:
        if not self.is_running:
            return
        if self._allocation_detail is not None:
            value = self._allocation_detail
            joined = value.get("interconnect")
            if joined and any(row["status"] == "recorded" and datetime.fromisoformat(
                    row["value"]["expires_at"].replace("Z", "+00:00")).timestamp() <= time.time()
                    for row in joined["nodes"]):
                from sai_native_topology import normalize_join
                from .allocation_view import allocation_view
                value["interconnect"] = normalize_join(joined, value["allocation"], cluster=value["cluster"])
                self._show_detail(allocation_view(value, language=self.language, expanded=self._expanded_allocation), focus=False)
        if self._reading or self._paused or len(self.screen_stack) > 1 or self.query_one("#selection", Select).expanded:
            return
        if self.view == "jobs" and self.query_one("#detail").display:
            return
        if time.monotonic() - self._last_read_at >= self.REFRESH_SECONDS[self.view]:
            self.action_refresh()

    def action_pause(self) -> None:
        self._paused = not self._paused
        self._refresh_footer()
        self.refresh_bindings()
        if self.snapshot is not None:
            self._stamp(self.snapshot.as_dict()["observed_at"])

    def action_allocation_details(self) -> None:
        if self._allocation_detail is not None and self.query_one("#detail").display:
            from .allocation_view import allocation_view
            self._expanded_allocation = not self._expanded_allocation
            self._refresh_footer()
            self._show_detail(allocation_view(self._allocation_detail, language=self.language,
                expanded=self._expanded_allocation), focus=False)
            self.query_one("#detail", VerticalScroll).scroll_home(animate=False)

    def _configure(self) -> None:
        w = self.words
        options = {
            "jobs": self._job_options(),
            "gpu": [(w["all"], "")] + ([(self.selection, self.selection)] if self.selection else []),
            "cpu": [(w["all"], "")] + ([(self.selection, self.selection)] if self.selection else []),
            "quota": self._quota_options(), "account": [(w["loading"], self.selection)],
        }[self.view]
        self._set_options(options, self.selection)
        self.query_one("#selection").disabled = self.view == "account"
        self.query_one("#job-table").display = self.view == "jobs"
        self.query_one("#resource-table").display = self.view in {"gpu", "cpu"}
        self.query_one("#body").set_class(self.view in {"gpu", "cpu"}, "resources")
        self.query_one("#answer").display = self.view != "jobs"
        self._close_detail(focus=False)
        self.query_one("#job-context").display = self.view == "jobs"
        self.query_one("#heading", Static).update(Text(f"SAI  ·  {w['central'] if self.view == 'account' else w['local']}"))
        if self.view in {"jobs", "gpu", "cpu"}:
            self.query_one("#job-table" if self.view == "jobs" else "#resource-table").focus()
        self.refresh_bindings()

    def _job_options(self) -> list[tuple[str, str]]:
        options = [(self.words["mine"], "mine")]
        if self.queries.account:
            options.append((self.words["identity"] + " · " + self.queries.account, "identity"))
        options += [(account, "account:" + account) for account in self._native_accounts if account != self.queries.account]
        if self.selection.startswith("account:") and self.selection not in {value for _, value in options}:
            options.append((self.selection.removeprefix("account:"), self.selection))
        return options

    def _quota_options(self) -> list[tuple[str, str]]:
        from .local_quota import _path_text
        options = [(self.words["here"], ""), (self.words["home"], "home")]
        if self.selection not in {"", "home"}:
            options.append((_path_text(self.selection), self.selection))
        options.append(("选择目录…" if self.language == "zh-CN" else "Choose directory…", "pick-directory"))
        return options

    def _selector_opened(self, expanded: bool) -> None:
        if expanded and self.view == "jobs":
            if self._reading:
                self._discover_accounts = True
            else:
                self._request(Read("job_accounts"))

    def _quota_directory_selected(self, path: str | None) -> None:
        if path is not None:
            self.selection = path
            self._set_options(self._quota_options(), path)
            self._clear_snapshot()
            self.action_refresh()

    def _set_options(self, options: list[tuple[str, str]], selected: str) -> None:
        widget = self.query_one("#selection", Select)
        with widget.prevent(Select.Changed):
            if options != self._options:
                widget.set_options([(Text(label), value) for label, value in options])
                self._options = options
                # Labels can change while the selected value stays the same.
                widget.mutate_reactive(Select.value)
            widget.value = selected if selected in {value for _, value in options} else options[0][1]
            self.selection = str(widget.value)

    @on(Tabs.TabActivated)
    def tab_changed(self, event: Tabs.TabActivated) -> None:
        if event.tab.id == self.view:
            return
        self._selections[self.view] = self.selection
        self.view = event.tab.id
        self.selection = self._selections.get(self.view, "identity" if self.view == "jobs" and self.queries.account else "")
        self.snapshot = None
        self._configure()
        self.action_refresh()

    @on(Select.Changed)
    def selection_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or event.value != event.select.value or event.value == self.selection:
            return
        if self.view == "quota" and event.value == "pick-directory":
            from .tui_directory import QuotaDirectory
            with event.select.prevent(Select.Changed):
                event.select.value = self.selection
            path = self.queries.home if self.selection == "home" else self.selection or self.queries.directory
            self.push_screen(QuotaDirectory(path, language=self.language), self._quota_directory_selected)
            return
        self.selection = str(event.value)
        self._close_detail(focus=False)
        if self.view in {"gpu", "cpu"} and self.snapshot is not None:
            self._render()
            self.query_one("#resource-table").focus()
        else:
            self._clear_snapshot()
            self.action_refresh()

    def action_view(self, view: str) -> None:
        if view in self.queries.views:
            self.query_one(Tabs).active = view

    def action_refresh(self) -> None:
        self._request(self._detail_request or Read(self.view, self.selection))

    def _clear_snapshot(self) -> None:
        self.snapshot = None
        self._job_ids = []
        for table in self.query(DataTable):
            with table.prevent(DataTable.RowHighlighted):
                table.clear()
        self.query_one("#content", Static).update("")
        self.query_one("#job-context", Static).update("")
        self._close_detail(focus=False)

    def _show_detail(self, content, *, focus: bool = True) -> None:
        self.query_one("#detail-content", Static).update(content)
        detail = self.query_one("#detail", VerticalScroll)
        detail.set_class(self.view == "jobs", "job-detail")
        detail.display = True
        self.query_one("#body").display = self.view != "jobs"
        self.query_one("#controls").display = self.view != "jobs"
        if self.view in {"gpu", "cpu"}:
            self.query_one("#answer").display = False
        if focus:
            detail.scroll_home(animate=False)
            detail.focus()
        self.refresh_bindings()

    def _close_detail(self, *, focus: bool = True) -> None:
        self._allocation_detail = None
        self._expanded_allocation = False
        self.query_one("#detail").display = False
        self.query_one("#body").display = True
        self.query_one("#controls").display = True
        self._detail_node = self._detail_request = self._detail_observed_at = None
        if self.view in {"gpu", "cpu"}:
            self.query_one("#answer").display = True
        if focus and self.view in {"jobs", "gpu", "cpu"}:
            self.query_one("#job-table" if self.view == "jobs" else "#resource-table").focus()
        self.refresh_bindings()

    def _request(self, request: Read) -> None:
        self._version += 1
        self._pending = self._version, request
        self._focus_after_read = self.snapshot is None
        self._focus_before_read = self.focused
        if self.snapshot is None:
            self._clear_snapshot()
        if request.view == "jobs":
            self._close_detail(focus=self.query_one("#detail").has_focus)
        if request.view in {"cost", "allocation"}:
            first_read = self._detail_request != request
            self._detail_request = request
            if first_read:
                self._allocation_detail = None
                self._expanded_allocation = False
                self._detail_observed_at = None
                self._show_detail(Text(request.job["item"].canonical_id + " · " + self.words["loading"]))
        self.refresh_bindings()
        if self.snapshot is None or request.view in {"job_accounts", "cost", "allocation"}:
            self.query_one("#notice", Static).update(self.words["loading"])
        if not self._reading:
            self._reading = True
            self.run_worker(self._drain(), exit_on_error=False)

    async def _drain(self) -> None:
        try:
            while self._pending is not None:
                version, request = self._pending
                self._pending = None
                self._active_request = request
                directory_ready = False
                try:
                    if request.view == "account":
                        directory = await self.queries.read(Read("accounts"))
                        if version != self._version:
                            continue
                        self._account_options(directory.values)
                        directory_ready = True
                    result = await self.queries.read(request)
                except Exception as exc:
                    if version == self._version and self._matches_job(request):
                        if request.view not in {"cost", "allocation", "job_accounts"}:
                            self._clear_snapshot()
                        if request.view == "account" and not directory_ready:
                            self._set_options([(self.words["current"], self.selection)], self.selection)
                            self.query_one("#selection").disabled = True
                        from .managed_runs import terminal_log
                        message = self.words["login"].format(command=follow_up_command(self.queries.args, "auth", "login")) if isinstance(exc, AuthenticationError) else (
                            exc.message if isinstance(exc, SaiCliError) else self.words["failure"])
                        error = Text(terminal_log(message), style="bold yellow")
                        if request.view in {"cost", "allocation"}:
                            self._allocation_detail = None
                            self.query_one("#notice", Static).update("")
                            self._show_detail(error, focus=False)
                        else:
                            self.query_one("#notice", Static).update(error)
                    continue
                if version != self._version or not self._matches_job(request):
                    continue
                self.query_one("#notice", Static).update("")
                if request.view == "job_accounts":
                    self._native_accounts = result.values["accounts"]
                    self._set_options(self._job_options(), self.selection)
                elif request.view == "cost":
                    self._detail_observed_at = result.freshness.observed_at
                    self._show_detail(self._cost_view(result), focus=False)
                    self._stamp(self.snapshot.observed_at)
                elif request.view == "allocation":
                    from .allocation_view import allocation_view
                    self._detail_observed_at = result.as_dict()["observed_at"]
                    self._allocation_detail = result.as_dict()
                    self._show_detail(allocation_view(self._allocation_detail, language=self.language,
                        expanded=self._expanded_allocation), focus=False)
                    self._stamp(self.snapshot.observed_at)
                else:
                    if request.view == "account":
                        self._account_options(directory.values, overview=result.values)
                    self.snapshot = result
                    self._render()
                    if self._focus_after_read and self.focused is self._focus_before_read:
                        if self.view in {"jobs", "gpu", "cpu"}:
                            self.query_one("#job-table" if self.view == "jobs" else "#resource-table").focus()
        finally:
            self._reading = False
            self._active_request = None
            self._last_read_at = time.monotonic()
            if self._discover_accounts:
                self._discover_accounts = False
                if self.view == "jobs" and self.query_one("#selection", Select).expanded:
                    self._request(Read("job_accounts"))

    def _account_options(self, directory: dict, *, overview: dict | None = None) -> None:
        options = [(row["name"], row["name"]) for row in directory["choices"]]
        if overview is not None and overview["context"]["state"] == "available":
            self.selection = overview["context"]["slurm_account"]
        if self.selection not in {value for _, value in options}:
            options.insert(0, (self.selection or self.words["current"], self.selection))
        self._set_options(options, self.selection)
        self.query_one("#selection").disabled = False

    def _matches_job(self, request: Read) -> bool:
        return request.view not in {"cost", "allocation"} or request.job["item"].canonical_id == self._selected_job

    def _render(self) -> None:
        if self.snapshot is None:
            return
        if self.view == "jobs":
            self._render_jobs()
            return
        if self.view in {"gpu", "cpu"}:
            self._render_resources()
            return
        elif self.view == "quota":
            from .tui_quota import quota_view
            body = quota_view(self.snapshot, language=self.language)
        else:
            from .overview_view import overview_panel
            body = overview_panel(self.snapshot, language=self.language)
        self.query_one("#content", Static).update(body)
        self._stamp(self.snapshot.as_dict()["observed_at"])

    def _render_jobs(self) -> None:
        from .render import _duration
        table = self.query_one("#job-table", DataTable)
        selected = self._selected_job
        scroll = table.scroll_offset
        cursor = table.cursor_row
        table.clear(columns=True)
        self._job_ids = [item.canonical_id for item in self.snapshot.items]
        wide = self.size.width >= 80
        table.add_column("Job", width=12 if wide else 10)
        table.add_column(self.words["state"], width=4)
        table.add_column(self.words["name"], width=max(8, self.size.width - (64 if wide else 30)))
        if wide:
            table.add_column(self.words["time"], width=14)
            table.add_column(self.words["partition"], width=16)
        for item in self.snapshot.items:
            row = item.values
            cells = [item.canonical_id, row["state"], row["name"] or "—"]
            if wide:
                cells += [_duration(row["run_wait_seconds"]), row["partition"] or "—"]
            table.add_row(*(Text(str(value)) for value in cells), key=item.canonical_id)
        if self._job_ids:
            table.move_cursor(row=self._job_ids.index(selected) if selected in self._job_ids else min(cursor, len(self._job_ids) - 1), scroll=False)
            self._selected_job = self._job_ids[table.cursor_row]
        else:
            self._selected_job = None
        table.scroll_to(scroll.x, scroll.y, animate=False, force=True)
        self._job_context()
        self.query_one("#notice", Static).update(self.words["empty"] if not self._job_ids else (
            self.words["truncated"] if self.snapshot.has_more else ""))
        self._stamp(self.snapshot.observed_at)
        self.refresh_bindings()

    def _job_context(self) -> None:
        from .tui_jobs import job_context
        item = next((item for item in self.snapshot.items if item.canonical_id == self._selected_job), None)
        self.query_one("#job-context", Static).update(job_context(item, language=self.language) if item else "")

    def _resource_nodes(self) -> list[dict]:
        if self.snapshot is None:
            return []
        return [node for node in self.snapshot.values["nodes"]
                if not self.selection or self.selection in node["partitions"]]

    def _resource_parts(self) -> list[dict]:
        return [part for part in self.snapshot.values["partitions"]
                if not self.selection or part["name"] == self.selection]

    def _render_resources(self) -> None:
        from .tui_resources import node_cells, node_detail, compact_summary
        from rich.console import Group
        from rich.table import Table
        values = self.snapshot.as_dict()
        options = [(self.words["all"], "")] + [(part["name"], part["name"]) for part in values["partitions"]]
        if self.selection and self.selection not in {value for _, value in options}:
            options.append((self.selection, self.selection))
        self._set_options(options, self.selection)
        nodes = self._resource_nodes()
        parts = self._resource_parts()
        if self.selection and parts:
            values = {**values, "nodes": nodes, "partitions": parts, "summary": parts[0]["summary"]}
        table = self.query_one("#resource-table", DataTable)
        scroll, cursor = table.scroll_offset, table.cursor_row
        table.clear(columns=True)
        width = max(24, table.size.width - table.styles.scrollbar_size_vertical)
        name_width = max(6, width // 6)
        state_width = 8 if width >= 64 else 4
        partition_width = max(12, width // 6) if not self.selection and width >= 80 else 0
        remaining = width - name_width - state_width - partition_width - (10 if partition_width else 8)
        data_width = max(6, remaining // 2)
        labels = ("gpu_free", "gpu_slots") if self.view == "gpu" else ("cpu_count", "memory")
        sizes = (min(data_width, 10), remaining - min(data_width, 10)) if self.view == "gpu" else (data_width, data_width)
        columns = [("node_name", name_width), ("state", state_width)]
        if partition_width:
            columns.append(("partition", partition_width))
        if width < 60:
            columns = [("node_name", (width - 4) // 2), ("gpu_free" if self.view == "gpu" else "allocated_total", (width - 4) // 2)]
        else:
            columns += list(zip(labels, sizes))
        for label, size in columns:
            table.add_column(self.words[label], width=size)
        for node in nodes:
            cells = node_cells(node, parts, kind=self.view, width=width)
            if width < 60:
                name = Text.assemble(cells[0], "\n", cells[1])
                if not self.selection:
                    name.append("\n" + ", ".join(node["partitions"]), style="dim")
                if self.view == "gpu":
                    metrics = Group(cells[2], cells[3])
                else:
                    metrics = Table.grid(padding=(0, 1))
                    metrics.add_row("CPU", cells[2])
                    metrics.add_row("GiB", cells[3])
                cells = [name, metrics]
            elif partition_width:
                cells.insert(2, Text(", ".join(node["partitions"])))
            elif not self.selection:
                cells[0].append("\n" + ", ".join(node["partitions"]), style="dim")
            table.add_row(*cells, key=node["name"], height=None)
        names = [node["name"] for node in nodes]
        if names:
            table.move_cursor(row=names.index(self._selected_node) if self._selected_node in names else min(cursor, len(names) - 1), scroll=False)
            self._selected_node = names[table.cursor_row]
        else:
            self._selected_node = None
        table.scroll_to(scroll.x, scroll.y, animate=False, force=True)
        summary = compact_summary(values, self.view, self.language)
        self.query_one("#content", Static).update(summary if nodes else "")
        self.query_one("#notice", Static).update("" if nodes else self.words["no_nodes"])
        if self._detail_node in names:
            node = nodes[names.index(self._detail_node)]
            self.query_one("#detail-content", Static).update(node_detail(node, parts, language=self.language, width=width))
        elif self._detail_node is not None:
            self._detail_node = None
            self.query_one("#detail").display = False
        self.query_one("#answer").display = self._detail_node is None
        self._stamp(self.snapshot.as_dict()["observed_at"])
        self.refresh_bindings()

    @on(DataTable.RowHighlighted, "#resource-table")
    def highlight_node(self, event: DataTable.RowHighlighted) -> None:
        table = self.query_one("#resource-table", DataTable)
        if table.row_count == 0 or event.row_key != table.coordinate_to_cell_key(table.cursor_coordinate).row_key:
            return
        if event.row_key.value != self._selected_node:
            self._selected_node = event.row_key.value
            self._detail_node = None
            self.query_one("#detail").display = False
            self.query_one("#answer").display = True

    @on(DataTable.RowSelected, "#resource-table")
    def resource_details(self, event: DataTable.RowSelected) -> None:
        from .tui_resources import node_detail
        node = next((node for node in self._resource_nodes() if node["name"] == event.row_key.value), None)
        if node is not None:
            self._detail_node = node["name"]
            self._show_detail(node_detail(node, self._resource_parts(), language=self.language, width=max(36, self.size.width - 4)))

    def _stamp(self, value: str) -> None:
        value = self._detail_observed_at or value
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        source = self.words["central"] if self.view == "account" else self.words["local"]
        cluster = getattr(self.snapshot, "cluster", None) or self.snapshot.as_dict().get("cluster")
        context = " · " + cluster if cluster else ""
        paused = self._paused or (self.view == "jobs" and self.query_one("#detail").display)
        context += " · " + (self.words["paused"] if paused else self.words["auto"].format(seconds=self.REFRESH_SECONDS[self.view]))
        self.query_one("#heading", Static).update(Text(f"SAI  ·  {source}{context}  ·  {stamp}"))

    def on_resize(self, event: Resize) -> None:
        if self.is_mounted:
            self._refresh_footer(width=event.size.width)
            self.call_after_refresh(self._render)

    def _refresh_footer(self, *, width: int | None = None) -> None:
        compact = (self.size.width if width is None else width) < 60
        self.query_one(Footer).compact = compact
        if self.language == "zh-CN":
            hardware = "收起" if self._expanded_allocation else "硬件"
        elif compact:
            hardware = "Less" if self._expanded_allocation else "More"
        else:
            hardware = "Collapse" if self._expanded_allocation else "Hardware"
        labels = {"enter": "Open" if compact and self.language == "en-US" else self.words["detail"],
                  "c": "Cost" if compact and self.language == "en-US" else self.words["cost"],
                  "i": hardware, "p": self.words["resume" if self._paused else "pause"]}
        for key, label in labels.items():
            # Textual.bind appends alternatives; update our existing binding.
            bindings = self._bindings.get_bindings_for_key(key)
            bindings[:] = [replace(binding, description=label) for binding in bindings]
        self.refresh_bindings()

    @on(DataTable.RowHighlighted, "#job-table")
    def highlight(self, event: DataTable.RowHighlighted) -> None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count == 0 or event.row_key != table.coordinate_to_cell_key(table.cursor_coordinate).row_key:
            return
        if event.row_key.value != self._selected_job:
            self._selected_job = event.row_key.value
            self._close_detail(focus=False)
            self._job_context()
            pending_cost = self._pending is not None and self._pending[1].view in {"cost", "allocation"}
            active_cost = self._active_request is not None and self._active_request.view in {"cost", "allocation"}
            if pending_cost or (active_cost and self._pending is None):
                self._version += 1
                self._pending = None
                self.query_one("#notice", Static).update("")

    @on(DataTable.RowSelected, "#job-table")
    def details(self, event: DataTable.RowSelected) -> None:
        if self.snapshot is None:
            return
        item = next(item for item in self.snapshot.items if item.canonical_id == event.row_key.value)
        if "[" in item.canonical_id:
            from .allocation_view import allocation_view
            self._show_detail(allocation_view({"job": item.as_dict(),
                "allocation": {"status": "not_allocated" if item.values["state"] == "PD" else "unavailable", "nodes": []}},
                language=self.language))
            self._stamp(self.snapshot.observed_at)
            return
        self._request(Read("allocation", self.selection, {"cluster": self.snapshot.cluster, "item": item}))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "allocation_details":
            return self._allocation_detail is not None and self.query_one("#detail").has_focus
        if action == "inspect":
            table = self.query("#resource-table" if self.view in {"gpu", "cpu"} else "#job-table")
            return bool(table) and table.first().has_focus and self.snapshot is not None and table.first().row_count > 0
        if action == "cost":
            return self.view == "jobs" and self.snapshot is not None and bool(self._job_ids) and (
                self.query_one("#job-table").has_focus or self.query_one("#detail").has_focus)
        if action == "back":
            return self.query_one("#detail").display or self.query_one("#selection", Select).expanded
        if action == "pause":
            return not (self.view == "jobs" and self.query_one("#detail").display)
        return True

    def action_inspect(self) -> None:
        self.query_one("#resource-table" if self.view in {"gpu", "cpu"} else "#job-table", DataTable).action_select_cursor()

    def action_cost(self) -> None:
        if self.view != "jobs" or self.snapshot is None or not self._job_ids:
            return
        table = self.query_one("#job-table", DataTable)
        item = self.snapshot.items[table.cursor_row]
        self._request(Read("cost", self.selection, {"cluster": self.snapshot.cluster, "item": item}))

    def _cost_view(self, result):
        from rich.console import Group
        from rich.table import Table
        from .render import format_decimal
        value = result.estimate.values
        grid = Table.grid(padding=(0, 2))
        for label, field in ((self.words["standard_price"], "gross_cny"), (self.words["cash_price"], "cash_before_credit_cny")):
            amount = value[field]
            grid.add_row(Text(label), Text(self.words["unknown"] if amount is None else "¥" + format_decimal(amount), style="bold"))
        identity = f"{value['job_id_raw']} · {value['slurm_account']}"
        title = self.words["estimate_title"]
        if value["estimate_status"] != "estimated":
            title += " · " + self.words[value["estimate_status"]]
        return Group(Text(title, style="bold"), Text(identity), grid,
                     Text(self.words["stale"] if result.freshness.stale else result.freshness.observed_at))

    def action_back(self) -> None:
        if self.query_one("#selection", Select).expanded:
            self.query_one("#selection", Select).expanded = False
        elif self.query_one("#detail").display:
            self._version += 1
            self._pending = None
            self._close_detail()
            if self.snapshot is not None:
                self._stamp(self.snapshot.as_dict()["observed_at"])
        else:
            self.exit()
