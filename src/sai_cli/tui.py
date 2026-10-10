"""One native query at a time, with optional SAI business reads on demand."""
from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Select, Static, Tab, Tabs

from .errors import AuthenticationError, SaiCliError
from .tui_queries import Queries, Read


LABELS = {
    "zh-CN": {"jobs": "作业", "gpu": "GPU", "cpu": "CPU", "quota": "配额", "account": "账户",
        "mine": "我的作业", "identity": "当前身份", "all": "全部分区", "here": "当前目录", "home": "Home",
        "current": "登录账户", "choose": "选择账户", "refresh": "刷新", "cost": "费用", "quit": "退出",
        "loading": "读取中…", "empty": "当前范围没有作业", "local": "本站", "central": "SAI 账户",
        "login": "账户查询需要登录：退出后运行 sai auth login", "failure": "读取失败，按 r 重试",
        "time": "运行 / 等待", "name": "名称", "state": "状态", "partition": "分区", "node": "节点 / 原因",
        "truncated": "仅显示前 500 条", "detail": "详情", "back": "返回", "snapshot": "更新", "read_only": "查看账户", "estimate_title": "预估费用 · 未结算", "standard_price": "标准价", "cash_price": "现金价", "unknown": "暂不可用", "stale": "旧观察，请刷新", "partial": "部分预估", "not_started": "尚未开始", "unavailable": "预估暂不可用"},
    "en-US": {"jobs": "Jobs", "gpu": "GPU", "cpu": "CPU", "quota": "Quota", "account": "Account",
        "mine": "My jobs", "identity": "Login account", "all": "All partitions", "here": "Working directory", "home": "Home",
        "current": "Login account", "choose": "Choose account", "refresh": "Refresh", "cost": "Estimate", "quit": "Quit",
        "loading": "Reading…", "empty": "No jobs in this scope", "local": "Local", "central": "SAI account",
        "login": "Sign in after exiting: sai auth login", "failure": "Read failed; press r to retry",
        "time": "Run / wait", "name": "Name", "state": "State", "partition": "Partition", "node": "Nodes / reason",
        "truncated": "First 500 jobs only", "detail": "Details", "back": "Back", "snapshot": "Updated", "read_only": "Viewing account", "estimate_title": "Estimate · not settled", "standard_price": "Standard", "cash_price": "Cash", "unknown": "Unavailable", "stale": "Stale observation; refresh", "partial": "Partial estimate", "not_started": "Not started", "unavailable": "Estimate unavailable"},
}


class QueryApp(App):
    TITLE = "SAI"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: ansi_default; color: ansi_default; }
    #heading { height: 1; margin: 1 2 0 2; text-style: bold; }
    Tabs { margin: 0 1; }
    #controls { height: 3; margin: 0 1; }
    Select { width: 1fr; }
    #choose { width: auto; min-width: 12; display: none; }
    #body { height: 1fr; margin: 0 2; }
    #job-table { height: 1fr; display: none; }
    #answer { height: 1fr; }
    #content { height: auto; }
    #detail { height: auto; max-height: 45%; display: none; padding: 1 2; overflow-y: auto; }
    #notice { height: auto; max-height: 3; margin: 0 2; }
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

    def compose(self) -> ComposeResult:
        yield Static("SAI", id="heading", markup=False)
        yield Tabs(*(Tab(self.words[view], id=view) for view in self.queries.views), active=self.view)
        with Horizontal(id="controls"):
            yield Select([(self.words["current"], "")], allow_blank=False, id="selection")
            yield Button(self.words["choose"], id="choose")
        with Horizontal(id="body"):
            yield DataTable(id="job-table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="answer"):
                yield Static(id="content", markup=False)
        with VerticalScroll(id="detail"):
            yield Static(id="detail-content", markup=False)
        yield Static(id="notice", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._bindings.bind("enter", "inspect", self.words["detail"], priority=True)
        for key in ("refresh", "cost", "back", "quit"):
            self.bind({"refresh": "r", "cost": "c", "back": "escape", "quit": "q"}[key], key, description=self.words[key], show=key != "back")

        self._configure()
        self.action_refresh()

    def _configure(self) -> None:
        w = self.words
        options = {
            "jobs": [(w["mine"], "mine")] + ([(w["identity"] + " · " + self.queries.account, "identity")] if self.queries.account else []),
            "gpu": [(w["all"], "")], "cpu": [(w["all"], "")],
            "quota": [(w["here"], ""), (w["home"], "home")], "account": [(w["current"], "")],
        }[self.view]
        self._set_options(options, self.selection)
        self.query_one("#choose").display = self.view == "account"
        self.query_one("#job-table").display = self.view == "jobs"
        self.query_one("#answer").display = self.view != "jobs"
        self.query_one("#detail").display = False
        self.query_one("#heading", Static).update(Text(f"SAI  ·  {w['central'] if self.view == 'account' else w['local']}"))
        self.refresh_bindings()

    def _set_options(self, options: list[tuple[str, str]], selected: str) -> None:
        widget = self.query_one("#selection", Select)
        with widget.prevent(Select.Changed):
            widget.set_options([(Text(label), value) for label, value in options])
            widget.value = selected if selected in {value for _, value in options} else options[0][1]
            self.selection = str(widget.value)

    @on(Tabs.TabActivated)
    def tab_changed(self, event: Tabs.TabActivated) -> None:
        if event.tab.id == self.view:
            return
        self.view = event.tab.id
        self.selection = "identity" if self.view == "jobs" and self.queries.account else ""
        self.snapshot = None
        self._configure()
        self.action_refresh()

    @on(Select.Changed)
    def selection_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or event.value != event.select.value or event.value == self.selection:
            return
        self.selection = str(event.value)
        if self.view in {"gpu", "cpu"} and self.snapshot is not None:
            self._render()
        else:
            self.action_refresh()

    @on(Button.Pressed, "#choose")
    def choose_account(self) -> None:
        self._request(Read("accounts"))

    def action_view(self, view: str) -> None:
        if view in self.queries.views:
            self.query_one(Tabs).active = view

    def action_refresh(self) -> None:
        self._request(Read(self.view, self.selection))

    def _request(self, request: Read) -> None:
        self._version += 1
        self._pending = self._version, request
        if request.view not in {"cost", "accounts"}:
            self.snapshot = None
            self.query_one("#job-table", DataTable).clear()
            self.query_one("#content", Static).update("")
            self.query_one("#detail").display = False
        if request.view == "cost":
            self.query_one("#detail-content", Static).update("")
            self.query_one("#detail").display = False
        self.refresh_bindings()
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
                try:
                    result = await self.queries.read(request)
                except Exception as exc:
                    if version == self._version and self._matches_job(request):
                        message = self.words["login"] if isinstance(exc, AuthenticationError) else (
                            exc.message if isinstance(exc, SaiCliError) else self.words["failure"])
                        self.query_one("#notice", Static).update(Text(message, style="bold yellow"))
                    continue
                if version != self._version or not self._matches_job(request):
                    continue
                self.query_one("#notice", Static).update("")
                if request.view == "accounts":
                    self._set_options([(self.words["current"], "")] + [(row["name"], row["name"]) for row in result.values["choices"]], self.selection)
                    self.query_one("#selection").focus()
                    self.query_one("#selection", Select).action_show_overlay()
                elif request.view == "cost":
                    self.query_one("#detail-content", Static).update(self._cost_view(result))
                    self.query_one("#detail").display = True
                else:
                    self.snapshot = result
                    self._render()
        finally:
            self._reading = False
            self._active_request = None

    def _matches_job(self, request: Read) -> bool:
        return request.view != "cost" or request.job["item"].canonical_id == self._selected_job

    def _render(self) -> None:
        if self.snapshot is None:
            return
        if self.view == "jobs":
            self._render_jobs()
            return
        if self.view in {"gpu", "cpu"}:
            from .local_resources import LocalResources
            from .native_resource_view import resource_view
            values = self.snapshot.as_dict()
            self._set_options([(self.words["all"], "")] + [(row["name"], row["name"]) for row in values["partitions"]], self.selection)
            if self.selection:
                part = next(row for row in values["partitions"] if row["name"] == self.selection)
                values = {**values, "partitions": [part], "nodes": [row for row in values["nodes"] if self.selection in row["partitions"]], "summary": part["summary"]}
            body = resource_view(LocalResources(values), details=True, width=max(36, self.size.width - 4))
        elif self.view == "quota":
            from .local_quota import render_local_quota
            body = Text(render_local_quota(self.snapshot, width=max(36, self.size.width - 4)))
        else:
            from .overview_view import overview_panel
            body = overview_panel(self.snapshot, language=self.language)
        self.query_one("#content", Static).update(body)
        self._stamp(self.snapshot.as_dict()["observed_at"])

    def _render_jobs(self) -> None:
        from .render import _duration
        table = self.query_one("#job-table", DataTable)
        selected = self._selected_job
        table.clear(columns=True)
        self._job_ids = [item.canonical_id for item in self.snapshot.items]
        wide = self.size.width >= 80
        table.add_column("Job", width=12 if wide else 10)
        table.add_column(self.words["state"], width=4)
        table.add_column(self.words["name"], width=max(10, self.size.width - (61 if wide else 26)))
        if wide:
            table.add_column(self.words["time"], width=14)
            table.add_column(self.words["partition"], width=16)
        for item in self.snapshot.items:
            row = item.values
            cells = [item.canonical_id, row["state"], row["name"] or "—"]
            if wide:
                cells += [_duration(row["run_wait_seconds"]), row["partition"] or "—"]
            table.add_row(*(Text(str(value)) for value in cells), key=item.canonical_id)
        if selected in self._job_ids:
            table.move_cursor(row=self._job_ids.index(selected))
        self.query_one("#notice", Static).update(self.words["empty"] if not self._job_ids else (
            self.words["truncated"] if self.snapshot.has_more else ""))
        self._stamp(self.snapshot.observed_at)
        table.focus()
        self.refresh_bindings()

    def _stamp(self, value: str) -> None:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        source = self.words["central"] if self.view == "account" else self.words["local"]
        cluster = getattr(self.snapshot, "cluster", None) or self.snapshot.as_dict().get("cluster")
        context = " · " + cluster if cluster else ""
        self.query_one("#heading", Static).update(Text(f"SAI  ·  {source}{context}  ·  {stamp}"))

    def on_resize(self) -> None:
        if self.is_mounted:
            self._render()

    @on(DataTable.RowHighlighted)
    def highlight(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value != self._selected_job:
            self._selected_job = event.row_key.value
            self.query_one("#detail").display = False
            pending_cost = self._pending is not None and self._pending[1].view == "cost"
            active_cost = self._active_request is not None and self._active_request.view == "cost"
            if pending_cost or (active_cost and self._pending is None):
                self._version += 1
                self._pending = None
                self.query_one("#notice", Static).update("")

    @on(DataTable.RowSelected)
    def details(self, event: DataTable.RowSelected) -> None:
        if self.snapshot is None:
            return
        row = next(item.values for item in self.snapshot.items if item.canonical_id == event.row_key.value)
        fields = [("Job", event.row_key.value), (self.words["name"], row["name"]), (self.words["account"], row["slurm_account"]),
                  (self.words["partition"], row["partition"]), (self.words["node"], row["reason_or_nodelist"])]
        self.query_one("#detail-content", Static).update(Text("\n".join(f"{label}  {value or '—'}" for label, value in fields)))
        self.query_one("#detail").display = True

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "inspect":
            table = self.query("#job-table")
            return bool(table) and table.first().has_focus and self.snapshot is not None and bool(self._job_ids)
        if action == "cost":
            return self.view == "jobs" and self.snapshot is not None and bool(self._job_ids)
        return True

    def action_inspect(self) -> None:
        self.query_one("#job-table", DataTable).action_select_cursor()

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
            self.query_one("#detail").display = False
        else:
            self.exit()
