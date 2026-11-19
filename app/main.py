#!/usr/bin/env python3
"""上画面アプリ。

  sudo python3 app/main.py            # 実機: 外付け液晶に表示、タッチで操作
  python3 app/main.py --preview out   # 実機なし: 各ページを PNG に書き出す
"""
import argparse
import datetime
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import status  # noqa: E402
import ui  # noqa: E402


def collect():
    bat, chg = status.battery()
    return {"now": datetime.datetime.now(), "bat": bat, "charging": chg,
            "wifi": status.wifi_quality(), "ssid": status.wifi_ssid(), "ip": status.ip_address(),
            "temp": status.cpu_temp(), "load": status.load_avg(), "mem": status.mem_used_percent()}


def preview(outdir):
    from drm import PngDisplay
    os.makedirs(outdir, exist_ok=True)
    app = ui.App()
    st = ui.sample_status()
    from touch import TouchEvent
    paint = app.pages[2]
    for x in range(40, 280, 6):   # お絵描きページにサンプルの線を描いておく
        paint.touch(TouchEvent("move" if x > 40 else "down", x, 80 + int(30 * ((x / 40) % 2))))
    paint.touch(TouchEvent("up", 280, 80))
    for i, p in enumerate(app.pages):
        app.select(i)
        PngDisplay(os.path.join(outdir, "page_%d_%s.png" % (i, p.title.lower()))).show(app.render(st))
    print("preview written to", outdir)


class StatusPoller:
    """状態の収集 (iw コマンドの起動など) は遅いので、別スレッドで数秒ごとに行う。
    描画ループはタッチを待つことだけに専念させる。"""

    def __init__(self, interval=3.0):
        import threading
        self.interval = interval
        self.data = collect()
        self.version = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            time.sleep(self.interval)
            try:
                self.data = collect()
                self.version += 1
            except Exception as e:   # 状態が読めなくても画面は止めない
                print("status:", e, file=sys.stderr)


def run(fps):
    from drm import DrmDisplay
    from touch import TouchReader
    disp = DrmDisplay()
    try:
        touch = TouchReader()
    except OSError as e:
        print("タッチなしで起動:", e, file=sys.stderr)
        touch = None
    app = ui.App()
    poller = StatusPoller()
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    seen_version = -1
    last_sec = None
    min_frame = 1 / fps
    last_draw = 0.0
    try:
        while not stop:
            now = time.time()
            # 次の秒の切り替わりまで、タッチを待つ (触ればすぐ起きる)
            timeout = 1.0 - (now % 1.0)
            events = touch.wait(timeout) if touch else (time.sleep(timeout) or [])
            dirty = False
            for ev in events:
                dirty |= bool(app.touch(ev)) or ev.kind != "move" or app.page.title == "TOUCH"
            sec = int(time.time())
            if sec != last_sec:
                last_sec = sec
                dirty = True
            if poller.version != seen_version:
                seen_version = poller.version
                dirty = True
            if not dirty:
                continue
            # 指でなぞっている間は描画を fps までに抑え、その間のイベントはまとめて反映する
            wait = min_frame - (time.monotonic() - last_draw)
            if wait > 0 and events and events[-1].kind == "move":
                time.sleep(wait)
                for ev in (touch.wait(0) if touch else []):
                    app.touch(ev)
            st = dict(poller.data)
            st["now"] = datetime.datetime.now()
            disp.show(app.render(st))
            last_draw = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", metavar="DIR", help="実機なしで各ページを PNG に書き出す")
    ap.add_argument("--fps", type=float, default=20)
    a = ap.parse_args()
    preview(a.preview) if a.preview else run(a.fps)
