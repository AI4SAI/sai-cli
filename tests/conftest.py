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
