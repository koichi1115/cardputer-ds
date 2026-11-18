#!/usr/bin/env python3
"""タッチ位置を画面座標(320x240)で表示する。使い方: sudo python3 touch/touch_test.py"""
import json, os
from evdev import InputDevice, ecodes
cal = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'touch_cal.json')))
def to_screen(rx, ry):
    a, b = (ry, rx) if cal['swap_xy'] else (rx, ry)
    x = (cal['x_raw_left'] - a) * cal['width'] / (cal['x_raw_left'] - cal['x_raw_right'])
    y = (cal['y_raw_top'] - b) * cal['height'] / (cal['y_raw_top'] - cal['y_raw_bottom'])
    return max(0, min(cal['width'] - 1, int(x))), max(0, min(cal['height'] - 1, int(y)))
dev = InputDevice('/dev/input/ds-touch')
rx = ry = 0; down = False
print('タッチしてください (Ctrl+Cで終了)')
for ev in dev.read_loop():
    if ev.type == ecodes.EV_ABS and ev.code == ecodes.ABS_X: rx = ev.value
    elif ev.type == ecodes.EV_ABS and ev.code == ecodes.ABS_Y: ry = ev.value
    elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
        down = bool(ev.value)
        if not down: print('  離した')
    elif ev.type == ecodes.EV_SYN and down:
        print('画面座標 x=%3d y=%3d' % to_screen(rx, ry), end='\r')
