from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def job_payload() -> dict[str, Any]:
    return {
        "site_id": "site-a",
        "cluster_id": "cluster-a",
        "scope": "self",
        "visibility_role": "self",
        "slurm_user": "alice",
        "slurm_account": None,
        "items": [
            {
                "job_id": "12345",
                "array_task_id": None,
                "name": "simulation",
                "slurm_user": "alice",
                "slurm_account": "personal-alice",
                "state": "R",
                "state_label": "running",
                "priority": 1000,
                "submit_time": "2026-07-31T00:00:00Z",
                "start_time": "2026-07-31T00:01:00Z",
                "elapsed_seconds": 3600,
                "run_wait_seconds": 3600,
                "partition": "gpu-standard",
                "qos": "normal",
                "nodes": 1,
                "slots": 8,
                "gpus_per_node": 1,
                "mem_per_unit": "16G",
                "reason_or_nodelist": "compute-node",
            }
        ],
        "count": 1,
        "freshness": {
            "source": "squeue",
            "queried_at": "2026-07-31T01:01:00Z",
        },
    }


@pytest.fixture
def running_estimate_payload() -> dict[str, Any]:
    common = {
        "slurm_job_db_index": None,
        "slurm_user": "alice",
        "slurm_account": "personal-alice",
        "currency": "CNY",
        "final": False,
    }
    allocated = {
        "partition": "gpu-standard",
        "qos": "normal",
        "nodes": 1,
        "alloc_tres": {
            "gpu": 1,
            "cpu": 8,
            "mem_mb": "16384",
            "billing": None,
            "nodes": 1,
        },
    }
    return {
        "operation": "billing.running-estimate",
        "version": "v1",
        "schema_version": "billing.running-estimate/v1",
        "site_id": "site-a",
        "site_timezone": "Asia/Shanghai",
        "cluster_id": "cluster-a",
        "scope": "self",
        "visibility_role": "self",
        "slurm_user": "alice",
        "slurm_account": None,
        "as_of": "2026-08-14T01:02:03Z",
        "freshness": {
            "source": "scheduler_cache",
            "observed_at": "2026-08-14T01:02:00Z",
            "ttl_seconds": 5,
            "age_seconds": 3,
            "stale": False,
        },
        "etag": "snapshot-etag",
        "items": [
            {
                **common,
                "job_key": "opaque-running-key",
                "job_id_raw": "12345",
                "state": "RUNNING",
                "submit_time": "2026-08-14T00:00:00Z",
                "start_time": "2026-08-14T00:02:00Z",
                "elapsed_seconds": 3600,
                "resources": {
                    **allocated,
                    "resource_type": "gpu",
                    "resource_count": 1,
                    "usage_quantity": "1.00000000",
                },
                "gross_cny": "2.00000000",
                "cash_cny": "1.80000000",
                "price_revision": "price-v1",
                "estimate_status": "estimated",
                "uncertainty": [],
            },
            {
                **common,
                "job_key": "opaque-pending-key",
                "job_id_raw": "12346",
                "state": "PENDING",
                "submit_time": "2026-08-14T01:00:00Z",
                "start_time": None,
                "elapsed_seconds": None,
                "resources": {
                    **allocated,
                    "resource_type": None,
                    "resource_count": None,
                    "usage_quantity": None,
                },
                "gross_cny": None,
                "cash_cny": None,
                "price_revision": None,
                "estimate_status": "not_started",
                "uncertainty": [],
            },
            {
                **common,
                "job_key": "opaque-unavailable-key",
                "job_id_raw": "12347",
                "state": "RUNNING",
                "submit_time": "2026-08-14T00:00:00Z",
                "start_time": "2026-08-14T00:02:00Z",
                "elapsed_seconds": 3600,
                "resources": {
                    "partition": "unknown-partition",
                    "qos": "normal",
                    "nodes": 1,
                    "alloc_tres": None,
                    "resource_type": None,
                    "resource_count": None,
                    "usage_quantity": None,
                },
                "gross_cny": None,
                "cash_cny": None,
                "price_revision": None,
                "estimate_status": "unavailable",
                "uncertainty": ["pricing_unavailable"],
            },
        ],
        "count": 3,
        "final": False,
    }
