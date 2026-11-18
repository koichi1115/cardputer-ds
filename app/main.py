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
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    st = collect()
    st_time = time.monotonic()
    last_touch = 0.0
    try:
        while not stop:
            t0 = time.monotonic()
            if t0 - st_time >= 2:
                st = collect()
                st_time = t0
            st["now"] = datetime.datetime.now()
            events = touch.poll() if touch else []
            for ev in events:
                app.touch(ev)
            if events:
                last_touch = t0
            disp.show(app.render(st))
            # 触っている間は fps どおり、2秒触らなければ 4fps に落として CPU と SPI を空ける
            period = 1 / fps if t0 - last_touch < 2 else 0.25
            time.sleep(max(0.0, period - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", metavar="DIR", help="実機なしで各ページを PNG に書き出す")
    ap.add_argument("--fps", type=float, default=15)
    a = ap.parse_args()
    preview(a.preview) if a.preview else run(a.fps)
