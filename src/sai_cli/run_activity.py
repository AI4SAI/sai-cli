"""Correlate authorized receipts and native observations without granting a read."""
from dataclasses import dataclass
from datetime import datetime

from .contracts import JobItem, JobResult
from .errors import SaiCliError
from .managed_runs import ManagedRunDetail
from .site_jobs import SiteJobResult


def matching_job(run: dict, observation: JobResult | SiteJobResult, *, site_id: str) -> JobItem | None:
    """A matching correlation also needs this site's current, bounded time evidence."""
    if (not isinstance(observation, SiteJobResult) or observation.freshness.stale
            or (observation.site_id, observation.cluster_id) != (site_id, run["cluster_id"])
            or not run.get("run_link")):
        return None
    candidates = [job for job in observation.items if job.values.get("run_link") == run["run_link"]]
    if len(candidates) != 1:
        return None
    job = candidates[0]
    if job.canonical_id != run["scheduler_ref"] or job.values["array_task_id"] is not None:
        return None
    submitted, started = job.values["submit_time"], job.values["start_time"]
    if submitted is None:
        return None
    accepted = datetime.fromisoformat(run["accepted_at"].replace("Z", "+00:00")).replace(microsecond=0)
    observed = datetime.fromisoformat(observation.freshness.observed_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(run["finished_at"].replace("Z", "+00:00")) if run["finished_at"] else observed
    if any(not accepted <= datetime.fromisoformat(stamp.replace("Z", "+00:00")) <= min(observed, end)
           for stamp in (submitted, started) if stamp is not None):
        return None
    return job


@dataclass(frozen=True)
class RunActivity:
    detail: ManagedRunDetail
    native: SiteJobResult | None = None
    error: SaiCliError | None = None

    @property
    def job(self) -> JobItem | None:
        return matching_job(self.detail.values["run"], self.native,
            site_id=self.detail.values["site_id"]) if self.native is not None else None

    @property
    def state(self) -> str:
        job = self.job
        return job.values["state"] if job is not None else self.detail.values["run"]["status"]
