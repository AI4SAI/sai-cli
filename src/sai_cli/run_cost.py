"""One explicitly authorized final-cost observation, without pricing arithmetic."""
from dataclasses import dataclass
import re

from .errors import ContractError
from .managed_runs import ManagedReadResult, _boolean, _context, _integer, _object, _text, _time, _token
from .render import format_decimal
from .messages import Messages, display_site_name


AMOUNT_FIELDS = ("gross_amount", "cash_amount", "sai_credit_cny_equivalent_amount", "sai_credit_amount",
                 "reservation_coverage_amount", "price_adjustment_amount", "quantity")
FUNDING_FIELDS = AMOUNT_FIELDS[1:-1]


def _amount(data: dict, key: str, request_id: str, *, nullable: bool = True) -> str | None:
    value = _text(data, key, request_id, nullable=nullable, maximum=64)
    unsigned = value.removeprefix('-') if key == 'price_adjustment_amount' and value is not None else value
    if unsigned is not None and re.fullmatch(r'(?:0|[1-9][0-9]*)\.[0-9]{8}', unsigned) is None:
        raise ContractError(request_id=request_id)
    return value


def cost_fields(data: dict, request_id: str) -> dict:
    """Validate the same final amounts and funding visibility for every consumer."""
    status = _text(data, "status", request_id)
    if data.get("currency") != "CNY" or status not in {"pending", "settled", "unavailable", "not_chargeable"}:
        raise ContractError(request_id=request_id)
    visible = _boolean(data, "cash_visible", request_id)
    amounts = _object(data.get("amounts"), request_id)
    checked = {}
    for key in AMOUNT_FIELDS:
        checked[key] = _amount(amounts, key, request_id)
    settled = status == "settled"
    settled_at = _time(data, "settled_at", request_id, nullable=True)
    unit = _text(data, "unit_name", request_id, nullable=True, maximum=64)
    if ((not settled and (any(value is not None for value in checked.values()) or settled_at is not None or unit is not None))
            or (settled and (checked["gross_amount"] is None or checked["quantity"] is None))
            or (not visible and any(checked[key] is not None for key in FUNDING_FIELDS))
            or (settled and visible and any(checked[key] is None for key in FUNDING_FIELDS))):
        raise ContractError(request_id=request_id)
    result = {"status": status, "currency": "CNY", "settled_at": settled_at,
              "cash_visible": visible, "amounts": checked, "unit_name": unit}
    if 'charge_amount' in data:
        charge = _amount(data, 'charge_amount', request_id)
        if (not settled or not visible) and charge is not None:
            raise ContractError(request_id=request_id)
        result['charge_amount'] = charge
    if 'segments' in data:
        raw = data['segments']
        if not isinstance(raw, list) or (not settled and raw):
            raise ContractError(request_id=request_id)
        segments, identities = [], set()
        for index, item in enumerate(raw):
            row = _object(item, request_id)
            identity = _text(row, 'line_item_id', request_id, maximum=36)
            if not identity or identity in identities or _integer(row, 'segment_index', request_id) != index:
                raise ContractError(request_id=request_id)
            identities.add(identity)
            segment = {'line_item_id': identity, 'segment_index': index,
                       'quantity': _amount(row, 'quantity', request_id, nullable=False),
                       'unit_name': _text(row, 'unit_name', request_id, maximum=64),
                       'unit_price': _amount(row, 'unit_price', request_id),
                       'charge_amount': _amount(row, 'charge_amount', request_id)}
            for key, maximum in [('purchase_reference', 160), ('pricing_contract_key', 96),
                                 ('purchase_label', 256), ('contract_no', 128)]:
                segment[key] = _text(row, key, request_id, nullable=True, maximum=maximum)
            if (not segment['unit_name'] or not visible and any(segment[key] is not None for key in
                    ('unit_price', 'charge_amount', 'purchase_reference', 'pricing_contract_key', 'purchase_label', 'contract_no'))):
                raise ContractError(request_id=request_id)
            segment['amounts'] = cost_fields({'status': status, 'currency': 'CNY', 'cash_visible': visible,
                'amounts': row.get('amounts'), 'unit_name': segment['unit_name'], 'settled_at': settled_at}, request_id)['amounts']
            if segment['quantity'] != segment['amounts']['quantity']:
                raise ContractError(request_id=request_id)
            segments.append(segment)
        result['segments'] = segments
    return result


@dataclass(frozen=True)
class ManagedRunCost(ManagedReadResult):
    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str,
                     run_ref: str, request_id: str) -> "ManagedRunCost":
        data, result = _context(payload, "compute.run-cost/v1", workspace_key, site_id, request_id)
        if _token(data, "run_ref", request_id) != run_ref or data.get("source") != "portal_final_billing":
            raise ContractError(request_id=request_id)
        checked = cost_fields(data, request_id)
        return cls({**result, "run_ref": run_ref, "source": "portal_final_billing",
                    "queried_at": _time(data, "queried_at", request_id), **checked})


def cost_lines(result: ManagedRunCost, language: str = "en-US") -> list[str]:
    t, data = Messages(language), result.values
    lines = [t("final_cost") + " · " + t("cost_" + data["status"])]
    if data["status"] == "settled":
        amounts = data["amounts"]
        lines.append(f"{t('cost_gross')}: {format_decimal(amounts['gross_amount'])} CNY")
        if data.get('charge_amount') is not None:
            lines.append(f"{t('cost_total_charge')}: {format_decimal(data['charge_amount'])} CNY")
        if data["cash_visible"]:
            lines.extend((f"{t('cost_cash')}: {format_decimal(amounts['cash_amount'])} CNY",
                          f"SAI Credit: {format_decimal(amounts['sai_credit_amount'], trim=True)} {t('credit_unit')} ({format_decimal(amounts['sai_credit_cny_equivalent_amount'])} CNY)",
                          f"{t('cost_coverage')}: {format_decimal(amounts['reservation_coverage_amount'])} CNY",
                          f"{t('cost_adjustment')}: {format_decimal(amounts['price_adjustment_amount'])} CNY"))
        else:
            lines.append(t("cost_funding_hidden"))
        lines.extend((f"{t('cost_quantity')}: {format_decimal(amounts['quantity'], 4, trim=True)} {data['unit_name'] or t('unknown')}",
                      f"{t('cost_settled_at')}: {data['settled_at'] or t('unknown')}"))
        if data.get('segments'):
            lines.append(t('cost_segments'))
            for part in data['segments']:
                label = part.get('purchase_label') or part.get('contract_no') or str(part['segment_index'] + 1)
                detail = f"  {label}: {format_decimal(part['quantity'], 4, trim=True)} {part['unit_name']}"
                if data['cash_visible'] and part['unit_price'] is not None:
                    detail += f" · {t('cost_unit_price')} {format_decimal(part['unit_price'], 8, trim=True)} CNY/{part['unit_name']}"
                if part['charge_amount'] is not None:
                    detail += f" · {format_decimal(part['charge_amount'])} CNY"
                lines.append(detail)
    lines.extend((t("queried", time=data["queried_at"]), t("cost_source")))
    return lines


def render_run_cost(result: ManagedRunCost, *, site_label: str | None = None) -> str:
    data = result.values
    return "\n".join([f"Run: {data['run_ref']} · Read scope: {data['workspace_key']} · Site: {display_site_name(site_label, data['site_id'])}", *cost_lines(result)]) + "\n"
