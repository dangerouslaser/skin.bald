"""TvController: the only code that touches aiowebostv's WebOsClient.

Owns connection lifecycle (pairing, key storage, loopback fallback,
reconnect with backoff) and exposes the commands actions call. Everything
here runs on the service's asyncio loop thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from aiowebostv import WebOsClient, WebOsTvCommandError, WebOsTvPairError
from aiowebostv.buttons import BUTTONS

from . import kodilog as log
from . import discovery, luna, storage, wol
from .errors import BadRequest, CommandFailed, Disconnected
from .net import Backoff, discover_lan_ip
from .pairing import KeyStore
from .settings import Settings
from .state import TvState

RUNTIME_FILE = "runtime.json"
IDENTITY_FILE = "tv.json"
# Re-discovery runs at most this often while the TV is unreachable.
DISCOVERY_INTERVAL = 120.0
PICTURE_SETTINGS = "settings/getSystemSettings"
PICTURE_QUERY = {"category": "picture", "keys": ["pictureMode"]}
PRESET_VERIFY_TIMEOUT = 3.0
# Older webOS (e.g. 5.x on 2020 models) refuses to read picture settings
# over SSAP; these phrases in its error mean "not on this TV".
PICTURE_UNSUPPORTED_ERRORS = ("not allowed", "doesn't support", "does not support")
CONNECTION_ERRORS = (OSError, TimeoutError, aiohttp.ClientError, WebOsTvCommandError)
MEDIA_COMMANDS = {
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "rewind": "rewind",
    "fast_forward": "fast_forward",
    "fastforward": "fast_forward",
}


class TvController:
    """Connection owner and command surface for one webOS TV."""

    def __init__(
        self,
        settings: Settings,
        *,
        keystore: KeyStore | None = None,
        on_state: Callable[[TvState], None] | None = None,
        on_mac: Callable[[str], None] | None = None,
        on_host: Callable[[str], None] | None = None,
        discover: Callable[[], Awaitable[list[discovery.DiscoveredTv]]] = discovery.discover,
        notify: Callable[[str, str], None] | None = None,
        client_factory: Callable[..., WebOsClient] = WebOsClient,
        lan_ip: Callable[[], str | None] = discover_lan_ip,
        backoff_base: float = 2.0,
    ) -> None:
        self.settings = settings
        self.keystore = keystore or KeyStore()
        self._on_state = on_state or (lambda _s: None)
        # on_mac(mac): persist a MAC the TV reported (setting was empty).
        self._on_mac = on_mac or (lambda _m: None)
        # on_host(host): persist a host found by discovery to settings.
        self._on_host = on_host or (lambda _h: None)
        self._discover = discover
        self._last_discovery: float | None = None
        self._multi_tv_notified = False
        # notify(kind, message): kind is "info" or "error"; the service maps
        # it to a Kodi notification.
        self._notify = notify or (lambda _k, _m: None)
        self._client_factory = client_factory
        self._lan_ip = lan_ip
        self._backoff = Backoff(base=backoff_base, cap=settings.backoff_cap)
        self.client: WebOsClient | None = None
        self.active_host = settings.host
        self.state = TvState(host=settings.host)
        self.pairing_blocked = False
        self._connected = False
        self._stopping = False
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._failure_notified = False
        self._had_key = False
        self._expected_uuid: str | None = None
        self._firmware: tuple[WebOsClient, str] | None = None
        self.picture_preset = ""
        # None until known; False when the TV's webOS won't report picture
        # settings (presets then can't be read, listed or verified).
        self.picture_supported: bool | None = None
        # Callbacks run with the new preset name (automations track it).
        self.picture_listeners: list[Callable[[str], None]] = []
        # Callbacks run with every new TvState (the TV watcher uses them).
        self.state_listeners: list[Callable[[TvState], None]] = []

    # lifecycle -----------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected and self.client is not None and self.client.connection is not None

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="webostv-connection")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        await self._disconnect_client()
        self._set_connected(False)

    async def reconfigure(self, settings: Settings) -> None:
        """Apply new settings; reconnect if the target changed."""
        old = self.settings
        self.settings = settings
        self._backoff.cap = settings.backoff_cap
        if settings.host != old.host or settings.loopback_fallback != old.loopback_fallback:
            log.info(f"host changed {old.host} -> {settings.host}; reconnecting")
            storage.write_json(RUNTIME_FILE, {})
            self.pairing_blocked = False
            self._last_discovery = None
            self._multi_tv_notified = False
            await self._disconnect_client()
            self._backoff.reset()
            self._wake.set()

    async def repair(self) -> None:
        """Forget the stored key and reconnect (shows the TV prompt once)."""
        log.info("re-pair requested; deleting stored client key")
        self._forget_key()
        self.pairing_blocked = False
        self._failure_notified = False
        await self._disconnect_client()
        self._backoff.reset()
        self._wake.set()

    async def _run(self) -> None:
        while not self._stopping:
            if self.pairing_blocked:
                await self._wait_wake(None)
                continue
            if await self._connect_cycle():
                self._backoff.reset()
                await self._wait_disconnected()
                if self._stopping:
                    break
                log.info(f"disconnected from {self.active_host}")
                self._set_connected(False)
                # Reconnect immediately once: covers Kodi returning to the
                # foreground after the TV switched inputs/apps.
                continue
            if self.pairing_blocked or self._stopping:
                continue
            delay = self._backoff.next()
            log.debug(f"retrying in {delay:.0f}s")
            await self._wait_wake(delay)

    async def _wait_wake(self, timeout: float | None) -> None:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(timeout):
                await self._wake.wait()
        self._wake.clear()

    def _candidate_hosts(self) -> list[str]:
        configured = self.settings.host
        if not (self.settings.is_loopback and self.settings.loopback_fallback):
            return [configured]
        runtime = storage.read_json(RUNTIME_FILE, {}) or {}
        remembered = runtime.get("fallback_host") if runtime.get("for_host") == configured else None
        if remembered:
            return [remembered, configured]
        return [configured, "__lan__"]

    async def _connect_cycle(self) -> bool:
        """Try each candidate host once. Return True when connected."""
        self._wake.clear()
        for index, host in enumerate(self._candidate_hosts()):
            if host == "__lan__":
                host = self._lan_ip()
                if not host:
                    log.warning("loopback refused and no LAN IP found for fallback")
                    break
                log.info(f"loopback refused; falling back to LAN IP {host}")
            try:
                await self._connect(host)
            except WebOsTvPairError as err:
                self._handle_pair_error(err)
                return False
            except asyncio.CancelledError:
                raise
            except CONNECTION_ERRORS as err:
                if self._pairing_timed_out():
                    self._block_pairing("Pairing timed out on the TV")
                    return False
                log.debug(f"connect to {host} failed: {err!r}")
                if index == 0 and not self._failure_notified:
                    log.warning(f"cannot reach TV at {host}: {err!r}")
                continue
            self._remember_host(host)
            return True
        if not self.pairing_blocked and await self._try_discovery():
            return True
        if self.pairing_blocked:
            return False
        if not self._failure_notified:
            self._failure_notified = True
            if self.settings.toast_on_connect:
                self._notify("error", f"Cannot reach TV at {self.settings.host}")
        self._set_connected(False)
        return False

    async def _connect(self, host: str, uuid: str | None = None) -> None:
        await self._disconnect_client()
        # A key follows the TV's UUID, so a TV picked with Find TV or found
        # at a new IP reuses its pairing instead of prompting again.
        self._expected_uuid = uuid or discovery.hinted_uuid(host)
        key = self.keystore.get(self.settings.host) or (
            self.keystore.get_uuid(self._expected_uuid) if self._expected_uuid else None
        )
        self._had_key = key is not None
        self.active_host = host
        client = self._client_factory(
            host, client_key=key, connect_timeout=self.settings.connect_timeout
        )
        self.client = client
        await client.register_state_update_callback(self._on_client_state)
        log.debug(f"connecting to {host} (paired={key is not None})")
        if not await client.connect():
            # disconnect() raced the attempt (re-pair, settings change, stop)
            raise ConnectionError("connect cancelled")
        tv_uuid = str(client.tv_info.hello.get("deviceUUID") or "").lower()
        if uuid and tv_uuid and tv_uuid != uuid.lower():
            await self._disconnect_client()
            error = f"{host} is a different TV ({tv_uuid})"
            raise ConnectionError(error)
        if client.client_key and client.client_key != key:
            log.info("pairing accepted; client key stored")
        if client.client_key:
            self.keystore.set(self.settings.host, client.client_key)
            if tv_uuid:
                self.keystore.set_uuid(tv_uuid, client.client_key)
        if tv_uuid:
            storage.write_json(IDENTITY_FILE, {"host": self.settings.host, "uuid": tv_uuid})
        self._failure_notified = False
        log.info(f"connected to {host}")
        self._learn_mac(client)
        await self._subscribe_picture(client)
        self._set_connected(True)
        if self.settings.toast_on_connect:
            self._notify("info", f"Connected to TV at {host}")

    def _learn_mac(self, client: WebOsClient) -> None:
        """Fill the MAC setting from the TV's own report, if it's empty."""
        if self.settings.mac:
            return
        mac = reported_mac(client.tv_info.connection)
        if not mac:
            return
        log.info(f"learned TV MAC address {mac}")
        self.settings = dataclasses.replace(self.settings, mac=mac)
        try:
            self._on_mac(mac)
        except Exception as err:  # noqa: BLE001
            log.warning(f"could not save MAC address: {err!r}")

    def _pairing_timed_out(self) -> bool:
        client = self.client
        return (
            client is not None
            and not self._had_key
            and bool(client.tv_info.hello)
            and not client.client_key
        )

    def _forget_key(self) -> None:
        self.keystore.delete(self.settings.host)
        for uuid in {self._known_uuid(), self._expected_uuid, discovery.hinted_uuid(self.settings.host)}:
            if uuid:
                self.keystore.delete(f"uuid:{uuid.lower()}")

    def _known_uuid(self) -> str | None:
        """UUID of the TV last connected for the configured host."""
        identity = storage.read_json(IDENTITY_FILE, {}) or {}
        if identity.get("host") == self.settings.host and identity.get("uuid"):
            return str(identity["uuid"])
        return None

    async def _try_discovery(self) -> bool:
        """Find the TV with SSDP when the configured host is unreachable.

        - Known TV (UUID recorded): accept only a TV with that UUID, at a
          new IP, and reuse its key; never prompts on another TV.
        - First run (default loopback host, nothing ever paired): accept a
          single discovered TV; its pairing prompt is the confirmation.
        On success the new host is written to settings.
        """
        if not self.settings.auto_discover:
            return False
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_discovery is not None and now - self._last_discovery < DISCOVERY_INTERVAL:
            return False
        self._last_discovery = now

        known = self._known_uuid()
        first_run = self.settings.is_loopback and self.keystore.is_empty()
        if not known and not first_run:
            return False

        found = await self._discover()
        if found:
            discovery.remember(found)
        if known:
            matches = [tv for tv in found if tv.uuid == known.lower()]
            target = next((tv for tv in matches if tv.host != self.active_host), None)
            if target is None:
                log.debug(f"discovery: paired TV {known} not found at a new address")
                return False
            log.info(f"paired TV found at new address {target.host}")
        else:
            if len(found) != 1:
                if len(found) > 1 and not self._multi_tv_notified:
                    self._multi_tv_notified = True
                    self._notify("info", f"Found {len(found)} TVs; choose one with Find TV in settings")
                log.info(f"discovery found {len(found)} TVs; not choosing automatically")
                return False
            target = found[0]
            log.info(f"discovered {target.name} at {target.host}; pairing")

        try:
            await self._connect(target.host, uuid=target.uuid)
        except WebOsTvPairError as err:
            self._handle_pair_error(err)
            return False
        except asyncio.CancelledError:
            raise
        except CONNECTION_ERRORS as err:
            if self._pairing_timed_out():
                self._block_pairing("Pairing timed out on the TV")
            else:
                log.debug(f"connect to discovered {target.host} failed: {err!r}")
            return False
        self._adopt_host(target.host)
        return True

    def _adopt_host(self, host: str) -> None:
        """Make a discovered host the configured one, keeping the key."""
        old = self.settings.host
        key = self.client.client_key if self.client else None
        self.settings = dataclasses.replace(self.settings, host=host)
        if key:
            self.keystore.set(host, key)
        identity = storage.read_json(IDENTITY_FILE, {}) or {}
        if identity.get("uuid"):
            storage.write_json(IDENTITY_FILE, {"host": host, "uuid": identity["uuid"]})
        storage.write_json(RUNTIME_FILE, {})
        log.info(f"host setting updated {old} -> {host}")
        try:
            self._on_host(host)
        except Exception as err:  # noqa: BLE001
            log.warning(f"could not save host setting: {err!r}")
        self._publish()

    def _handle_pair_error(self, err: WebOsTvPairError) -> None:
        if self._had_key:
            self._forget_key()
            self._block_pairing("Stored pairing key was rejected; use Re-pair")
        else:
            self._block_pairing(f"Pairing declined ({err})")

    def _block_pairing(self, message: str) -> None:
        log.warning(message)
        self.pairing_blocked = True
        self._notify("error", message)
        self._set_connected(False)

    def _remember_host(self, host: str) -> None:
        if not self.settings.is_loopback:
            return
        if host == self.settings.host:
            storage.write_json(RUNTIME_FILE, {})
        else:
            log.info(f"using {host} instead of {self.settings.host}")
            storage.write_json(RUNTIME_FILE, {"for_host": self.settings.host, "fallback_host": host})

    async def _wait_disconnected(self) -> None:
        client = self.client
        task = client.connect_task if client else None
        if task is None:
            return
        await asyncio.wait({task})
        if not task.cancelled() and task.exception() is not None:
            log.debug(f"connection ended: {task.exception()!r}")

    async def _disconnect_client(self) -> None:
        client = self.client
        if client is None:
            return
        self._connected = False
        with contextlib.suppress(Exception):
            await client.disconnect()

    # state ---------------------------------------------------------------

    def _set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._publish()

    async def _on_client_state(self, _tv_state: Any) -> None:
        self._publish()

    def _publish(self) -> None:
        client = self.client
        connected = self.connected
        if client is not None:
            snapshot = TvState.from_client(
                client.tv_state,
                connected=connected,
                paired=self.keystore.get(self.settings.host) is not None,
                host=self.active_host,
                picture_preset=self.picture_preset if connected else "",
                picture_supported=self.picture_supported if connected else None,
                model=str((client.tv_info.system or {}).get("modelName") or ""),
            )
        else:
            snapshot = TvState(
                host=self.active_host,
                paired=self.keystore.get(self.settings.host) is not None,
            )
        self.state = snapshot
        try:
            self._on_state(snapshot)
        except Exception as err:  # noqa: BLE001
            log.error(f"state publish failed: {err!r}")
        for listener in list(self.state_listeners):
            try:
                listener(snapshot)
            except Exception as err:  # noqa: BLE001
                log.warning(f"state listener failed: {err!r}")

    # commands ------------------------------------------------------------

    def _require(self) -> WebOsClient:
        if not self.connected or self.client is None:
            raise Disconnected
        return self.client

    async def _call(self, method: str, *args: Any) -> Any:
        client = self._require()
        try:
            return await getattr(client, method)(*args)
        except WebOsTvCommandError as err:
            log.warning(f"{method} failed: {err}")
            raise CommandFailed(str(err)) from err
        except (OSError, aiohttp.ClientError) as err:
            raise Disconnected(str(err)) from err

    async def power_off(self) -> None:
        await self._call("power_off")

    async def power_on(self) -> None:
        if self.connected and not self.state.screen_on and self.state.is_on:
            await self._call("set_screen_state", True)
            return
        if not self.settings.mac:
            raise BadRequest("power_on needs the TV MAC address (off-TV mode)")
        try:
            wol.send_magic_packet(self.settings.mac)
        except ValueError as err:
            raise BadRequest(str(err)) from err
        log.info("sent Wake-on-LAN packet")
        self._backoff.reset()
        self._wake.set()

    async def screen(self, on: bool) -> None:
        await self._call("set_screen_state", on)

    async def volume(self, value: int | str) -> None:
        if value == "up":
            await self._call("volume_up")
        elif value == "down":
            await self._call("volume_down")
        else:
            await self._call("set_volume", int(value))

    async def mute(self, mode: str) -> None:
        if mode == "toggle":
            client = self._require()
            muted = not bool(client.tv_state.muted)
        else:
            muted = mode == "on"
        await self._call("set_mute", muted)

    def resolve_input(self, query: str) -> str:
        self._require()
        q = query.casefold()
        for input_id, label, app_id in self.state.inputs:
            if q in (input_id.casefold(), label.casefold(), app_id.casefold()):
                return input_id
        raise BadRequest(f"unknown input: {query}")

    async def set_input(self, query: str) -> str:
        input_id = self.resolve_input(query)
        await self._call("set_input", input_id)
        return input_id

    def resolve_app(self, query: str) -> str:
        self._require()
        q = query.casefold()
        apps = self.state.apps
        for app_id, title in apps:
            if q == app_id.casefold() or q == title.casefold():
                return app_id
        partial = [app_id for app_id, title in apps if q in app_id.casefold() or q in title.casefold()]
        if len(partial) == 1:
            return partial[0]
        if partial:
            raise BadRequest(f"ambiguous app {query!r}: {', '.join(sorted(partial))}")
        raise BadRequest(f"unknown app: {query}")

    async def launch_app(self, query: str, params: dict[str, Any] | None = None) -> str:
        app_id = self.resolve_app(query)
        if params:
            await self._call("launch_app_with_params", app_id, params)
        else:
            await self._call("launch_app", app_id)
        return app_id

    async def sound_output(self, output: str) -> None:
        await self._call("change_sound_output", output)

    async def button(self, name: str) -> None:
        name = name.upper()
        if name not in BUTTONS:
            raise BadRequest(f"unknown button: {name}")
        await self._call("button", name)

    async def toast(self, message: str) -> None:
        await self._call("send_message", message)

    async def media(self, command: str) -> None:
        method = MEDIA_COMMANDS.get(command)
        if method is None:
            raise BadRequest(f"unknown media command: {command}")
        await self._call(method)

    async def channel(self, value: str) -> None:
        if value == "up":
            await self._call("channel_up")
        elif value == "down":
            await self._call("channel_down")
        else:
            await self._call("set_channel", value)

    async def command(self, uri: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        uri = uri.removeprefix("ssap://")
        return await self._call("request", uri, payload)

    # picture (phase 2) ---------------------------------------------------

    async def _subscribe_picture(self, client: WebOsClient) -> None:
        async def on_picture(payload: dict[str, Any]) -> None:
            mode = str(((payload or {}).get("settings") or {}).get("pictureMode") or "")
            if mode and mode != self.picture_preset:
                self.picture_preset = mode
                log.debug(f"picture mode is {mode}")
                self._publish()
                for listener in list(self.picture_listeners):
                    try:
                        listener(mode)
                    except Exception as err:  # noqa: BLE001
                        log.warning(f"picture listener failed: {err!r}")

        try:
            await client.subscribe(on_picture, PICTURE_SETTINGS, dict(PICTURE_QUERY))
        except Exception as err:  # noqa: BLE001
            if _picture_unsupported(err):
                self._mark_picture_unsupported()
            else:
                log.warning(f"cannot follow picture mode: {err!r}")
        else:
            self.picture_supported = True
            self._publish()

    def _mark_picture_unsupported(self) -> None:
        if self.picture_supported is not False:
            log.info("this TV's webOS doesn't allow reading picture settings; picture presets are off")
        self.picture_supported = False
        self._publish()

    def _require_picture(self) -> None:
        if self.picture_supported is False:
            raise BadRequest("picture presets aren't available on this TV's webOS version")

    async def picture_modes(self) -> list[dict[str, Any]]:
        """Picture modes the TV knows, from getSystemSettingDesc.

        Each item: {"value", "visible"}; "visible" means selectable for the
        current signal (SDR names while showing SDR, and so on).
        """
        self._require_picture()
        try:
            res = await self._call(
                "request", "settings/getSystemSettingDesc",
                {"category": "picture", "keys": ["pictureMode"]},
            )
        except CommandFailed as err:
            if _picture_unsupported(err):
                self._mark_picture_unsupported()
                self._require_picture()
            raise
        return _modes_from_desc(res)

    async def get_picture_mode(self) -> str:
        self._require_picture()
        res = await self._call("request", PICTURE_SETTINGS, dict(PICTURE_QUERY))
        mode = str((res.get("settings") or {}).get("pictureMode") or "")
        if mode:
            self.picture_preset = mode
        return mode

    async def set_picture_mode(self, mode: str) -> str:
        """Set the picture mode and confirm the TV applied it."""
        client = self._require()
        self._require_picture()
        mode = mode.strip()
        if not mode:
            raise BadRequest("missing picture preset")
        if self.picture_preset == mode:
            return mode

        async def request(uri: str, payload: dict[str, Any] | None) -> dict[str, Any]:
            try:
                return await client.request(uri, payload)
            except WebOsTvCommandError as err:
                raise CommandFailed(str(err)) from err

        try:
            await luna.set_picture_settings(request, {"pictureMode": mode})
        except CommandFailed:
            raise
        except RuntimeError as err:
            raise CommandFailed(str(err)) from err
        except (OSError, aiohttp.ClientError) as err:
            raise Disconnected(str(err)) from err

        # The luna call reports nothing; read back until it sticks.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + PRESET_VERIFY_TIMEOUT
        current = ""
        while loop.time() < deadline:
            current = await self.get_picture_mode()
            if current == mode:
                log.info(f"picture mode set to {mode}")
                self._publish()
                return mode
            await asyncio.sleep(0.2)
        error = f"TV did not apply picture preset {mode!r} (still {current!r})"
        log.warning(error)
        raise CommandFailed(error)

    async def firmware(self) -> str:
        """Firmware version string, cached per connection.

        getCurrentSWInformation returns 401 on newer firmware (webOS 10+),
        so fall back to the tv.nyx.* config values, which stay readable.
        """
        client = self._require()
        if self._firmware is not None and self._firmware[0] is client:
            return self._firmware[1]
        text = ""
        software = client.tv_info.software
        if not software:
            with contextlib.suppress(CommandFailed):
                software = await self._call("get_software_info")
        if software:
            text = " ".join(
                str(software.get(k, "")) for k in ("product_name", "major_ver", "minor_ver")
            ).strip()
        if not text:
            with contextlib.suppress(CommandFailed):
                res = await self._call(
                    "request",
                    "config/getConfigs",
                    {"configNames": ["tv.nyx.firmwareVersion", "tv.nyx.platformVersion"]},
                )
                configs = res.get("configs") or {}
                version = configs.get("tv.nyx.firmwareVersion", "")
                platform = configs.get("tv.nyx.platformVersion", "")
                text = f"{version} (webOS {platform})" if version and platform else version
        self._firmware = (client, text)
        return text

    def status(self) -> dict[str, Any]:
        client = self.client
        system = client.tv_info.system if client else {}
        firmware = ""
        if self._firmware is not None and self._firmware[0] is client:
            firmware = self._firmware[1]
        return {
            "host": self.active_host,
            "configured_host": self.settings.host,
            "connected": self.connected,
            "paired": self.keystore.get(self.settings.host) is not None,
            "pairing_blocked": self.pairing_blocked,
            "model": system.get("modelName", "") if system else "",
            "firmware": firmware,
            "power": self.state.power,
            "volume": self.state.volume,
            "muted": self.state.muted,
            "app": self.state.app_id,
            "input": self.state.input_id,
            "sound_output": self.state.sound_output,
            "picture_preset": self.state.picture_preset,
        }

    def launch_points(self) -> dict[str, Any]:
        """Apps in the TV's launcher order and inputs, with icon URLs."""
        client = self._require()
        apps = [
            {"id": str(app_id), "title": str(app.get("title") or app_id), "icon": _icon(app),
             "color": str(app.get("bgColor") or "")}
            for app_id, app in (client.tv_state.apps or {}).items()
            if isinstance(app, dict) and not app.get("hidden")
        ]
        inputs = [
            {"id": str(i.get("id", "")), "title": str(i.get("label") or i.get("id", "")),
             "icon": _icon(i), "connected": bool(i.get("connected", True))}
            for i in (client.tv_state.inputs or {}).values()
            if isinstance(i, dict)
        ]
        return {"host": self.active_host, "apps": apps, "inputs": inputs,
                "current_app": self.state.app_id}

    def catalog(self) -> dict[str, Any]:
        self._require()
        return {
            "inputs": [{"id": i, "label": label, "app_id": a} for i, label, a in self.state.inputs],
            "apps": sorted(
                ({"id": a, "title": t} for a, t in self.state.apps),
                key=lambda app: app["title"].casefold(),
            ),
            "current_app": self.state.app_id,
            "sound_output": self.state.sound_output,
        }


def _picture_unsupported(err: BaseException) -> bool:
    text = str(err).casefold()
    return any(phrase in text for phrase in PICTURE_UNSUPPORTED_ERRORS)


def _modes_from_desc(res: dict[str, Any]) -> list[dict[str, Any]]:
    modes = []
    for result in res.get("results") or []:
        if result.get("key") != "pictureMode":
            continue
        values = (result.get("values") or {}).get("arrayExt") or []
        for item in values:
            if isinstance(item, dict) and item.get("value") and item.get("active", True):
                modes.append({"value": str(item["value"]), "visible": bool(item.get("visible"))})
    return modes


def _icon(item: dict[str, Any]) -> str:
    for key in ("largeIcon", "mediumLargeIcon", "extraLargeIcon", "icon"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return ""


def reported_mac(connection: dict[str, Any] | None) -> str:
    """Pick the MAC from connectionmanager/getinfo, preferring wired."""
    for key in ("wiredInfo", "wifiInfo"):
        mac = ((connection or {}).get(key) or {}).get("macAddress", "")
        try:
            wol.parse_mac(mac)
        except ValueError:
            continue
        return mac.upper()
    return ""
