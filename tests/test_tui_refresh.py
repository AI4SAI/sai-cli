"""Polling must preserve the user's place and use only the visible native read."""
import asyncio
from copy import deepcopy
import html
import json
from pathlib import Path

import pytest
from textual.widgets import DataTable, Select, Static

from sai_cli.cli import build_parser
from sai_cli.tui import QueryApp
from sai_cli.tui_queries import Queries
from test_tui import loaded
from test_local_jobs import native_client, native_job
from test_native_topology import topology_client as job_client
from test_local_resources import native_client as resource_client


def test_background_refresh_preserves_rows_selection_scroll_and_focus(job_client):
    env, path, payload = job_client
    payload['jobs'] = [{**deepcopy(payload['jobs'][0]), 'job_id': number} for number in range(100,180)]
    path.write_text(json.dumps(payload))
    queries = Queries(build_parser().parse_args(['tui']), env)
    original = queries.read
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def read(request):
        calls.append(request.view)
        if len(calls) == 2:
            started.set()
            await release.wait()
        return await original(request)
    queries.read = read
    async def run():
        app = QueryApp(queries)
        async with app.run_test(size=(100,25)) as pilot:
            await loaded(app,pilot)
            table = app.query_one('#job-table', DataTable)
            table.move_cursor(row=40)
            await pilot.pause()
            selected, scroll = app._selected_job, table.scroll_offset
            chooser = app.query_one(Select)
            chooser.focus()
            app._last_read_at -= 6
            app._poll_current_view()
            await asyncio.wait_for(started.wait(),2)
            assert table.row_count == 80 and app.snapshot is not None
            app._poll_current_view(); app._poll_current_view()
            payload['jobs'].reverse()
            path.write_text(json.dumps(payload))
            release.set()
            await loaded(app,pilot)
            assert calls == ['jobs','jobs']
            assert app._selected_job == selected
            assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == selected
            assert table.scroll_offset == scroll and chooser.has_focus
            chooser.action_show_overlay()
            app._last_read_at -= 6
            app._poll_current_view()
            await pilot.pause(.05)
            assert calls == ['jobs','jobs','job_accounts'] and chooser.expanded
            await pilot.press('escape')
            table.focus()
            await pilot.press('enter'); await loaded(app,pilot)
            assert app.query_one('#detail').display
            app._last_read_at -= 6
            app._poll_current_view()
            await pilot.pause(.05)
            assert calls == ['jobs','jobs','job_accounts','allocation']
    asyncio.run(run())


def test_real_timer_pause_resume_and_failure_retry(job_client, monkeypatch):
    env, path, payload = job_client
    queries = Queries(build_parser().parse_args(['tui']), env)
    original = queries.read
    calls = []
    async def read(request):
        calls.append(request.view)
        return await original(request)
    queries.read = read
    monkeypatch.setattr(QueryApp,'REFRESH_SECONDS', {**QueryApp.REFRESH_SECONDS, 'jobs':.1})
    async def run():
        app = QueryApp(queries)
        async with app.run_test(size=(80,24)) as pilot:
            await loaded(app,pilot)
            await pilot.press('p')
            await pilot.pause(1.15)
            assert calls == ['jobs'] and app.snapshot is not None
            payload['errors'] = [{'description':'private native failure'}]
            path.write_text(json.dumps(payload))
            await pilot.press('p')
            for _ in range(25):
                await pilot.pause(.1)
                if len(calls) >= 2 and not app._reading:
                    break
            assert len(calls) == 2 and app.snapshot is None
            assert app.query_one('#job-table',DataTable).row_count == 0
            assert 'private native failure' not in str(app.query_one('#notice',Static).render())
            payload['errors'] = []
            path.write_text(json.dumps(payload))
            for _ in range(25):
                await pilot.pause(.1)
                if len(calls) >= 3 and not app._reading:
                    break
            assert calls == ['jobs'] * 3 and app.snapshot is not None
    asyncio.run(run())


@pytest.mark.parametrize('width',[40,100])
def test_node_expansion_updates_from_same_observation_without_extra_queries(resource_client, width):
    env, path, payload = resource_client
    payload['sinfo'][0]['gres']['used'] = 'gpu:example:2(IDX:1,3)'
    path.write_text(json.dumps(payload))
    def count():
        return len(Path(env['NATIVE_CALL']).read_text().splitlines())
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']),env))
        async with app.run_test(size=(width,30)) as pilot:
            await loaded(app,pilot)
            assert '全部分区' in str(app.query_one(Select).query_one('#label',Static).render())
            await pilot.press('enter')
            assert count() == 1 and app.query_one('#detail').display
            assert app._detail_node == 'node-a'
            assert '[1]' in html.unescape(app.export_screenshot())
            payload['sinfo'][0]['gres']['used'] = 'gpu:example:2(IDX:0,2)'
            path.write_text(json.dumps(payload))
            app._last_read_at -= 11
            app._poll_current_view(); await loaded(app,pilot)
            assert count() == 2 and app._detail_node == 'node-a'
            assert app.query_one('#detail').display
            assert app.snapshot.values['nodes'][0]['gpu']['allocated_indices'] == [0,2]
            await pilot.press('escape','3'); await loaded(app,pilot)
            await pilot.click('#resource-table',offset=(2,2))
            assert app.view == 'cpu' and app._detail_node == 'node-c'
            assert count() == 3 and app.query_one('#detail').display
    asyncio.run(run())


def test_disappearing_partition_does_not_silently_expand_scope(resource_client):
    env, path, payload = resource_client
    async def run():
        app = QueryApp(Queries(build_parser().parse_args(['tui']),env))
        async with app.run_test(size=(80,24)) as pilot:
            await loaded(app,pilot)
            app.query_one(Select).value = 'gpu-new'
            await pilot.pause()
            for node in payload['sinfo']:
                if node['partition']['name'] == 'gpu-new':
                    node['partition']['name'] = 'gpu-other'
            path.write_text(json.dumps(payload))
            app.action_refresh(); await loaded(app,pilot)
            assert app.selection == 'gpu-new'
            assert app.query_one('#resource-table',DataTable).row_count == 0
            assert not app.query_one('#detail').display
            assert 'gpu-other' not in str(app.query_one('#content',Static).render())
    asyncio.run(run())
