"""Browser-confirmed login using the existing Identity device flow and store."""
from __future__ import annotations

import asyncio
from webbrowser import Error as BrowserError

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .auth import TokenProvider
from .errors import AuthenticationError
from .oidc import DeviceAuthorization, OidcPending, OidcSlowDown


class DeviceLoginScreen(ModalScreen[bool]):
    BINDINGS = [Binding('escape', 'cancel', show=False, priority=True)]
    DEFAULT_CSS = '''
    DeviceLoginScreen { align: center middle; }
    #login-dialog { width: 68; max-width: 100%; height: auto; max-height: 100%; padding: 1; background: $surface; }
    #login-title { height: 1; text-style: bold; }
    #login-link, #login-code, #login-status { height: auto; margin-bottom: 1; }
    #login-actions { height: 3; }
    #login-actions Button { width: 1fr; min-width: 0; }
    '''

    def __init__(self, provider: TokenProvider, language: str):
        super().__init__()
        self.provider, self.language = provider, language
        self.authorization: DeviceAuthorization | None = None
        self.cancelled = asyncio.Event()
        self.busy = self.quitting = False
        self._operation: asyncio.Task[bool] | None = None

    def t(self, zh: str, en: str) -> str:
        return zh if self.language == 'zh-CN' else en

    def compose(self) -> ComposeResult:
        with Vertical(id='login-dialog'):
            yield Static(self.t('登录 SAI', 'Sign in to SAI'), id='login-title', markup=False)
            yield Static('', id='login-link', markup=False)
            yield Static('', id='login-code', markup=False)
            yield Static('', id='login-status', markup=False)
            with Horizontal(id='login-actions'):
                yield Button(self.t('打开登录页', 'Open sign-in'), id='login-open', variant='primary', disabled=True)
                yield Button(self.t('复制链接', 'Copy link'), id='login-copy', disabled=True)
                yield Button(self.t('重试', 'Retry'), id='login-retry')
                yield Button(self.t('返回', 'Back'), id='login-cancel')

    def on_mount(self) -> None:
        self._start()

    def _start(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.cancelled.clear()
        self.query_one('#login-retry', Button).display = False
        self.query_one('#login-status', Static).update(self.t('正在准备登录…', 'Preparing sign-in…'))
        self.run_worker(self._perform(), group='device-login')

    def _clear_pending(self) -> None:
        if self.authorization is not None:
            self.provider.clear_pending_device_code(device_code=self.authorization.device_code)

    async def _exchange(self) -> bool:
        try:
            self.authorization = await asyncio.to_thread(self.provider.start_device_authorization)
            auth = self.authorization
            if self.cancelled.is_set():
                return False
            self.query_one('#login-link', Static).update(Text(auth.verification_url, style=f'link {auth.verification_url}', overflow='fold'))
            self.query_one('#login-code', Static).update(self.t('在浏览器确认设备码：', 'Confirm this code in your browser: ') + auth.user_code)
            self.query_one('#login-status', Static).update(self.t('等待浏览器确认，完成后会自动返回。', 'Waiting for confirmation. Your work opens when you finish.'))
            for name in ('login-open', 'login-copy'):
                self.query_one('#' + name, Button).disabled = False
            self.query_one('#login-open', Button).focus()
            interval = auth.interval_seconds
            while int(self.provider.clock()) < auth.expires_at and not self.cancelled.is_set():
                try:
                    result = await asyncio.to_thread(self.provider.poll_device_token, device_code=auth.device_code)
                except OidcPending:
                    result = None
                except OidcSlowDown:
                    interval = min(30, interval + 5)
                    result = None
                if self.cancelled.is_set():
                    return False
                if result is not None:
                    await asyncio.to_thread(self._clear_pending)
                    await asyncio.to_thread(self.provider.install_device_tokens, result)
                    return True
                try:
                    await asyncio.wait_for(self.cancelled.wait(), timeout=interval)
                except TimeoutError:
                    pass
            if not self.cancelled.is_set():
                raise AuthenticationError('Device authorization expired')
            return False
        finally:
            await asyncio.to_thread(self._clear_pending)

    async def _perform(self) -> None:
        self._operation = asyncio.create_task(self._exchange())
        result = False
        failed = False
        try:
            result = await asyncio.shield(self._operation)
        except asyncio.CancelledError:
            self.cancelled.set()
            try:
                await self._operation
            except Exception:
                pass
            raise
        except Exception:
            failed = True
        finally:
            self.busy = False
        if not self.is_mounted:
            return
        if self.quitting:
            self.app.exit()
        elif result or self.cancelled.is_set():
            self.dismiss(result)
        elif failed:
            self.authorization = None
            for name in ('login-open', 'login-copy'):
                self.query_one('#' + name, Button).disabled = True
            self.query_one('#login-link', Static).update('')
            self.query_one('#login-code', Static).update('')
            self.query_one('#login-status', Static).update(self.t('登录未完成，请重试。', 'Sign-in did not finish. Please retry.'))
            self.query_one('#login-retry', Button).display = True
            self.query_one('#login-retry', Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == 'login-cancel':
            self.action_cancel()
        elif event.button.id == 'login-retry':
            self._start()
        elif self.authorization is not None:
            if event.button.id == 'login-copy':
                self.app.copy_to_clipboard(self.authorization.verification_url)
            elif event.button.id == 'login-open':
                try:
                    self.app.open_url(self.authorization.verification_url)
                except (BrowserError, OSError):
                    self.query_one('#login-status', Static).update(self.t('可以点击上方链接，或复制到浏览器。', 'Use the link above, or copy it to your browser.'))

    def action_cancel(self, *, quit_app: bool = False) -> None:
        self.quitting = self.quitting or quit_app
        self.cancelled.set()
        if self.busy:
            self.query_one('#login-status', Static).update(self.t('正在返回…', 'Returning…'))
        elif self.quitting:
            self.app.exit()
        else:
            self.dismiss(False)

    async def on_unmount(self) -> None:
        self.cancelled.set()
        if self._operation is not None:
            try:
                await asyncio.shield(self._operation)
            except Exception:
                pass
