"""Compact terminal presentation, shared by login panels and the workbench."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .overview import AccountOverview
from .tui_messages import Messages


def _money(value: str) -> str:
    return f"¥{Decimal(value):,.2f}"


def overview_rows(overview: AccountOverview, *, work_dir: str | None = None, language: str = "zh-CN") -> list[tuple[str, str, str]]:
    t = Messages(language)
    data = overview.values
    context, access, funds, inbox = (data[key] for key in ("context", "access", "funds", "inbox"))
    rows = []
    if context["state"] != "available":
        rows.append((t("default_identity"), t("identity_unavailable"), "warning"))
    else:
        rows.append((t("identity"), f"{context['label']} · Account={context['slurm_account']}", "identity"))
        if context["default_account"] != context["slurm_account"]:
            rows.append((t("check"), t("identity_mismatch"), "warning"))
    if work_dir is not None:
        safe_dir = "".join(c for c in work_dir if c.isprintable())
        rows.append((t("directory"), safe_dir, "path"))
    if access["submit_allowed"] is False:
        rows.append((t("submit_restricted"), t("check_admission"), "warning"))
    if access["state"] == "recovery_pending":
        rows.append((t("recovering"), t("recovery_pending"), "warning"))
    elif access["state"] == "failed":
        rows.append((t("action_needed"), t("access_sync_failed"), "warning"))
    if not access["verification_current"] and access["initial_verification_deadline"]:
        deadline = datetime.fromisoformat(access["initial_verification_deadline"].replace("Z", "+00:00"))
        rows.append((t("verification_deadline"), deadline.astimezone().strftime("%Y-%m-%d") + " · " + t("complete_verification"), "plain"))
    if funds is None:
        pass
    elif funds["state"] == "unavailable":
        rows.append((t("funds"), t("funds_unavailable"), "plain"))
    elif funds["state"] == "not_authorized":
        rows.append((t("funds"), t("funds_denied"), "plain"))
    else:
        amounts = []
        if funds["budget_mode"]:
            budget = t("unlimited") if funds["budget_mode"] == "unlimited" and funds["budget_available"] is None else _money(funds["budget_available"])
            amounts.append(t("project_budget") + " " + budget)
        if funds["net_balance"] is not None:
            amounts.append(t("cash") + " " + _money(funds["net_balance"]))
        if funds["available_credit"] is not None:
            points = f"{Decimal(funds['available_credit']):,.2f}".rstrip("0").rstrip(".")
            amounts.append(t("credit_points", points=points))
        rows.append((t("org_shared" if context["kind"] == "org" else "funds"), " · ".join(amounts) or t("no_visible_amount"), "money"))
        extra = []
        if funds["postpaid_available"] is not None and Decimal(funds["postpaid_available"]) > 0:
            extra.append(t("postpaid") + " " + _money(funds["postpaid_available"]))
        if funds["running_cash_exposure"] is not None and Decimal(funds["running_cash_exposure"]) > 0:
            extra.append(t("running_cash") + " " + _money(funds["running_cash_exposure"]))
        if extra:
            rows.append((t("funds_detail"), " · ".join(extra), "plain"))
        if funds["credit_expires_at"]:
            expiry = datetime.fromisoformat(funds["credit_expires_at"].replace("Z", "+00:00"))
            rows.append((t("credit_expiry"), t("credit_first_expiry") + " " + expiry.astimezone().strftime("%Y-%m-%d"), "plain"))
    if inbox is not None:
        rows.append((t("inbox"), t("inbox_count", count=inbox['unread_count']), "plain"))
        rows.extend(("", item["title"], "message") for item in inbox["items"])
    return rows


def render_overview(overview: AccountOverview, *, work_dir: str | None = None) -> str:
    data = overview.values
    lines = [f"SAI · {data['site_id']} · {data['user_name']}"]
    lines += [f"{label}  {value}" for label, value, _ in overview_rows(overview, work_dir=work_dir)]
    return "\n".join([*lines, "查看详细信息：sai tui", f"数据时间：{data['observed_at']}"]) + "\n"


def overview_panel(overview: AccountOverview, *, work_dir: str | None = None, base_url: str | None = None, language: str = "zh-CN"):
    # Optional UI dependencies stay outside JSON and plain-text command paths.
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    data = overview.values
    t = Messages(language)
    grid = Table.grid(padding=(0, 2), expand=True)
    if language == "zh-CN":
        grid.add_column(width=8, overflow="fold")
        grid.add_column(ratio=1, overflow="fold")
    else:
        grid.add_column(max_width=10, overflow="fold")
        grid.add_column(ratio=1, overflow="fold")
    styles = {"warning": "bold yellow", "identity": "bold", "money": "bold"}
    for label, value, kind in overview_rows(overview, work_dir=work_dir, language=language):
        if language == "en-US":
            label = {t("identity"): t("identity_compact"), t("default_identity"): t("identity_compact"),
                     t("org_shared"): t("shared_compact"), t("funds_detail"): t("details"),
                     t("inbox"): t("unread_compact")}.get(label, label)
        compact = kind in {"path", "message"}
        grid.add_row(Text(label, style="cyan" if kind != "warning" else "bold yellow"),
                     Text(value, style=styles.get(kind, ""), no_wrap=compact, overflow="ellipsis" if compact else "fold"))
    navigation = Text("sai tui", style="cyan")
    if base_url:
        navigation.append(" · " + t("message_center"), style=f"link {overview.messages_url(base_url)}")
    grid.add_row(Text(""), navigation)
    stamp = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
    return Panel(grid, title=Text(f"SAI  /  {data['site_id']}  /  {data['user_name']}", style="bold cyan"),
                 subtitle=Text(f"{t('login_snapshot')} · {stamp}"), title_align="left",
                 subtitle_align="right", border_style="cyan", box=box.ROUNDED, padding=(0, 1))
