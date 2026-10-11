"""Selected queue context, using the same observation as the job list."""
from rich.console import Group
from rich.text import Text

from .contracts import JobItem
from .render import _duration


def job_context(item: JobItem, *, language: str) -> Group:
    row = item.values
    chinese = language == "zh-CN"
    pending = row["state"] == "PD"
    location = ("等待原因" if pending else "节点") if chinese else ("Waiting" if pending else "Nodes")
    context = " · ".join(row[key] for key in ("slurm_user", "slurm_account", "partition") if row[key])
    amounts = [_duration(row["run_wait_seconds"])]
    if row["slots"] is not None:
        unit = ("任务" if chinese else "tasks") if pending else "CPU"
        amounts.append(f"{row['slots']} {unit}")
    if row["gpus_per_node"] is not None:
        amounts.append(f"{row['gpus_per_node']} " + ("GPU/节点" if chinese else "GPU/node"))
    return Group(Text(location + "  " + (row["reason_or_nodelist"] or "?")),
                 Text(" · ".join(amounts)), Text(context))
