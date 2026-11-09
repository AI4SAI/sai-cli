"""Standard Slurm association metadata shared by SAI writers and readers."""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from typing import Any

REASONS = frozenset({"arrears", "severe_arrears", "no_compute_funding", "admin_blocked"})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}")


def validate_reason(value: object) -> str | None:
    if value is not None and (not isinstance(value, str) or value not in REASONS):
        raise ValueError("invalid SAI account restriction")
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError("invalid native account or cluster")
    return value


def _time(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 253402300799:
        raise ValueError("invalid observation time")
    return value


_PREFIX = "[sai.account-state/"
_MARKER = re.compile(
    r"\[sai\.account-state/(v[12]):([A-Za-z0-9][A-Za-z0-9_.+\-]{0,127}):"
    r"([1-9][0-9]{0,9}):([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}):"
    r"([1-9][0-9]{0,18}):(open|arrears|severe_arrears|no_compute_funding|admin_blocked)"
    r"(?::([A-Za-z0-9_-]+))?\]"
)
ASSOCIATION_BATCH_SIZE = 512
_LIMIT_FIELDS = {"billing_tres_limit": 2**64 - 3, "max_submit_jobs": 2**32 - 3}
_REASON_FIELDS = {"AssocGrpBilling": "billing_tres_limit", "AssocMaxSubmitJobLimit": "max_submit_jobs"}
_SOURCE_KINDS = frozenset({"service_level", "grant", "reservation", "org_admin", "project_pi",
                           "hard_clamp", "member_limit", "risk_control"})
_SERVICE_LEVELS = frozenset({"personal_unverified", "personal_standard", "registration_trial",
                            "personal_advanced", "org_standard", "standard", "plus", "pro", "ultra"})
_GRANT_KINDS = frozenset({"baseline", "assurance", "contract", "subscription", "trial", "mis"})
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_OMITTED = object()


def _integer(value: object, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid native limit integer")
    return value


def _association_id(value: object) -> int:
    if _integer(value, 2**32 - 3) == 0:
        raise ValueError("invalid native association identity")
    return value


def _sources(value: object, *, allow_empty: bool = False) -> list[dict[str, str]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError("invalid limit sources")
    result, seen = [], set()
    for source in value:
        if (not isinstance(source, dict) or not isinstance(source.get("kind"), str)
                or source["kind"] not in _SOURCE_KINDS
                or set(source) - {"kind", "service_level_code", "grant_kind"}):
            raise ValueError("invalid limit source")
        kind = source["kind"]
        for field, allowed, kinds in (("service_level_code", _SERVICE_LEVELS, {"service_level", "grant"}),
                                      ("grant_kind", _GRANT_KINDS, {"grant"})):
            if field in source and (kind not in kinds or not isinstance(source[field], str)
                                    or source[field] not in allowed):
                raise ValueError("invalid limit source category")
        key = tuple(sorted(source.items()))
        if key in seen:
            raise ValueError("duplicate limit source")
        seen.add(key)
        result.append(dict(key))
    return sorted(result, key=lambda source: tuple(sorted(source.items())))


def validate_limit_sources(value: object) -> dict[str, Any]:
    """Validate the applied field/value/source map without importing Center policy."""
    if not isinstance(value, dict) or set(value) - _LIMIT_FIELDS.keys():
        raise ValueError("invalid limit fields")
    result = {}
    for field, entry in sorted(value.items()):
        if not isinstance(entry, dict) or set(entry) != {"value", "sources"}:
            raise ValueError("invalid applied limit")
        result[field] = {"value": _integer(entry["value"], _LIMIT_FIELDS[field]),
                         "sources": _sources(entry["sources"])}
    return result


def validate_applied_context(value: object) -> dict[str, Any]:
    """Validate a writer's bounded native readback record, never its manual notes."""
    if (not isinstance(value, dict)
            or set(value) != {"recorded_at", "association_id", "lineage", "parents"}):
        raise ValueError("invalid applied association record")
    lineage, parents = value["lineage"], value["parents"]
    if (not isinstance(lineage, str) or not lineage.startswith("/") or not lineage.endswith("/")
            or len(lineage) > 65536 or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in lineage)
            or not isinstance(parents, list) or not 1 <= len(parents) <= ASSOCIATION_BATCH_SIZE):
        raise ValueError("invalid applied association scope")
    result, seen_ids, seen_accounts = [], set(), set()
    bounds = {"group_jobs_limit": 2**32 - 3, **_LIMIT_FIELDS}
    for parent in parents:
        if (not isinstance(parent, dict) or set(parent) != {
                "account", "association_id", "owner_ref", "revision", "reason", "numeric", "limits"}):
            raise ValueError("invalid applied parent record")
        account, ident = _name(parent["account"]), _association_id(parent["association_id"])
        if account in seen_accounts or ident in seen_ids:
            raise ValueError("duplicate applied association")
        seen_accounts.add(account)
        seen_ids.add(ident)
        owner, revision, reason = parent["owner_ref"], parent["revision"], validate_reason(parent["reason"])
        limits = validate_limit_sources(parent["limits"])
        if owner is None:
            if revision is not None or reason is not None or limits:
                raise ValueError("unowned applied source")
        elif (not isinstance(owner, str) or _UUID.fullmatch(owner) is None
                or _integer(revision, 2**63 - 1) == 0):
            raise ValueError("invalid applied source incarnation")
        numeric = parent["numeric"]
        if not isinstance(numeric, dict) or set(numeric) != bounds.keys():
            raise ValueError("invalid applied native values")
        numeric = {field: None if numeric[field] is None else _integer(numeric[field], maximum)
                   for field, maximum in bounds.items()}
        result.append({"account": account, "association_id": ident, "owner_ref": owner,
                       "revision": revision, "reason": reason, "numeric": numeric, "limits": limits})
    return {"recorded_at": _time(value["recorded_at"]), "association_id": _association_id(value["association_id"]),
            "lineage": lineage, "parents": result}


def _metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in (
            {"limits", "ancestor_ids", "member"}, {"limits", "ancestor_ids", "member", "applied"}):
        raise ValueError("invalid association metadata")
    ancestors = value["ancestor_ids"]
    if not isinstance(ancestors, list) or len(ancestors) > ASSOCIATION_BATCH_SIZE:
        raise ValueError("invalid association ancestry")
    ancestors = [_association_id(ident) for ident in ancestors]
    if len(set(ancestors)) != len(ancestors):
        raise ValueError("duplicate association ancestor")
    limits, member = validate_limit_sources(value["limits"]), value["member"]
    if member is not None:
        if (not isinstance(member, dict) or set(member) != {"association_id", "owner_ref", "revision", "limits"}
                or not isinstance(member["owner_ref"], str) or _UUID.fullmatch(member["owner_ref"]) is None
                or _integer(member["revision"], 2**63 - 1) == 0):
            raise ValueError("invalid member limit incarnation")
        member = {"association_id": _association_id(member["association_id"]),
                  "owner_ref": member["owner_ref"], "revision": member["revision"],
                  "limits": validate_limit_sources(member["limits"])}
    if (limits and (ancestors or member is not None)) or (member is not None and not ancestors):
        raise ValueError("mixed account and member metadata")
    result = {"limits": limits, "ancestor_ids": ancestors, "member": member}
    if "applied" in value:
        if limits or not ancestors:
            raise ValueError("applied context requires a user association")
        result["applied"] = validate_applied_context(value["applied"])
    return result


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def decode_association_comment(comment: object) -> dict[str, Any] | None:
    """Decode only our ASCII prefix; native cache escaping of notes is irrelevant."""
    if comment is None or comment == "":
        return None
    if not isinstance(comment, str) or len(comment.encode("utf-8")) > 65536:
        raise ValueError("invalid association comment")
    if not comment.startswith(_PREFIX):
        return None
    match = _MARKER.match(comment)
    if match is None or (match.end() < len(comment) and comment[match.end()] != " "):
        raise ValueError("invalid managed association prefix")
    version, account, association_id, owner_ref, revision, reason, encoded = match.groups()
    association_id, revision = int(association_id), int(revision)
    if association_id >= 2**32 - 2 or revision > 2**63 - 1:
        raise ValueError("invalid managed association generation")
    result = {"account": account, "association_id": association_id, "owner_ref": owner_ref,
              "revision": revision, "reason": None if reason == "open" else reason}
    if version == "v1":
        if encoded is not None:
            raise ValueError("invalid v1 association metadata")
        return result
    if encoded is None:
        raise ValueError("missing v2 association metadata")
    try:
        decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        metadata = _metadata(json.loads(decoded.decode("ascii")))
    except (ValueError, UnicodeError, binascii.Error, RecursionError) as exc:
        raise ValueError("invalid v2 association metadata") from exc
    if base64.urlsafe_b64encode(_canonical(metadata)).rstrip(b"=").decode("ascii") != encoded:
        raise ValueError("noncanonical association metadata")
    return {**result, **metadata}


def strip_association_comment(comment: str | None) -> str:
    """Preserve the original database note, including its spaces and quotes."""
    if comment is None:
        return ""
    if decode_association_comment(comment) is None:
        return comment
    end = _MARKER.match(comment).end()
    return comment[end + 1:] if end < len(comment) else ""


def encode_association_comment(comment: str | None, *, account: str, association_id: int,
                               owner_ref: str, revision: int, reason: str | None,
                               limits: object = _OMITTED, ancestor_ids: object = _OMITTED,
                               member: object = _OMITTED, applied: object = _OMITTED) -> str:
    account = _name(account)
    validate_reason(reason)
    if type(association_id) is not int or type(revision) is not int:
        raise ValueError("invalid managed association generation")
    version, suffix = "v1", ""
    if any(value is not _OMITTED for value in (limits, ancestor_ids, member, applied)):
        metadata = {"limits": {} if limits is _OMITTED else limits,
                    "ancestor_ids": [] if ancestor_ids is _OMITTED else ancestor_ids,
                    "member": None if member is _OMITTED else member}
        if applied is not _OMITTED:
            metadata["applied"] = applied
        metadata = _metadata(metadata)
        suffix = ":" + base64.urlsafe_b64encode(_canonical(metadata)).rstrip(b"=").decode("ascii")
        version = "v2"
    prefix = f"{_PREFIX}{version}:{account}:{association_id}:{owner_ref}:{revision}:{reason or 'open'}{suffix}]"
    decode_association_comment(prefix)
    note = strip_association_comment(comment)
    value = prefix + (" " + note if note else "")
    if len(value.encode("utf-8")) > 65536:
        raise ValueError("association comment exceeds native input bound")
    return value


def association_read_command(cluster: str, ids: list[int]) -> list[str]:
    _name(cluster)
    if (not ids or len(ids) > ASSOCIATION_BATCH_SIZE
            or any(type(value) is not int or not 0 < value < 2**32 - 2 for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("invalid association query cohort")
    return ["sacctmgr", "--json", "show", "association", "where", f"Cluster={cluster}",
            "Ids=" + ",".join(str(value) for value in ids), "WOPLimits"]


def _native_count(value: object) -> int | None:
    if (not isinstance(value, dict) or type(value.get("set")) is not bool
            or type(value.get("infinite")) is not bool or type(value.get("number")) is not int):
        raise ValueError("invalid native association count")
    if value["set"] and value["infinite"]:
        raise ValueError("contradictory native association count")
    return _integer(value["number"], 2**32 - 3) if value["set"] else None


def association_limit_values(row: dict[str, Any]) -> dict[str, int | None]:
    """Read upstream WOPLimits JSON; inherited effective values belong to no layer."""
    try:
        maximum = row["max"]
        group_jobs = _native_count(maximum["jobs"]["per"]["count"])
        submit = _native_count(maximum["jobs"]["total"])
        tres = maximum["tres"]["total"]
    except (KeyError, TypeError) as exc:
        raise ValueError("missing native association limit") from exc
    if not isinstance(tres, list):
        raise ValueError("invalid native association TRES")
    billing = None
    for item in tres:
        if not isinstance(item, dict):
            raise ValueError("invalid native association TRES")
        if item.get("type") == "billing" or item.get("id") == 5:
            if (item.get("type") != "billing" or type(item.get("id")) is not int
                    or item["id"] != 5 or item.get("name") != "" or billing is not None):
                raise ValueError("ambiguous native billing TRES")
            billing = _integer(item.get("count"), _LIMIT_FIELDS["billing_tres_limit"])
    return {"group_jobs_limit": group_jobs, "billing_tres_limit": billing, "max_submit_jobs": submit}


def _association_rows(ids: list[int], *, cluster: str, fetch) -> dict[int, dict[str, Any]]:
    rows = {}
    for offset in range(0, len(ids), ASSOCIATION_BATCH_SIZE):
        cohort = ids[offset:offset + ASSOCIATION_BATCH_SIZE]
        payload = fetch(cohort)
        if (not isinstance(payload, dict) or payload.get("errors")
                or not isinstance(payload.get("associations"), list)
                or len(payload["associations"]) > len(cohort)):
            raise ValueError("invalid native association result")
        for row in payload["associations"]:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or row["id"] not in cohort or row["id"] in rows or row.get("cluster") != cluster):
                raise ValueError("native association returned outside the requested cohort")
            rows[row["id"]] = row
    return rows


def _user_lineage(row: dict[str, Any], job: dict[str, Any]) -> list[str]:
    if row.get("account") != job.get("slurm_account") or row.get("user") != job.get("slurm_user"):
        raise ValueError("native association does not match the observed job")
    partition = row.get("partition") or ""
    if not isinstance(partition, str) or (partition and partition not in (job.get("partition") or "").split(",")):
        raise ValueError("native association partition does not match the observed job")
    lineage = row.get("lineage")
    if not isinstance(lineage, str) or not lineage.startswith("/") or not lineage.endswith("/"):
        raise ValueError("invalid native association lineage")
    parts = lineage.split("/")[1:-1]
    tail = ["0-" + _name(row["user"])] + ([partition] if partition else [])
    if parts[-len(tail):] != tail:
        raise ValueError("native association lineage does not match the observed user")
    names = parts[:-len(tail)]
    if (any(_name(name) != name for name in names) or len(set(names)) != len(names)
            or (names[-1] if names else "root") != row["account"]):
        raise ValueError("native association lineage does not match the observed account")
    return ["root", *names] if "root" not in names else names


def _parent_marker(row: dict[str, Any]) -> dict[str, Any] | None:
    marker = decode_association_comment(row.get("comment"))
    if (marker is None or marker["account"] != row["account"] or marker["association_id"] != row["id"]
            or marker.get("ancestor_ids") or marker.get("member") is not None):
        return None
    return marker


def _constraint(row: dict[str, Any], scope: str, field: str, limits: dict[str, Any], *,
                numeric: dict[str, int | None] | None = None) -> dict[str, Any] | None:
    value = (association_limit_values(row) if numeric is None else numeric)[field]
    if value is None:
        return None
    evidence = limits.get(field)
    sources = evidence["sources"] if evidence is not None and evidence["value"] == value else []
    return {"account": row["account"], "scope": scope, "field": field,
            "value": str(value), "sources": sources}


def _applied_matches(row: dict[str, Any], lineage: list[str], marker: dict[str, Any], observed: int) -> bool:
    applied = marker["applied"]
    if (applied["association_id"] != row["id"] or applied["lineage"] != row["lineage"]
            or applied["recorded_at"] > observed
            or [parent["association_id"] for parent in applied["parents"]] != marker["ancestor_ids"]
            or [parent["account"] for parent in applied["parents"]] != lineage):
        return False
    if marker["association_id"] == row["id"]:
        member = marker.get("member")
        return (marker["reason"] is None and marker["account"] == row["account"] and member is not None
                and all(member[key] == marker[key] for key in ("association_id", "owner_ref", "revision")))
    return any(all(parent[key] == marker[key] for key in
                   ("account", "association_id", "owner_ref", "revision", "reason"))
               for parent in applied["parents"])


def read_job_contexts(jobs: list[dict[str, Any]], association_ids: list[object], *,
                      cluster: str, fetch, now: float | None = None) -> list[dict[str, Any]]:
    """Read visible job associations and their applied records; old v2 reads parents."""
    _name(cluster)
    if len(jobs) != len(association_ids):
        raise ValueError("job association bindings are incomplete")
    eligible = [i for i, job in enumerate(jobs) if job.get("state") in {"PD", "PENDING"}
                and job.get("reason_or_nodelist") in {"AssocGrpJobsLimit", *_REASON_FIELDS}]
    ids = list(dict.fromkeys(_association_id(association_ids[i]) for i in eligible if association_ids[i] is not None))
    users = _association_rows(ids, cluster=cluster, fetch=fetch)
    prepared, ancestor_ids = {}, []
    for index in eligible:
        row = users.get(association_ids[index])
        if row is None:
            continue
        lineage = _user_lineage(row, jobs[index])
        marker = decode_association_comment(row.get("comment"))
        if marker is not None:
            if marker["account"] not in lineage or marker.get("limits"):
                raise ValueError("account context is outside the observed association lineage")
            if "ancestor_ids" in marker:
                if len(marker["ancestor_ids"]) != len(lineage) or row["id"] in marker["ancestor_ids"]:
                    raise ValueError("native association ancestry changed")
                if "applied" not in marker:
                    ancestor_ids.extend(marker["ancestor_ids"])
        prepared[index] = row, lineage, marker
    parents = _association_rows(list(dict.fromkeys(ancestor_ids)), cluster=cluster, fetch=fetch)
    results = [{} for _ in jobs]
    observed = _time(int(time.time() if now is None else now))
    for index, (row, lineage, marker) in prepared.items():
        current_parents = []
        recorded_at = None
        applied = marker.get("applied") if marker else None
        if applied is not None and _applied_matches(row, lineage, marker, observed):
            recorded_at = applied["recorded_at"]
            current_parents = [({"id": parent["association_id"], "account": parent["account"]},
                                parent if parent["owner_ref"] is not None else None, parent["numeric"])
                               for parent in applied["parents"]]
        old_ancestors = marker.get("ancestor_ids", []) if marker and applied is None else []
        for position, ident in enumerate(old_ancestors):
            parent = parents.get(ident)
            if parent is None:
                continue
            expected_lineage = "/" if position == 0 else "/" + "/".join(lineage[1:position + 1]) + "/"
            if (parent.get("account") != lineage[position] or parent.get("user") not in (None, "")
                    or parent.get("partition") not in (None, "") or parent.get("lineage") != expected_lineage):
                raise ValueError("native ancestor does not match the current lineage")
            current_parents.append((parent, _parent_marker(parent), association_limit_values(parent)))
        reason = jobs[index]["reason_or_nodelist"]
        if reason == "AssocGrpJobsLimit" and marker is not None and marker["reason"] is not None:
            verified = "ancestor_ids" not in marker or any(
                parent["id"] == marker["association_id"] and source is not None
                and all(source[key] == marker[key] for key in ("account", "owner_ref", "revision", "reason"))
                and numeric["group_jobs_limit"] == 0
                for parent, source, numeric in current_parents)
            if verified:
                results[index]["account_restriction"] = {"code": marker["reason"], "account": marker["account"],
                    "source": "sai_applied_policy", "observed_at": observed}
                if recorded_at is not None:
                    results[index]["account_restriction"].update(basis="applied_record", recorded_at=recorded_at)
        field = _REASON_FIELDS.get(reason)
        if field is None:
            continue
        member = marker.get("member") if marker else None
        member_limits = member["limits"] if member is not None and member["association_id"] == row["id"] else {}
        if applied is not None and recorded_at is None:
            member_limits = {}
        member_constraint = _constraint(row, "member", field, member_limits)
        if field == "max_submit_jobs":
            # Slurm inherits this per-user limit from the nearest explicit layer.
            constraints = [member_constraint] if member_constraint is not None else []
            current = {parent["id"]: (parent, source, numeric) for parent, source, numeric in current_parents}
            for ident in reversed(marker.get("ancestor_ids", []) if marker else []):
                if constraints or ident not in current:
                    break  # A missing nearer row cannot prove a farther inherited limit.
                parent, source, numeric = current[ident]
                candidate = _constraint(parent, "account", field, source.get("limits", {}) if source else {}, numeric=numeric)
                if candidate is not None:
                    constraints.append(candidate)
        else:
            constraints = [_constraint(parent, "account", field, source.get("limits", {}) if source else {}, numeric=numeric)
                           for parent, source, numeric in current_parents]
            constraints = [item for item in [*constraints, member_constraint] if item is not None]
        if constraints:
            results[index]["limit_context"] = {"observed_at": observed, "constraints": constraints}
            if recorded_at is not None and any(item["scope"] == "account" for item in constraints):
                results[index]["limit_context"].update(basis="applied_record", recorded_at=recorded_at)
    return results


def validate_account_restriction(value: object, *, state: object, reason: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if (not isinstance(value, dict) or not isinstance(state, str) or state not in {"PD", "PENDING"}
            or reason != "AssocGrpJobsLimit" or value.get("source") != "sai_applied_policy"
            or not isinstance(value.get("code"), str) or value["code"] not in REASONS):
        raise ValueError("invalid SAI account restriction")
    observed = _time(value.get("observed_at"))
    return {"code": value["code"], "account": _name(value.get("account")),
            "source": "sai_applied_policy", "observed_at": observed, **_record_time(value, observed)}


def _record_time(value: dict[str, Any], observed: int) -> dict[str, Any]:
    if "basis" not in value and "recorded_at" not in value:
        return {}
    recorded = _time(value.get("recorded_at"))
    if value.get("basis") != "applied_record" or recorded > observed:
        raise ValueError("invalid applied record time")
    return {"basis": "applied_record", "recorded_at": recorded}


def validate_limit_context(value: object, *, state: object, reason: object) -> dict[str, Any] | None:
    """Allowlist current limits, without claiming one of them caused scheduling."""
    if value is None:
        return None
    if (not isinstance(value, dict) or not isinstance(state, str) or state not in {"PD", "PENDING"}
            or not isinstance(reason, str) or reason not in _REASON_FIELDS):
        raise ValueError("invalid job limit context")
    constraints = value.get("constraints")
    if not isinstance(constraints, list) or not 1 <= len(constraints) <= ASSOCIATION_BATCH_SIZE + 1:
        raise ValueError("invalid job limit constraints")
    result, seen = [], set()
    field = _REASON_FIELDS[reason]
    if field == "max_submit_jobs" and len(constraints) != 1:
        raise ValueError("ambiguous inherited submit limit")
    for item in constraints:
        if (not isinstance(item, dict) or item.get("field") != field
                or not isinstance(item.get("scope"), str) or item["scope"] not in {"account", "member"}):
            raise ValueError("invalid job limit constraint")
        account = _name(item.get("account"))
        key = (account, item["scope"], field)
        if key in seen:
            raise ValueError("duplicate job limit constraint")
        seen.add(key)
        amount = item.get("value")
        if (not isinstance(amount, str) or len(amount) > 20
                or re.fullmatch(r"0|[1-9][0-9]*", amount) is None):
            raise ValueError("invalid public limit integer")
        _integer(int(amount), _LIMIT_FIELDS[field])
        result.append({"account": account, "scope": item["scope"], "field": field,
                       "value": amount,
                       "sources": _sources(item.get("sources"), allow_empty=True)})
    observed = _time(value.get("observed_at"))
    return {"observed_at": observed, "constraints": result, **_record_time(value, observed)}
