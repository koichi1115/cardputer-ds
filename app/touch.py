"""タッチ (ADS7846) を読んで、画面座標のイベントにする。"""
import json
import os
import queue
import threading

DEFAULT_CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "touch", "touch_cal.json")


class Calibration:
    def __init__(self, cal):
        self.c = cal

    @classmethod
    def load(cls, path=DEFAULT_CAL):
        with open(path) as f:
            return cls(json.load(f))

    def to_screen(self, rx, ry):
        c = self.c
        a, b = (ry, rx) if c["swap_xy"] else (rx, ry)
        x = (c["x_raw_left"] - a) * c["width"] / (c["x_raw_left"] - c["x_raw_right"])
        y = (c["y_raw_top"] - b) * c["height"] / (c["y_raw_top"] - c["y_raw_bottom"])
        return (max(0, min(c["width"] - 1, int(x))), max(0, min(c["height"] - 1, int(y))))


class TouchEvent:
    __slots__ = ("kind", "x", "y")

    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y   # kind: "down" / "move" / "up"

    def __repr__(self):
        return "TouchEvent(%s, %d, %d)" % (self.kind, self.x, self.y)


class TouchState:
    """evdev の生イベントを TouchEvent にまとめる (テストしやすいよう入出力だけの部品にしてある)。"""
    EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
    ABS_X, ABS_Y, BTN_TOUCH = 0, 1, 330

    def __init__(self, cal):
        self.cal = cal
        self.rx = self.ry = 0
        self.down = False
        self.pending_down = False
        self.pending_up = False
        self.last_xy = None

    def feed(self, etype, code, value):
        """生イベントを1つ受け取り、出せる TouchEvent があれば返す。"""
        if etype == self.EV_ABS and code == self.ABS_X:
            self.rx = value
        elif etype == self.EV_ABS and code == self.ABS_Y:
            self.ry = value
        elif etype == self.EV_KEY and code == self.BTN_TOUCH:
            if value:
                self.pending_down = True
            else:
                self.pending_up = True
        elif etype == self.EV_SYN:
            if self.pending_up:
                self.pending_up = False
                self.down = False
                x, y = self.last_xy or self.cal.to_screen(self.rx, self.ry)
                return TouchEvent("up", x, y)
            xy = self.cal.to_screen(self.rx, self.ry)
            if self.pending_down:
                self.pending_down = False
                self.down = True
                self.last_xy = xy
                return TouchEvent("down", *xy)
            if self.down and xy != self.last_xy:
                self.last_xy = xy
                return TouchEvent("move", *xy)
        return None


class TouchReader:
    """別スレッドで /dev/input/ds-touch を読み、TouchEvent をキューに入れる。"""

    def __init__(self, path="/dev/input/ds-touch", cal=None):
        from evdev import InputDevice
        self.dev = InputDevice(path)
        self.state = TouchState(cal or Calibration.load())
        self.events = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        for ev in self.dev.read_loop():
            out = self.state.feed(ev.type, ev.code, ev.value)
            if out:
                self.events.put(out)

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out
