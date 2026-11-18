"""時計・バッテリー・Wi-Fi などの状態を集める。読めないものは None を返す。"""
import glob
import os
import socket
import subprocess


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def battery(root="/sys/class/power_supply"):
    """(残量%, 充電中か) を返す。バッテリーが見つからなければ (None, False)。"""
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        if _read(os.path.join(d, "type")) != "Battery":
            continue
        cap = _read(os.path.join(d, "capacity"))
        status = _read(os.path.join(d, "status")) or ""
        if cap is not None and cap.lstrip("-").isdigit():
            return max(0, min(100, int(cap))), status in ("Charging", "Full")
    return None, False


def wifi_quality(text=None, iface="wlan0"):
    """/proc/net/wireless からリンク品質 0〜100 を返す。未接続なら None。"""
    if text is None:
        text = _read("/proc/net/wireless") or ""
    for line in text.splitlines():
        if line.strip().startswith(iface + ":"):
            parts = line.split()
            try:
                q = float(parts[2].rstrip("."))
            except (IndexError, ValueError):
                return None
            return max(0, min(100, int(q * 100 / 70)))
    return None


def wifi_ssid(iface="wlan0"):
    try:
        out = subprocess.run(["iw", "dev", iface, "link"], capture_output=True, text=True,
                             timeout=2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            return line[5:].strip()
    return None


def ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))   # 実際には送信しない。経路から自分の IP を知るため
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def cpu_temp():
    t = _read("/sys/class/thermal/thermal_zone0/temp")
    return int(t) / 1000 if t and t.isdigit() else None


def load_avg():
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


def mem_used_percent(text=None):
    if text is None:
        text = _read("/proc/meminfo") or ""
    info = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if v:
            info[k] = int(v.split()[0])
    if "MemTotal" in info and "MemAvailable" in info:
        return 100 * (info["MemTotal"] - info["MemAvailable"]) / info["MemTotal"]
    return None
