"""在线视频 URL：校验、探测、下载（yt-dlp）"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp

ProgressCallback = Callable[[float], None]

_STRIP_QUERY_KEYS = frozenset(
    {
        "spm",
        "from",
        "se",
        "share_source",
        "share_medium",
        "vd_source",
        "share_plat",
        "share_session_id",
        "share_tag",
        "unique_k",
        "t",
        "timestamp",
    }
)


def _base_ydl_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
    }


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast:
        return True
    return False


def validate_url_safe(url: str) -> None:
    """拒绝 SSRF：非 http(s)、localhost、内网 IP。"""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https 链接")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("链接无效")
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("不允许访问本地地址")

    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if _is_blocked_ip(host):
            raise ValueError("不允许访问内网或保留地址")
        return

    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as e:
        raise ValueError(f"无法解析域名: {host}") from e

    if not addrs:
        raise ValueError(f"无法解析域名: {host}")

    # 双栈 DNS 可能混有异常 AAAA（如 2001::1）；只要存在可达公网地址即放行
    if not any(not _is_blocked_ip(ip) for ip in addrs):
        raise ValueError("不允许访问内网或保留地址")


def normalize_url(url: str) -> str:
    """规范化 URL 供查重（去 tracking 参数、统一 scheme/host）。"""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    netloc = host
    if parsed.port and parsed.port not in (80, 443):
        netloc = f"{host}:{parsed.port}"
    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in qs.items() if k.lower() not in _STRIP_QUERY_KEYS}
    query = urlencode(filtered, doseq=True)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def probe_video(url: str) -> dict:
    """预取标题等信息，不下载。"""
    validate_url_safe(url)
    opts = {**_base_ydl_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    title = (info.get("title") or "在线视频").strip()
    title = re.sub(r'[\\/:*?"<>|]', "_", title)[:200]
    return {"title": title or "在线视频", "duration": info.get("duration")}


def download_video(
    url: str,
    dest_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """下载视频到 dest_dir，返回最终文件路径。"""
    validate_url_safe(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "dl_%(id)s.%(ext)s")

    def _hook(d: dict) -> None:
        if not on_progress or d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes") or 0
        if total > 0:
            pct = 10 + (downloaded / total) * 10
            on_progress(min(20.0, pct))

    opts = {
        **_base_ydl_opts(),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "progress_hooks": [_hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if not path.is_file():
            candidates = list(dest_dir.glob(f"dl_*{path.suffix}"))
            if candidates:
                path = candidates[0]
        if not path.is_file():
            raise FileNotFoundError("下载完成但未找到视频文件")
        return path
