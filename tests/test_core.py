"""実機なしで確認できる部分のテスト: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

import drm  # noqa: E402
import status  # noqa: E402
import touch  # noqa: E402
import ui  # noqa: E402


class TestPixels(unittest.TestCase):
    def test_rgb565(self):
        rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
        self.assertEqual(drm.rgb_to_rgb565(rgb).tolist(), [[0xF800, 0x07E0, 0x001F, 0xFFFF]])

    def test_bbox(self):
        a = np.zeros((240, 320), np.uint16)
        self.assertEqual(drm.changed_bbox(None, a), (0, 0, 320, 240))
        self.assertIsNone(drm.changed_bbox(a, a.copy()))
        b = a.copy()
        b[10, 20] = 1
        b[30, 5] = 1
        self.assertEqual(drm.changed_bbox(a, b), (5, 10, 21, 31))

    def test_ioctl_numbers(self):
        # Linux の drm.h と同じ値になっていること
        self.assertEqual(drm.DRM_IOCTL_MODE_CREATE_DUMB, 0xC02064B2)
        self.assertEqual(drm.DRM_IOCTL_MODE_MAP_DUMB, 0xC01064B3)


class TestTouch(unittest.TestCase):
    def setUp(self):
        self.cal = touch.Calibration.load()

    def test_corners(self):
        # 実機で測った四隅の生の値
        self.assertEqual(self.cal.to_screen(3535, 3650), (0, 0))
        x, y = self.cal.to_screen(3540, 430)
        self.assertGreaterEqual(x, 315); self.assertLessEqual(y, 3)
        x, y = self.cal.to_screen(510, 525)
        self.assertGreaterEqual(x, 315); self.assertGreaterEqual(y, 235)

    def test_event_sequence(self):
        s = touch.TouchState(self.cal)
        K, A, S = s.EV_KEY, s.EV_ABS, s.EV_SYN
        out = [s.feed(K, s.BTN_TOUCH, 1), s.feed(A, s.ABS_X, 2055), s.feed(A, s.ABS_Y, 2110)]
        down = s.feed(S, 0, 0)
        self.assertEqual(down.kind, "down")
        self.assertTrue(150 <= down.x <= 165 and 110 <= down.y <= 125)
        s.feed(A, s.ABS_Y, 1800)
        self.assertEqual(s.feed(S, 0, 0).kind, "move")
        self.assertIsNone(s.feed(S, 0, 0))          # 位置が変わらなければ何も出ない
        s.feed(K, s.BTN_TOUCH, 0)
        self.assertEqual(s.feed(S, 0, 0).kind, "up")
        self.assertEqual(out, [None, None, None])


class TestStatus(unittest.TestCase):
    def test_wifi(self):
        text = ("Inter-| sta-|   Quality        |   Discarded packets\n"
                " face | tus | link level noise |  nwid  crypt   frag\n"
                " wlan0: 0000   49.  -61.  -256        0      0      0\n")
        self.assertEqual(status.wifi_quality(text), 70)
        self.assertIsNone(status.wifi_quality("nothing"))

    def test_mem(self):
        self.assertAlmostEqual(status.mem_used_percent("MemTotal: 1000 kB\nMemAvailable: 250 kB\n"), 75)

    def test_battery(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "ac"))
            def put(path, text):
                with open(path, "w") as f:
                    f.write(text)
            put(os.path.join(d, "ac", "type"), "Mains\n")
            b = os.path.join(d, "bq27220-0")
            os.makedirs(b)
            put(os.path.join(b, "type"), "Battery\n")
            put(os.path.join(b, "capacity"), "88\n")
            put(os.path.join(b, "status"), "Discharging\n")
            self.assertEqual(status.battery(d), (88, False))
        self.assertEqual(status.battery("/nonexistent"), (None, False))


class TestUi(unittest.TestCase):
    def test_tabs_and_buttons(self):
        app = ui.App()
        T = touch.TouchEvent
        # SYSTEM タブ (中央下) をタップ
        app.touch(T("down", 160, 225)); app.touch(T("up", 160, 225))
        self.assertEqual(app.page.title, "SYSTEM")
        # 押したまま外へずらして離すとタップにならない
        app.touch(T("down", 270, 225)); app.touch(T("move", 270, 100)); app.touch(T("up", 270, 100))
        self.assertEqual(app.page.title, "SYSTEM")
        app.touch(T("down", 270, 225)); app.touch(T("up", 270, 225))
        self.assertEqual(app.page.title, "TOUCH")
        paint = app.page
        before = paint.color
        app.touch(T("down", 40, 190)); app.touch(T("up", 40, 190))   # Color ボタン
        self.assertNotEqual(paint.color, before)

    def test_render_all_pages(self):
        app = ui.App()
        for i in range(len(app.pages)):
            app.select(i)
            img = app.render(ui.sample_status())
            self.assertEqual(img.size, (320, 240))
        st = dict(ui.sample_status(), bat=None, wifi=None, ssid=None, ip=None, temp=None)
        app.render(st)   # 値が取れないときも落ちない


if __name__ == "__main__":
    unittest.main()
