"""A width-aware quota view; the native alias and exact counters stay unchanged."""
from rich import box
from rich.console import Group
from rich.table import Table
from rich.text import Text

from .local_quota import LocalQuota, _path_text, _size


def quota_view(result: LocalQuota, *, language: str) -> Group:
    value = result.values
    chinese = language == "zh-CN"
    headings = ("", "空间", "文件数") if chinese else ("", "Space", "Files")
    table = Table(*headings, box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 1))
    labels = ("已用", "配额", "上限") if chinese else ("Used", "Quota", "Limit")
    for index, (space, files) in enumerate((("used_bytes", "used_inodes"), ("block_soft_bytes", "inode_soft"), ("block_hard_bytes", "inode_hard"))):
        size = _size(value[space], limit=index != 0)
        count = f"{int(value[files]):,}" if index == 0 or int(value[files]) else "unlimited"
        if chinese:
            size, count = size.replace("unlimited", "不限"), count.replace("unlimited", "不限")
        if index == 0:
            size += "*" if value["native_usage_markers"]["space"] else ""
            count += "*" if value["native_usage_markers"]["inodes"] else ""
        table.add_row(labels[index], size, count)
    table.add_row("宽限期" if chinese else "Grace", value["block_grace"]["raw"], value["inode_grace"]["raw"])
    return Group(Text(_path_text(value["path"])), table)
