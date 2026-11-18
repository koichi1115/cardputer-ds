#!/bin/bash
# CardputerZero DS化(外付け 2.8" ILI9341 + タッチ) のセットアップ。何度実行しても同じ結果になる。
# 使い方: sudo ./install.sh  → 終わったら sudo reboot
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "sudo ./install.sh で実行してください"; exit 1; }
cd "$(dirname "$0")"
FW=/boot/firmware

echo "== パッケージ"
apt-get install -y device-tree-compiler python3-pil python3-evdev python3-numpy fonts-ipafont-gothic libdrm-tests evtest

echo "== 初期化データ"
python3 tools/make_init_bin.py /lib/firmware/cardputerzero,ili9341_ext.bin

echo "== overlay"
dtc -@ -q -I dts -O dtb -o $FW/overlays/ds-display.dtbo overlay/ds-display.dts
if ! grep -q '^dtoverlay=ds-display' $FW/config.txt; then
  cp $FW/config.txt $FW/config.txt.bak-ds
  printf '\ndtoverlay=ds-display\n' >> $FW/config.txt
  echo "config.txt に追加 (バックアップ: config.txt.bak-ds)"
fi

echo "== udev"
install -m 644 udev/99-ds-display.rules /etc/udev/rules.d/
udevadm control --reload

echo "== 起動ロゴ (fb_load)"
mkdir -p /usr/local/share/ds
python3 tools/make_splash.py /usr/local/share/ds/splash.bmp
install -D -m 644 systemd/fb_load.service.d/override.conf /etc/systemd/system/fb_load.service.d/override.conf
systemctl daemon-reload

echo "== G14 を RESET に使うためシリアル端末を止める"
systemctl disable --now serial-getty@ttyS0.service 2>/dev/null || true

echo "== 上画面アプリ (/opt/cardputer-ds, ds-top.service)"
mkdir -p /opt/cardputer-ds
rm -rf /opt/cardputer-ds/app /opt/cardputer-ds/touch
cp -r app touch /opt/cardputer-ds/
install -m 644 systemd/ds-top.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ds-top.service

echo
echo "完了。sudo reboot で反映されます。"
echo "上画面アプリ: 起動後に自動で表示 (止める: sudo systemctl stop ds-top)"
echo "確認: sudo modetest -M panel-mipi-dbi -s 34@37:320x240   (カラーバー。ds-top を止めてから)"
echo "      sudo python3 touch/touch_test.py                    (タッチ)"
