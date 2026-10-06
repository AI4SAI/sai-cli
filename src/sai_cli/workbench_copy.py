"""Everyday workbench language and presentation, without protocol decisions."""
from dataclasses import dataclass
from datetime import datetime

from rich.text import Text

from .contracts import short_job_state
from .managed_runs import terminal_log
from .tui_messages import Messages


COPY = {
    "home": ("我的工作", "My work"), "scoped_home": ("工作", "Work"),
    "live": ("正在进行", "In progress"), "scoped_live": ("当前范围的活动", "Activity in this account"),
    "recent": ("最近工作", "Recent work"), "open": ("打开", "Open"),
    "view_status": ("查看状态", "View status"),
    "more": ("更多", "More"), "work": ("这项工作", "This work"),
    "loading": ("正在读取…", "Loading…"), "results": ("查看结果", "View results"),
    "result_title": ("结果", "Results"), "logs": ("查看运行记录", "Read activity"),
    "stdout": ("运行记录", "Activity"), "stderr": ("错误记录", "Error log"),
    "evidence": ("详细信息", "Details"), "run": ("工作状态", "Work status"),
    "native": ("当前状态", "Current status"),
    "empty": ("这里还没有你的工作。\n准备开始一项计算，或稍后回来查看。", "No work here yet.\nPrepare a computation, or return later."),
    "no_live": ("当前没有进行中的计算", "No computations in progress"),
    "no_recent": ("还没有可查看的工作记录", "No work records yet"),
    "start": ("开始一项工作", "Start work"),
    "catalog": ("选择计算资源", "Choose compute resources"),
    "catalog_hint": ("选择适合你的资源，再到 Pilot 准备计算。", "Choose resources, then prepare your computation in Pilot."),
    "catalog_empty": ("本站暂时没有发布可选计算资源。", "No compute resources are published here yet."),
    "storage_empty": ("目前没有可查看的存储空间。", "No readable storage is available now."),
    "prepare": ("在 Pilot 中准备", "Prepare in Pilot"),
    "begin_hint": ("已选站点会保留，打开网页后再确认计算方案。", "Your site choice is kept. Review the computation in the browser."),
    "files_empty": ("这里暂时没有输出文件。可以查看运行记录。", "No output files here yet. You can read the activity log."),
    "files_hint": ("选择文件阅读，或保存到当前主机", "Choose a file to read or save on this host"),
    "native_hint": ("可查看当前状态与使用的资源。\n这项计算尚未关联可读取的结果。", "Current state and allocated resources are available.\nReadable results have not been linked to this computation."),
    "run_hint": ("查看运行记录，或检查已经产生的结果。", "Read the activity log or inspect available results."),
    "completed_hint": ("计算已结束，正在读取结果。", "Computation finished. Reading its results."),
    "failed_hint": ("计算未正常结束，先查看错误记录。", "Computation did not finish normally. Start with its error log."),
    "missing": ("这项内容已不存在。请返回后重新选择。", "This item is no longer available. Go back and choose again."),
    "denied": ("目前无权查看这项内容。", "You cannot view this item now."),
    "unavailable": ("暂时无法读取，请重试。", "Could not read this now. Please retry."),
    "expired": ("登录后即可查看你的工作。", "Sign in to see your work."),
    "login": ("登录 SAI", "Sign in to SAI"),
    "files_denied": ("目前无法查看结果文件，工作状态仍可查看。", "Result files are not accessible now. Work status remains available."),
    "cost_denied": ("目前无法查看费用，工作仍可查看。", "Costs are not accessible now. Work remains available."),
    "live_failed": ("当前活动暂时无法读取", "Current activity could not be read"),
    "recent_failed": ("工作记录暂时无法读取", "Work records could not be read"),
    "more_live": ("只显示部分当前活动", "Showing part of the current activity"),
    "next": ("下一页", "Next page"), "first": ("回到开头", "Start again"),
    "previous": ("上一页", "Previous page"),
    "storage_choices": ("选择存储空间", "Choose storage"),
    "workspaces": ("按账号查看工作", "Choose an account"),
    "all_work": ("回到我的工作", "Return to my work"),
    "legacy_history": ("查看工作记录时，请选择账号名称。", "Choose an account by name to view its work records."),
    "workspaces_empty": ("目前没有可查看的账号。", "No readable accounts are available now."),
    "storage": ("存储用量", "Storage usage"), "storage_native": ("读取当前配额", "Read current quota"),
    "overview": ("账号与消息", "Account and messages"),
    "web": ("在网页中继续", "Continue in browser"),
    "web_ready": ("链接已准备好，也可以复制后打开。", "Link ready. You can also copy it to open elsewhere."),
    "copy": ("复制链接", "Copy link"), "copied": ("链接已复制", "Link copied"),
    "unknown_state": ("状态待确认", "State not confirmed"),
    "updated": ("更新于 {time}", "Updated {time}"),
    "menu_title": ("当前可用的操作", "Available actions"),
    "retry": ("重新读取", "Retry"), "paused": ("自动更新已暂停", "Automatic updates paused"),
    "resume": ("继续自动更新", "Resume updates"), "pause": ("暂停自动更新", "Pause updates"),
}


@dataclass(frozen=True)
class WorkbenchText:
    language: str

    def __call__(self, key: str, **values: object) -> str:
        if key in COPY:
            return COPY[key][0 if self.language == "zh-CN" else 1].format(**values)
        return Messages(self.language)(key, **values)


def natural_state(value: str | None, text: WorkbenchText) -> str:
    key = {"R": "running", "PD": "queued", "S": "suspended", "CG": "completing", "CD": "completed",
           "F": "failed", "CA": "canceled", "TO": "failed", "OOM": "failed", "NF": "failed"}.get(
               short_job_state(value or ""), value)
    if key not in {"accepted", "queued", "running", "completed", "failed", "canceled", "canceling", "needs_attention", "suspended", "completing"}:
        key = "unknown_state"
    return text(key)


def work_row(title: str | None, state: str | None, label: str, text: WorkbenchText) -> Text:
    prompt = Text(terminal_log(title or text("untitled")), style="bold", overflow="fold")
    style = "not bold " + {"completed": "green", "failed": "red", "needs_attention": "yellow"}.get(state or "", "")
    prompt.append("\n" + natural_state(state, text), style=style)
    if label:
        prompt.append(" · " + terminal_log(label), style="not bold")
    return prompt


def short_time(value: str | None) -> str:
    return "" if value is None else datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
