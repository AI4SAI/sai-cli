"""User paths through native scopes, readable allocation and explicit directories."""
import asyncio
from copy import deepcopy
import html
import json
import os
from pathlib import Path
import pwd

import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, DirectoryTree, Select, Static, Tabs

from sai_cli.cli import build_parser
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
from test_tui import loaded
from test_local_jobs import native_client, native_job
from test_local_resources import native_client as resource_client
from test_native_account_tree import tree_client
from test_native_topology import topology_client as job_client
from test_local_quota import native_quota


def test_job_chooser_discovers_other_native_accounts_and_keeps_selected_scope(tree_client):
    env, path, payload = tree_client
    user = pwd.getpwuid(os.geteuid()).pw_name
    env['TREE_ROWS'] = (f'cluster-a|research|{user}|/research/0-{user}/\n'
                        f'cluster-a|project-a|{user}|/research/project-a/0-{user}/\n')
    payload['jobs'] = payload['jobs'][:1]
    path.write_text(json.dumps(payload))
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']), env))
        async with app.run_test(size=(80, 24)) as pilot:
            await loaded(app, pilot)
            assert not Path(env['TREE_CALLS']).exists(), 'first queue must not wait for account discovery'
            chooser = app.query_one(Select)
            chooser.focus()
            await pilot.pause()
            await pilot.press('enter')
            await loaded(app, pilot)
            assert chooser.expanded
            assert ('project-a', 'account:project-a') in app._options
            await pilot.press('down', 'down', 'enter')
            await loaded(app, pilot)
            assert app.selection == 'account:research'
            assert app.snapshot.filters['account_root'] == 'research'
            app.query_one(Tabs).active = 'account'
            await loaded(app, pilot)
            app.query_one(Tabs).active = 'jobs'
            await loaded(app, pilot)
            assert app.selection == 'account:research'
            assert app.snapshot.filters['account_root'] == 'research'
    asyncio.run(run())


@pytest.mark.parametrize('width', [40, 80, 120])
def test_topology_detail_scrolls_refreshes_and_returns_without_changing_job(job_client, width):
    env, path, payload = job_client
    second = {**deepcopy(payload['jobs'][0]), 'job_id':43}
    payload['jobs'].append(second)
    path.write_text(json.dumps(payload))
    queries = Queries(build_parser().parse_args(['tui']), env)
    original, calls = queries.read, []
    async def read(request):
        calls.append(request.view)
        return await original(request)
    queries.read = read
    async def run():
        app = QueryApp(queries)
        async with app.run_test(size=(width, 20)) as pilot:
            await loaded(app, pilot)
            assert 'compute-' in html.unescape(app.export_screenshot())
            await pilot.press('down', 'enter')
            await loaded(app, pilot)
            detail = app.query_one('#detail', VerticalScroll)
            assert detail.has_focus and not app.query_one('#body').display
            assert detail.max_scroll_y > 0
            await pilot.press('i')
            await pilot.pause()
            assert app._expanded_allocation and calls == ['jobs','allocation']
            await pilot.press('i')
            assert not app._expanded_allocation
            await pilot.press('pagedown', 'down')
            await pilot.pause()
            assert detail.scroll_y > 0 and app._selected_job == '43'
            await pilot.press('r')
            await loaded(app, pilot)
            assert calls == ['jobs','allocation','allocation']
            assert detail.has_focus
            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert detail.max_scroll_x == 0
            await pilot.press('escape')
            assert not detail.display and app.query_one('#job-table').has_focus
            assert app._selected_job == '43' and calls == ['jobs','allocation','allocation']
    asyncio.run(run())


def test_partition_choice_survives_view_switch_and_no_extra_read_for_selection(resource_client):
    env, _, _ = resource_client
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']), env))
        async with app.run_test(size=(80,24)) as pilot:
            await loaded(app, pilot)
            app.query_one(Select).value = 'gpu-new'
            await pilot.pause()
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines()) == 1
            await pilot.press('3'); await loaded(app, pilot)
            await pilot.press('2'); await loaded(app, pilot)
            assert app.selection == 'gpu-new'
            assert app.query_one('#resource-table',DataTable).row_count == 2
            await pilot.pause()
            assert app.query_one('#resource-table').max_scroll_x == 0
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines()) == 3
    asyncio.run(run())


def test_opening_accounts_during_first_read_does_not_discard_the_queue(tree_client):
    from sai_cli.local_accounts import LocalAccounts
    env, path, payload = tree_client
    payload['jobs'] = payload['jobs'][:1]
    path.write_text(json.dumps(payload))
    queries = Queries(build_parser().parse_args(['tui']), env)
    original = queries.read
    release = asyncio.Event()
    calls = []
    async def read(request):
        calls.append(request.view)
        if request.view == 'jobs':
            await release.wait()
        if request.view == 'job_accounts':
            return LocalAccounts({'accounts': ['research'], 'cluster': 'cluster-a'})
        return await original(request)
    queries.read = read
    async def run():
        app = QueryApp(queries)
        async with app.run_test(size=(80,24)) as pilot:
            chooser = app.query_one(Select)
            chooser.focus()
            await pilot.pause()
            await pilot.press('enter')
            assert chooser.expanded
            release.set()
            await loaded(app, pilot)
            assert calls == ['jobs', 'job_accounts']
            assert app.snapshot is not None and app.query_one('#job-table',DataTable).row_count == 1
            assert chooser.expanded and ('research', 'account:research') in app._options
    asyncio.run(run())


def test_quota_directory_picker_reads_selected_path_and_cancel_preserves_scope(native_quota, monkeypatch):
    env, path = native_quota
    monkeypatch.chdir(path)
    chosen = path / '[bold]shared research'
    chosen.mkdir()
    (path / 'not-a-directory').write_text('unchanged')
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']), env))
        async with app.run_test(size=(60,24)) as pilot:
            await loaded(app, pilot)
            assert app.view == 'quota'
            app.query_one(Select).value = 'pick-directory'
            await pilot.pause()
            tree = app.screen.query_one(DirectoryTree)
            for _ in range(20):
                if tree.root.children:
                    break
                await pilot.pause(.02)
            assert len(tree.root.children) == 1
            assert tree.root.children[0].label.plain == chosen.name
            tree.select_node(tree.root.children[0])
            await pilot.press('enter')
            await pilot.click('#directory-use')
            await loaded(app, pilot)
            assert app.selection == str(chosen)
            assert app.snapshot.values['path'] == str(chosen)
            assert app.query_one('#answer').max_scroll_x == 0
            calls = [json.loads(line) for line in Path(env['NATIVE_CALL']).read_text().splitlines()]
            assert len(calls) == 4 and all(call['argv'][-1] == str(chosen) for call in calls[-2:])
            app.query_one(Select).value = 'pick-directory'
            await pilot.pause()
            app._last_read_at -= 40
            app._poll_current_view()
            await pilot.press('escape')
            assert app.selection == str(chosen)
            assert len(Path(env['NATIVE_CALL']).read_text().splitlines()) == 4
            assert (path / 'not-a-directory').read_text() == 'unchanged'
    asyncio.run(run())
