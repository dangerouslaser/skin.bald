from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


class ConfigError(ValueError):
    pass


def _base_url(server: str) -> tuple[str, str]:
    value = server.strip().rstrip("/")
    if not value:
        raise ConfigError("Enter the Xtream Codes server URL.")
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError("The server must be a valid HTTP or HTTPS URL.")
    if parsed.query or parsed.fragment:
        raise ConfigError("Enter only the server base URL, without a query or fragment.")
    base_path = parsed.path.rstrip("/")
    origin = urlunsplit((parsed.scheme, parsed.netloc, base_path, "", ""))
    return origin, base_path


def build_urls(server: str, username: str, password: str, output: str = "ts") -> tuple[str, str]:
    user = username.strip()
    secret = password.strip()
    if not user or not secret:
        raise ConfigError("Enter both the Xtream Codes username and password.")
    if output not in ("ts", "m3u8"):
        raise ConfigError("Stream output must be TS or M3U8.")
    origin, _ = _base_url(server)
    auth = {"username": user, "password": secret}
    playlist = f"{origin}/get.php?{urlencode({**auth, 'type': 'm3u_plus', 'output': output})}"
    epg = f"{origin}/xmltv.php?{urlencode(auth)}"
    return playlist, epg


def build_api_url(server: str, username: str, password: str, action: str) -> str:
    user = username.strip()
    secret = password.strip()
    if not user or not secret:
        raise ConfigError("Enter both the Xtream Codes username and password.")
    origin, _ = _base_url(server)
    return f"{origin}/player_api.php?{urlencode({'username': user, 'password': secret, 'action': action})}"


def build_m3u(server: str, username: str, password: str, output: str, categories: list[dict], streams: list[dict]) -> str:
    if output not in ("ts", "m3u8"):
        raise ConfigError("Stream output must be TS or M3U8.")
    origin, _ = _base_url(server)
    user = quote(username.strip(), safe="")
    secret = quote(password.strip(), safe="")
    groups = {str(item.get("category_id", "")): str(item.get("category_name", "")) for item in categories}
    lines = ["#EXTM3U"]
    for item in streams:
        stream_id = str(item.get("stream_id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not stream_id or not name:
            continue
        def clean(value: object) -> str:
            return str(value or "").replace('"', "'").replace("\r", " ").replace("\n", " ")
        epg_id = clean(item.get("epg_channel_id"))
        icon = clean(item.get("stream_icon"))
        group = clean(groups.get(str(item.get("category_id", "")), ""))
        label = clean(name)
        lines.append(f'#EXTINF:-1 tvg-id="{epg_id}" tvg-name="{label}" tvg-logo="{icon}" group-title="{group}",{label}')
        direct = str(item.get("direct_source", "")).strip()
        lines.append(direct if direct.startswith(("http://", "https://")) else f"{origin}/live/{user}/{secret}/{quote(stream_id, safe='')}.{output}")
    if len(lines) == 1:
        raise ConfigError("The XC API returned no usable live channels.")
    return "\n".join(lines) + "\n"


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "***" if key in ("username", "password") else value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
