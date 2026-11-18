"""外付け液晶 (panel-mipi-dbi) に DRM で直接描くための最小ラッパー。

Cardputer は fbcon が無効なので、/dev/fb_ext に書くだけでは画面がオンにならない。
ここでは libdrm を ctypes で呼び、ダムバッファを作ってモードを設定し、
書き換えた範囲だけを DirtyFB で液晶に送る。
"""
import ctypes
import ctypes.util
import fcntl
import mmap
import os

import numpy as np

# ---- libdrm の構造体 (xf86drmMode.h) ----

class ModeInfo(ctypes.Structure):
    _fields_ = [
        ("clock", ctypes.c_uint32),
        ("hdisplay", ctypes.c_uint16), ("hsync_start", ctypes.c_uint16),
        ("hsync_end", ctypes.c_uint16), ("htotal", ctypes.c_uint16), ("hskew", ctypes.c_uint16),
        ("vdisplay", ctypes.c_uint16), ("vsync_start", ctypes.c_uint16),
        ("vsync_end", ctypes.c_uint16), ("vtotal", ctypes.c_uint16), ("vscan", ctypes.c_uint16),
        ("vrefresh", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("type", ctypes.c_uint32),
        ("name", ctypes.c_char * 32),
    ]


class Resources(ctypes.Structure):
    _fields_ = [
        ("count_fbs", ctypes.c_int), ("fbs", ctypes.POINTER(ctypes.c_uint32)),
        ("count_crtcs", ctypes.c_int), ("crtcs", ctypes.POINTER(ctypes.c_uint32)),
        ("count_connectors", ctypes.c_int), ("connectors", ctypes.POINTER(ctypes.c_uint32)),
        ("count_encoders", ctypes.c_int), ("encoders", ctypes.POINTER(ctypes.c_uint32)),
        ("min_width", ctypes.c_uint32), ("max_width", ctypes.c_uint32),
        ("min_height", ctypes.c_uint32), ("max_height", ctypes.c_uint32),
    ]


class Connector(ctypes.Structure):
    _fields_ = [
        ("connector_id", ctypes.c_uint32), ("encoder_id", ctypes.c_uint32),
        ("connector_type", ctypes.c_uint32), ("connector_type_id", ctypes.c_uint32),
        ("connection", ctypes.c_int),
        ("mmWidth", ctypes.c_uint32), ("mmHeight", ctypes.c_uint32),
        ("subpixel", ctypes.c_int),
        ("count_modes", ctypes.c_int), ("modes", ctypes.POINTER(ModeInfo)),
        ("count_props", ctypes.c_int), ("props", ctypes.POINTER(ctypes.c_uint32)),
        ("prop_values", ctypes.POINTER(ctypes.c_uint64)),
        ("count_encoders", ctypes.c_int), ("encoders", ctypes.POINTER(ctypes.c_uint32)),
    ]


class ClipRect(ctypes.Structure):
    _fields_ = [("x1", ctypes.c_uint16), ("y1", ctypes.c_uint16),
                ("x2", ctypes.c_uint16), ("y2", ctypes.c_uint16)]


class CreateDumb(ctypes.Structure):
    _fields_ = [("height", ctypes.c_uint32), ("width", ctypes.c_uint32), ("bpp", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("handle", ctypes.c_uint32), ("pitch", ctypes.c_uint32),
                ("size", ctypes.c_uint64)]


class MapDumb(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32), ("pad", ctypes.c_uint32), ("offset", ctypes.c_uint64)]


def _iowr(nr, size):
    return (3 << 30) | (size << 16) | (ord("d") << 8) | nr


DRM_IOCTL_MODE_CREATE_DUMB = _iowr(0xB2, ctypes.sizeof(CreateDumb))
DRM_IOCTL_MODE_MAP_DUMB = _iowr(0xB3, ctypes.sizeof(MapDumb))
DRM_MODE_CONNECTED = 1


def _lib():
    name = ctypes.util.find_library("drm") or "libdrm.so.2"
    lib = ctypes.CDLL(name, use_errno=True)
    lib.drmModeGetResources.restype = ctypes.POINTER(Resources)
    lib.drmModeGetResources.argtypes = [ctypes.c_int]
    lib.drmModeFreeResources.argtypes = [ctypes.POINTER(Resources)]
    lib.drmModeGetConnector.restype = ctypes.POINTER(Connector)
    lib.drmModeGetConnector.argtypes = [ctypes.c_int, ctypes.c_uint32]
    lib.drmModeFreeConnector.argtypes = [ctypes.POINTER(Connector)]
    lib.drmModeAddFB.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint8,
                                 ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
                                 ctypes.POINTER(ctypes.c_uint32)]
    lib.drmModeSetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                                   ctypes.POINTER(ModeInfo)]
    lib.drmModeDirtyFB.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(ClipRect),
                                   ctypes.c_uint32]
    lib.drmModeRmFB.argtypes = [ctypes.c_int, ctypes.c_uint32]
    lib.drmSetMaster.argtypes = [ctypes.c_int]
    return lib


def rgb_to_rgb565(rgb):
    """(H, W, 3) uint8 の RGB を (H, W) uint16 の RGB565 に変換する。"""
    r = rgb[..., 0].astype(np.uint16)
    g = rgb[..., 1].astype(np.uint16)
    b = rgb[..., 2].astype(np.uint16)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def changed_bbox(old, new):
    """2枚の RGB565 画像の差分を囲む矩形 (x1, y1, x2, y2) を返す。差がなければ None。
    x2, y2 は含まない (DRM の clip rect と同じ)。"""
    if old is None:
        h, w = new.shape
        return (0, 0, w, h)
    diff = old != new
    rows = np.flatnonzero(diff.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(diff.any(axis=0))
    return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


class DrmDisplay:
    """/dev/dri/ds-external を開いて 320x240 RGB565 の画面として使う。"""

    def __init__(self, path="/dev/dri/ds-external"):
        self.lib = _lib()
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        self.lib.drmSetMaster(self.fd)  # 誰も持っていなければ取れる。失敗しても SetCrtc で分かる

        res = self.lib.drmModeGetResources(self.fd)
        if not res:
            raise OSError(ctypes.get_errno(), "drmModeGetResources failed")
        try:
            self.crtc_id = res.contents.crtcs[0]
            conn = None
            for i in range(res.contents.count_connectors):
                c = self.lib.drmModeGetConnector(self.fd, res.contents.connectors[i])
                if c and c.contents.connection == DRM_MODE_CONNECTED and c.contents.count_modes > 0:
                    conn = c
                    break
                if c:
                    self.lib.drmModeFreeConnector(c)
            if conn is None:
                raise RuntimeError("接続中のコネクタが見つからない")
            self.connector_id = conn.contents.connector_id
            self.mode = ModeInfo.from_buffer_copy(conn.contents.modes[0])
            self.lib.drmModeFreeConnector(conn)
        finally:
            self.lib.drmModeFreeResources(res)

        self.width, self.height = self.mode.hdisplay, self.mode.vdisplay

        dumb = CreateDumb(height=self.height, width=self.width, bpp=16)
        fcntl.ioctl(self.fd, DRM_IOCTL_MODE_CREATE_DUMB, dumb)
        self.pitch = dumb.pitch
        self.size = dumb.size

        fb = ctypes.c_uint32()
        if self.lib.drmModeAddFB(self.fd, self.width, self.height, 16, 16, self.pitch,
                                 dumb.handle, ctypes.byref(fb)):
            raise OSError(ctypes.get_errno(), "drmModeAddFB failed")
        self.fb_id = fb.value

        mp = MapDumb(handle=dumb.handle)
        fcntl.ioctl(self.fd, DRM_IOCTL_MODE_MAP_DUMB, mp)
        self.map = mmap.mmap(self.fd, self.size, mmap.MAP_SHARED,
                             mmap.PROT_READ | mmap.PROT_WRITE, offset=mp.offset)
        self.pixels = np.ndarray((self.height, self.pitch // 2), dtype=np.uint16,
                                 buffer=self.map)[:, : self.width]
        self.pixels[:] = 0

        conn_id = ctypes.c_uint32(self.connector_id)
        if self.lib.drmModeSetCrtc(self.fd, self.crtc_id, self.fb_id, 0, 0,
                                   ctypes.byref(conn_id), 1, ctypes.byref(self.mode)):
            raise OSError(ctypes.get_errno(),
                          "drmModeSetCrtc failed (ほかのプログラムが画面を握っていないか確認)")
        self.last = None

    def show(self, rgb):
        """PIL 画像か (H, W, 3) 配列を表示する。変わった範囲だけを液晶に送る。"""
        frame = rgb_to_rgb565(np.asarray(rgb))
        box = changed_bbox(self.last, frame)
        if box is None:
            return None
        x1, y1, x2, y2 = box
        self.pixels[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
        clip = ClipRect(x1, y1, x2, y2)
        self.lib.drmModeDirtyFB(self.fd, self.fb_id, ctypes.byref(clip), 1)
        self.last = frame
        return box

    def close(self):
        try:
            self.map.close()
            self.lib.drmModeRmFB(self.fd, self.fb_id)
        finally:
            os.close(self.fd)


class PngDisplay:
    """実機なしで画面を確認するための代用品。show() のたびに PNG に保存する。"""

    def __init__(self, path="ds_preview.png", width=320, height=240):
        self.path, self.width, self.height = path, width, height
        self.last = None

    def show(self, rgb):
        from PIL import Image
        img = rgb if isinstance(rgb, Image.Image) else Image.fromarray(np.asarray(rgb))
        img.save(self.path)
        frame = rgb_to_rgb565(np.asarray(img))
        box = changed_bbox(self.last, frame)
        self.last = frame
        return box

    def close(self):
        pass
