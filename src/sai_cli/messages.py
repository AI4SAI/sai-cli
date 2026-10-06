"""Chinese and English presentation for the retained SAI command outputs."""
from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigError


MESSAGES: dict[str, tuple[str, str]] = {
    'runtime_stats': ('运行观测', 'Runtime stats'),
    'stats_available': ('已读取', 'Read'),
    'stats_not_running': ('当前无适用的运行步骤', 'No current running-step read'),
    'stats_unavailable': ('无法建立可靠观测', 'Observation unavailable'),
    'stats_meaning': ('按步骤统计，非利用率或总内存。', 'Per step, not utilization/total RSS.'),
    'stats_cpu': ('平均累计 CPU 秒', 'Mean cumulative CPU seconds'),
    'stats_rss': ('平均任务 RSS 字节', 'Mean task RSS bytes'),
    'stats_max_rss': ('单任务峰值 RSS 字节', 'Peak task RSS bytes'),
    'stats_tasks': ('任务数', 'Task count'),
    'stats_window': ('读取窗口 UTC', 'Read window UTC'),
    'stats_no_read': ('未调用原生读取', 'No native read'),
    'stats_sample_unknown': ('Slurm sstat · 原生采样时间未知', 'Slurm sstat · native sampling time unknown'),
    'stats_resize': ('资源调整时间 UTC', 'Resize time UTC'),
    'final_cost': ('最终费用', 'Final cost'),
    'cost_pending': ('待结算', 'Pending settlement'),
    'cost_settled': ('已结算', 'Settled'),
    'cost_unavailable': ('暂无法确认最终费用', 'Final cost is unavailable'),
    'cost_not_chargeable': ('不计费', 'Not chargeable'),
    'cost_gross': ('标准金额', 'Standard amount'),
    'cost_cash': ('现金支出', 'Cash charged'),
    'credit_unit': ('点', 'points'),
    'cost_coverage': ('预留覆盖', 'Reserved coverage'),
    'cost_adjustment': ('价格调整', 'Price adjustment'),
    'cost_quantity': ('计费用量', 'Quantity'),
    'cost_settled_at': ('结算时间', 'Settled at'),
    'cost_funding_hidden': ('资金分项无查看权限', 'Funding components are not visible'),
    'cost_source': ('Portal 最终账务记录', 'Portal final billing records'),
    'unknown': ('未知', 'Unknown'),
    'details': ('详情', 'Details'),
    'content_empty': ('文件为空', 'This file is empty'),
    'content_end': ('已到文件末尾', 'End of file'),
    'content_more': ('内容分段显示', 'Content is shown in sections'),
    'content_missing': ('文件已不存在，请刷新清单', 'The file is no longer present. Refresh the list.'),
    'content_unsupported': ('此文件不支持文本预览', 'Text preview is unavailable for this file'),
    'content_changed': ('文件已变化，请重新读取', 'The file changed. Refresh to read it again.'),
    'queried': ('读取于 {time}', 'Queried {time}'),
    'identity_compact': ('身份', 'Identity'),
    'shared_compact': ('共享资金', 'Shared'),
    'unread_compact': ('未读', 'Unread'),
    'nodes': ('节点', 'Nodes'),
    'kind': ('类别', 'Kind'),
    'submitted': ('提交 UTC', 'Submitted UTC'),
    'started': ('开始 UTC', 'Started UTC'),
    'restart': ('重启次数', 'Restart count'),
    'default_identity': ('默认身份', 'Default identity'),
    'identity': ('工作身份', 'Working identity'),
    'identity_unavailable': ('暂不可用，请在控制台检查身份与站点权限', 'Unavailable; check identity and site access in the console'),
    'check': ('需核对', 'Check'),
    'identity_mismatch': ('站点登录身份与控制台默认设置不同', 'The login identity differs from the console default'),
    'directory': ('当前目录', 'Current directory'),
    'submit_restricted': ('提交受限', 'Submission restricted'),
    'check_admission': ('请到控制台查看准入状态和处理方式', 'Check access status and next steps in the console'),
    'recovering': ('恢复中', 'Recovering'),
    'recovery_pending': ('正在等待站点恢复登录和作业提交', 'Waiting for site login and submission access to recover'),
    'action_needed': ('需处理', 'Action needed'),
    'access_sync_failed': ('访问状态未能同步，请联系运营，无需重复认证', 'Access could not be synchronized; contact support without repeating verification'),
    'verification_deadline': ('认证截止', 'Verification due'),
    'complete_verification': ('请在控制台完成认证', 'Complete verification in the console'),
    'funds': ('资金', 'Funds'),
    'funds_unavailable': ('暂不可读取', 'Temporarily unavailable'),
    'funds_denied': ('当前 CLI 会话未授权资金读取', 'This CLI session is not authorized to read funds'),
    'unlimited': ('未设上限', 'Unlimited'),
    'project_budget': ('项目预算', 'Project budget'),
    'cash': ('现金', 'Cash'),
    'credit_points': ('SAI Credit {points} 点', 'SAI Credit {points} points'),
    'org_shared': ('组织共享', 'Organization shared'),
    'no_visible_amount': ('当前范围无可见金额', 'No visible amount in this scope'),
    'postpaid': ('可用授信', 'Available credit'),
    'running_cash': ('运行现金预估', 'Running cash estimate'),
    'funds_detail': ('资金明细', 'Funds detail'),
    'credit_expiry': ('额度到期', 'Credit expiry'),
    'credit_first_expiry': ('SAI Credit 最早到期', 'Earliest SAI Credit expiry'),
    'inbox': ('未读消息', 'Unread messages'),
    'inbox_count': ('{count} 条 · 当前身份 / 本站', '{count} · current identity / site'),
    'message_center': ('消息中心', 'Messages'),
    'snapshot': ('查询时间', 'Observed'),
}


@dataclass(frozen=True)
class Messages:
    language: str = "zh-CN"

    def __post_init__(self) -> None:
        if self.language not in {"zh-CN", "en-US"}:
            raise ConfigError("Display language must be zh-CN or en-US")

    def __call__(self, key: str, /, **values: object) -> str:
        return MESSAGES[key][self.language == "en-US"].format(**values)
