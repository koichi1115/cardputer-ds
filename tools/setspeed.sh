#!/bin/sh
# 外付け液晶の SPI 速度を変える。使い方: sudo tools/setspeed.sh 32000000
set -e
cd "$(dirname "$0")/.."
sed -i "/ili9341@1/,/panel-timing/ s/spi-max-frequency = <[0-9]*>;/spi-max-frequency = <$1>;/" overlay/ds-display.dts
dtc -@ -q -I dts -O dtb -o /boot/firmware/overlays/ds-display.dtbo overlay/ds-display.dts
echo "ds-display: $1 Hz (再起動で反映)"
