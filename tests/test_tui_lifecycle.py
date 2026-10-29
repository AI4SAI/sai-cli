"""A slow account service must not block native work or prescribe another login."""
import asyncio

from textual.widgets import Static, Tabs

from sai_cli.cli import build_parser
from sai_cli.errors import AuthenticationError, NetworkError
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
from test_tui import loaded
from test_local_jobs import native_client, native_job
from test_native_topology import topology_client as job_client


def test_switch_to_native_reads_without_waiting_for_obsolete_remote_read(job_client):
    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), job_client[0])
        original = queries.read
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def read(request):
            calls.append(request.view)
            if request.view == "accounts":
                started.set()
                await release.wait()
                raise NetworkError("obsolete remote result")
            return await original(request)

        queries.read = read
        app = QueryApp(queries)
        async with app.run_test(size=(80, 24)) as pilot:
            await loaded(app, pilot)
            app.query_one(Tabs).active = "account"
            await asyncio.wait_for(started.wait(), 2)
            app.query_one(Tabs).active = "jobs"
            await loaded(app, pilot)
            assert calls == ["jobs", "accounts", "jobs"]
            assert app.snapshot is not None and not release.is_set()
            assert len(app._active_reads) == 1
            snapshot = app.snapshot
            release.set()
            await pilot.pause(.05)
            assert app.snapshot is snapshot
            assert not str(app.query_one("#notice", Static).render())

    asyncio.run(run())


def test_credential_storage_error_does_not_ask_the_user_to_sign_in(job_client):
    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), job_client[0])

        async def fail(request):
            raise AuthenticationError("the token cache could not be written")

        queries.read = fail
        app = QueryApp(queries, initial="account")
        async with app.run_test(size=(80, 24)) as pilot:
            await loaded(app, pilot)
            notice = str(app.query_one("#content", Static).render())
            assert "could not be written" in notice
            assert "auth login" not in notice

    asyncio.run(run())


def test_slow_cancelled_authorization_does_not_immediately_overwrite_its_failure(job_client):
    from contextlib import nullcontext
    from sai_cli.errors import UnavailableError

    async def run():
        queries = Queries(build_parser().parse_args(["tui"]), job_client[0])
        calls = []
        error = AuthenticationError("Sign in", code="credentials_unavailable")
        error.recovery_argv = ("sai", "auth", "login")

        async def read(request):
            calls.append(request)
            raise error

        queries.read = read
        app = QueryApp(queries, initial="account")

        async def authorize(argv):
            app._last_read_at -= 120  # Browser interaction outlasted the ordinary poll interval.
            raise UnavailableError("The issuer is unavailable")

        queries.authorize = authorize
        app.suspend = nullcontext
        async with app.run_test(size=(80, 24)) as pilot:
            await loaded(app, pilot)
            count = len(calls)
            await app._authorize(error, [])
            app._poll_current_view()
            await pilot.pause(.05)
            assert len(calls) == count
            assert "issuer is unavailable" in str(app.query_one("#content", Static).render())

    asyncio.run(run())
