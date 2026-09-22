"""Compact terminal presentation, shared by login panels and the workbench."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .overview import AccountOverview


def _money(value: str) -> str:
    return f"¥{Decimal(value):,.2f}"


def overview_rows(overview: AccountOverview, *, work_dir: str | None = None) -> list[tuple[str, str, str]]:
    data = overview.values
    context, access, funds, inbox = (data[key] for key in ("context", "access", "funds", "inbox"))
    rows = []
    if context["state"] != "available":
        rows.append(("默认身份", "暂不可用，请在控制台检查身份与站点权限", "warning"))
    else:
        rows.append(("工作身份", f"{context['label']} · Account={context['slurm_account']}", "identity"))
        if context["default_account"] != context["slurm_account"]:
            rows.append(("需核对", "站点登录身份与控制台默认设置不同", "warning"))
    if work_dir is not None:
        safe_dir = "".join(c for c in work_dir if c.isprintable())
        rows.append(("当前目录", safe_dir, "plain"))
    if access["submit_allowed"] is False:
        rows.append(("提交受限", "请到控制台查看准入状态和处理方式", "warning"))
    if access["state"] == "recovery_pending":
        rows.append(("恢复中", "正在等待站点恢复登录和作业提交", "warning"))
    elif access["state"] == "failed":
        rows.append(("需处理", "访问状态未能同步，请联系运营，无需重复认证", "warning"))
    if not access["verification_current"] and access["initial_verification_deadline"]:
        deadline = datetime.fromisoformat(access["initial_verification_deadline"].replace("Z", "+00:00"))
        rows.append(("认证截止", deadline.astimezone().strftime("%Y-%m-%d") + " · 请在控制台完成认证", "plain"))
    if funds is None:
        pass
    elif funds["state"] == "unavailable":
        rows.append(("资金", "暂不可读取", "plain"))
    elif funds["state"] == "not_authorized":
        rows.append(("资金", "当前 CLI 会话未授权资金读取", "plain"))
    else:
        amounts = []
        if funds["budget_mode"]:
            budget = "未设上限" if funds["budget_mode"] == "unlimited" and funds["budget_available"] is None else _money(funds["budget_available"])
            amounts.append("项目预算 " + budget)
        if funds["net_balance"] is not None:
            amounts.append("现金 " + _money(funds["net_balance"]))
        if funds["available_credit"] is not None:
            points = f"{Decimal(funds['available_credit']):,.2f}".rstrip("0").rstrip(".")
            amounts.append(f"SAI Credit {points} 点")
        rows.append(("组织共享" if context["kind"] == "org" else "资金", " · ".join(amounts) or "当前范围无可见金额", "money"))
        extra = []
        if funds["postpaid_available"] is not None and Decimal(funds["postpaid_available"]) > 0:
            extra.append("可用授信 " + _money(funds["postpaid_available"]))
        if funds["running_cash_exposure"] is not None and Decimal(funds["running_cash_exposure"]) > 0:
            extra.append("运行现金预估 " + _money(funds["running_cash_exposure"]))
        if extra:
            rows.append(("资金明细", " · ".join(extra), "plain"))
        if funds["credit_expires_at"]:
            expiry = datetime.fromisoformat(funds["credit_expires_at"].replace("Z", "+00:00"))
            rows.append(("额度到期", "SAI Credit 最早到期 " + expiry.astimezone().strftime("%Y-%m-%d"), "plain"))
    if inbox is not None:
        rows.append(("未读消息", f"{inbox['unread_count']} 条 · 当前身份 / 本站", "plain"))
        rows.extend(("", item["title"], "plain") for item in inbox["items"])
    return rows


def render_overview(overview: AccountOverview, *, work_dir: str | None = None) -> str:
    data = overview.values
    lines = [f"SAI · {data['site_id']} · {data['user_name']}"]
    lines += [f"{label}  {value}" for label, value, _ in overview_rows(overview, work_dir=work_dir)]
    return "\n".join([*lines, "查看详细信息：sai tui", f"数据时间：{data['observed_at']}"]) + "\n"


def overview_panel(overview: AccountOverview, *, work_dir: str | None = None, base_url: str | None = None):
    # Optional UI dependencies stay outside JSON and plain-text command paths.
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    data = overview.values
    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(width=8, no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    styles = {"warning": "bold yellow", "identity": "bold", "money": "bold", "plain": ""}
    for label, value, kind in overview_rows(overview, work_dir=work_dir):
        grid.add_row(Text(label, style="cyan" if kind != "warning" else "bold yellow"), Text(value, style=styles[kind]))
    navigation = Text("sai tui", style="cyan")
    if base_url:
        navigation.append(" · 消息中心", style=f"link {overview.messages_url(base_url)}")
    grid.add_row(Text(""), navigation)
    stamp = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
    return Panel(grid, title=Text(f"SAI  /  {data['site_id']}  /  {data['user_name']}", style="bold cyan"),
                 subtitle=Text(f"登录快照 · {stamp}"), title_align="left",
                 subtitle_align="right", border_style="cyan", box=box.ROUNDED, padding=(0, 1))
