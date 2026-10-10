"""Final job-charge pages using the same validated amounts as managed Runs."""
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ContractError
from .managed_runs import ManagedReadResult, _boolean, _integer, _object, _text, _time, _token
from .render import _line, format_decimal
from .run_cost import cost_fields, cost_lines


class JobCharges(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, site_id: str, scope: str, limit: int,
                     account_id: str | None, account_name: str | None, workspace_key: str | None,
                     job_key: str | None, job_id: str | None,
                     start_date: str | None, end_date: str | None, request_id: str):
        data = _object(payload, request_id)
        if (data.get('schema_version') != 'billing.job-charges/v1'
                or data.get('source') != 'portal_final_billing' or data.get('site_id') != site_id
                or data.get('scope') != scope or data.get('date_basis') != 'settled_at'
                or data.get('workspace_key') != workspace_key):
            raise ContractError(request_id=request_id)
        result = {key: data[key] for key in ('schema_version', 'source', 'site_id', 'scope', 'date_basis')}
        for key in ('account_id', 'account', 'workspace_key', 'slurm_user'):
            result[key] = _token(data, key, request_id, nullable=True)
        if (account_id is not None and result['account_id'] != account_id
                or account_name is not None and result['account'] != account_name
                or scope == 'self' and (result['account_id'] is not None or result['account'] is not None or not result['slurm_user'])
                or scope != 'self' and (result['account_id'] is None or result['account'] is None)):
            raise ContractError(request_id=request_id)
        result['queried_at'] = _time(data, 'queried_at', request_id)
        result['calendar_timezone'] = _text(data, 'calendar_timezone', request_id, nullable=True)
        for key, expected in (('start_date', start_date), ('end_date', end_date)):
            value = _text(data, key, request_id, nullable=True, maximum=10)
            try:
                if value is not None and date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise ContractError(request_id=request_id) from exc
            if value != expected:
                raise ContractError(request_id=request_id)
            result[key] = value
        if bool(start_date or end_date) != bool(result['calendar_timezone']):
            raise ContractError(request_id=request_id)
        calendar_zone = None
        if result['calendar_timezone'] is not None:
            try:
                calendar_zone = ZoneInfo(result['calendar_timezone'])
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ContractError(request_id=request_id) from exc
        raw = data.get('items')
        if not isinstance(raw, list) or len(raw) > limit:
            raise ContractError(request_id=request_id)
        items = []
        for value in raw:
            row = _object(value, request_id)
            item = {key: _token(row, key, request_id) for key in ('job_key', 'site_id', 'slurm_user', 'slurm_account')}
            for key in ('slurm_job_id', 'partition', 'resource_kind'):
                item[key] = _text(row, key, request_id)
            item['slurm_job_id_raw'] = _text(row, 'slurm_job_id_raw', request_id, nullable=True)
            item['resource_count'] = _integer(row, 'resource_count', request_id)
            item.update(cost_fields(row, request_id))
            if calendar_zone is not None:
                if item['settled_at'] is None:
                    raise ContractError(request_id=request_id)
                settled_date = datetime.fromisoformat(item['settled_at'].replace('Z', '+00:00')).astimezone(calendar_zone).date().isoformat()
                if start_date is not None and settled_date < start_date or end_date is not None and settled_date > end_date:
                    raise ContractError(request_id=request_id)
            if (item['site_id'] != site_id or item['status'] != 'settled'
                    or re.fullmatch(re.escape(f'slurm:{site_id}:') + r'(?:0|[1-9][0-9]{0,18})', item['job_key']) is None
                    or result['slurm_user'] is not None and item['slurm_user'] != result['slurm_user']
                    or job_key is not None and item['job_key'] != job_key
                    or job_id is not None and job_id not in {item['slurm_job_id'], item['slurm_job_id_raw']}):
                raise ContractError(request_id=request_id)
            items.append(item)
        if len({item['job_key'] for item in items}) != len(items) or job_key is not None and len(items) != 1:
            raise ContractError(request_id=request_id)
        result.update(items=items, count=_integer(data, 'count', request_id, maximum=limit),
                      has_more=_boolean(data, 'has_more', request_id),
                      next_cursor=_text(data, 'next_cursor', request_id, nullable=True, maximum=1024))
        if result['count'] != len(items) or result['has_more'] != bool(result['next_cursor']) or job_key and result['has_more']:
            raise ContractError(request_id=request_id)
        return cls(result)


def render_job_charges(result: JobCharges, *, detail: bool = False) -> str:
    data = result.values
    if detail:
        item = data['items'][0]
        return '\n'.join([f"{item['slurm_job_id_raw'] or item['slurm_job_id']} · {item['slurm_account']}",
            item['job_key'], *cost_lines(ManagedReadResult({**item, 'queried_at': data['queried_at']}))]) + '\n'
    rows = []
    for item in data['items']:
        amounts = item['amounts']
        rows.append((item['slurm_job_id_raw'] or item['slurm_job_id'], item['slurm_account'],
                     format_decimal(amounts['cash_amount']) if item['cash_visible'] else 'Hidden',
                     format_decimal(amounts['sai_credit_amount'], trim=True) if item['cash_visible'] else 'Hidden',
                     item['settled_at'] or 'Unknown'))
    headings = ('Job', 'Account', 'Cash CNY', 'SAI Credit', 'Settled UTC')
    widths = [max(len(header), *(len(row[index]) for row in rows)) if rows else len(header)
              for index, header in enumerate(headings)]
    lines = [f"Settled job charges · {data['site_id']}"]
    if rows:
        lines.extend((_line(headings, widths), *(_line(row, widths) for row in rows)))
    else:
        lines.append('No settled charges in this scope.')
    if data['has_more']:
        lines.append('More records are available; JSON includes the next cursor.')
    return '\n'.join(lines) + '\n'
