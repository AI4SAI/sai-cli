import asyncio
import threading
import time

import pytest

pytest.importorskip('textual')
from textual.app import App
from textual.widgets import Button

from sai_cli.auth import TokenProvider
from sai_cli.config import Settings
from sai_cli.oidc import DeviceTokenResult, OidcClient
from sai_cli.transport import JsonTransport
from sai_cli.workbench_auth import DeviceLoginScreen
from test_cli_auth import _AuthHandler, _server


@pytest.mark.parametrize('cancel,newer_login', [(False, False), (True, False), (True, True)])
def test_device_login_reuses_http_protocol_and_cancellation_preserves_old_login(tmp_path, monkeypatch, cancel, newer_login):
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')
    started, release = threading.Event(), threading.Event()
    original = _AuthHandler.do_POST

    def held(handler):
        if handler.path == '/oauth/token':
            started.set()
            assert release.wait(5)
        original(handler)

    monkeypatch.setattr(_AuthHandler, 'do_POST', held)
    with _server() as (origin, server):
        settings = Settings(base_url=origin, site_id='site-a', timeout_seconds=3,
            allow_insecure_http=False, cache_path=tmp_path/'cache/token.json', use_cache=True,
            profile='default', credential_path=tmp_path/'data/credentials.json', identity_issuer=origin)
        transport = JsonTransport(base_url=origin, timeout_seconds=3)
        oidc = OidcClient(transport=transport, issuer_url=origin, client_id='sai-cli',
            scope='openid offline_access sai.compute.read', resource='https://portal.example.org')
        provider = TokenProvider(settings=settings, transport=transport, oidc_client=oidc, environ={})
        provider.install_device_tokens(DeviceTokenResult('prior-access', int(time.time())+300, 'prior-refresh', None))
        result = []

        class Harness(App):
            def on_mount(self):
                self.push_screen(DeviceLoginScreen(provider, 'zh-CN'), result.append)

        async def scenario():
            app = Harness()
            async with app.run_test(size=(40, 24)) as pilot:
                try:
                    for _ in range(100):
                        if started.is_set(): break
                        await pilot.pause(.02)
                    assert started.is_set()
                    picture = app.export_screenshot()
                    assert 'ABCD-EFGH' in picture
                    assert all(secret not in picture for secret in ['device-code-opaque', 'prior-access', 'prior-refresh', 'opaque-access-token', 'opaque-refresh-token'])
                    if cancel:
                        if newer_login:
                            provider.store_pending_device_code(device_code='newer-pending-device', expires_at=int(time.time()) + 300)
                        app.screen.query_one('#login-cancel', Button).focus()
                        await pilot.press('enter')
                        assert result == []
                finally:
                    release.set()
                for _ in range(100):
                    if result: break
                    await pilot.pause(.02)
                assert result == [not cancel]

        asyncio.run(scenario())
        assert provider.device_refresh()[0] == ('prior-refresh' if cancel else 'opaque-refresh-token')
        if newer_login:
            assert provider.pending_device_code()[0] == 'newer-pending-device'
        else:
            assert provider.pending_device_code() is None
        assert not any(call['path'] == '/oauth/revoke' for call in server.requests)
        assert settings.credential_path.stat().st_mode & 0o777 == 0o600
