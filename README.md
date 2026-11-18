# cardputer-ds

M5Stack CardputerZero に外付けの 2.8インチ SPI 液晶（ILI9341、240×320、XPT2046 タッチ付き）をつないで、ニンテンドーDSのような2画面構成にするためのセットアップ一式です。

- 上画面（外付け）: 320×240 横向き、SPI 32MHz、約21fps
- 下画面（内蔵）: 320×170、ランチャーはそのまま動く
- タッチ: 抵抗膜式、画面座標に補正済み

## セットアップ

```bash
git clone https://github.com/koichi1115/cardputer-ds.git
cd cardputer-ds
sudo ./install.sh
sudo reboot
```

起動後の確認:

```bash
sudo modetest -M panel-mipi-dbi -s 34@37:320x240   # 上画面にカラーバー（Enterで終了）
sudo python3 touch/touch_test.py                    # タッチ座標の表示
```

## 上画面アプリ（app/）

外付け液晶に、時計・システム状態・タッチお絵描きの3ページを表示する土台です。下のタブをタッチして切り替えます。`install.sh` で `/opt/cardputer-ds` に入り、`ds-top.service` として起動時に自動で動きます。

| ページ | 内容 |
|---|---|
| HOME | 時計、日付、Wi-Fi の SSID と IP |
| SYSTEM | CPU 温度、負荷、メモリ、バッテリー |
| TOUCH | 指やペンで描ける（Color / Clear ボタン） |

```bash
sudo systemctl stop ds-top              # 止める（modetest などで画面を使うとき）
sudo python3 app/main.py                # 手動で起動（Ctrl+C で終了）
python3 app/main.py --preview out       # 実機なしで各ページを PNG に書き出す
python3 -m unittest discover -s tests   # 実機なしで動くテスト
```

仕組み:

- `app/drm.py`: libdrm を ctypes で呼び、ダムバッファを作ってモードを設定する（Cardputer は fbcon が無効なので、`/dev/fb_ext` に書くだけでは画面がオンにならない）。前のフレームとの差分の範囲だけを `DirtyFB` で送るので、時計の秒だけが変わるときは数百バイトで済む。
- `app/touch.py`: `/dev/input/ds-touch` を別スレッドで読み、`touch/touch_cal.json` で画面座標に変換して down / move / up のイベントにする。
- `app/ui.py`: PIL で 320×240 の画像を描く。ページとボタンの最小限の仕組み。
- 触っている間は 15fps、2秒触らなければ 4fps に落として、内蔵液晶と共用の SPI と CPU を空ける。

## 配線

液晶はブレッドボードの A 列 1〜14 行目に、画面を上にして挿す（VCC = 四角いパッドが 14 行目）。EXT のピン名は本体の印刷ラベルどおり。

| 液晶ピン | つなぐ先（EXT） | 備考 |
|---|---|---|
| VCC | 5V OUT | 「5V IN」は使わない |
| GND | G | |
| CS | G7 CS1 | |
| RESET | G14 TX | **5V に直結しない**（信号ピンは 3.3V まで） |
| DC | G23 | |
| SDI(MOSI) | G10 MO | 内蔵液晶と共用 |
| SCK | G11 CLK | 内蔵液晶と共用 |
| LED | 5V OUT | 基板上のトランジスタ経由なので 5V で可 |
| SDO(MISO) | 未接続 | この基板は CS 非選択時も MISO を離さず、タッチの読み取りを壊す |
| T_CLK | G11 CLK | SCK と分岐 |
| T_CS | G22 | M5 が用意している SPI0 の CS2 |
| T_DIN | G10 MO | SDI と分岐 |
| T_DO | G9 MI | |
| T_IRQ | G26 | |

液晶基板の J1 ジャンパーは開放のまま（ショートすると 5V が直接入る）。

## 入っているもの

| パス | 内容 | インストール先 |
|---|---|---|
| `overlay/ds-display.dts` | デバイスツリー overlay（液晶・タッチ・EXT 5V 自動 ON） | `/boot/firmware/overlays/ds-display.dtbo` |
| `tools/make_init_bin.py` | ILI9341 の初期化データ生成 | `/lib/firmware/cardputerzero,ili9341_ext.bin` |
| `udev/99-ds-display.rules` | `/dev/fb_ext` `/dev/dri/ds-external` `/dev/input/ds-touch` の固定名と seat 分離 | `/etc/udev/rules.d/` |
| `systemd/fb_load.service.d/override.conf` | 起動ロゴを名前で内蔵液晶に出す | `/etc/systemd/system/fb_load.service.d/` |
| `tools/make_splash.py` | 起動ロゴ（16bit BMP、170×320）生成 | `/usr/local/share/ds/splash.bmp` |
| `tools/setspeed.sh` | 上画面の SPI 速度変更 | |
| `touch/` | タッチ補正値とテスト | |

## つまずいた点（記録）

1. **デスクトップ（labwc）に上画面を取られる**: 新しい DRM 画面が seat0 に入るとデスクトップが握り、`/dev/fb_ext` に書いても出ない。udev で `ID_SEAT=seat-ds` にして分離。
2. **RESET を 5V に直結して真っ白**: 信号ピンは 3.3V 系。G14 で GPIO 制御に変更。
3. **reset-gpios の極性**: mipi-dbi 系ドライバは `reset-gpios = <&gpio 14 0>`（active-high 表記）が正しい。`1` にするとリセットされっぱなし。
4. **ドライバの二重登録**: compatible に標準の `panel-mipi-dbi-spi` を書くと標準版モジュールも読まれ、内蔵液晶が映らなくなる可能性。M5 版の `panel-mipi-dbi-m5stack` に揃える。
5. **fbcon が無効**: Cardputer は `fbcon=map:off` なので誰も画面をオンにしない。上画面はアプリ側が DRM でモードを設定してから描く必要がある。
6. **fb_load が card1 決め打ち**: 外付けを足すと番号がずれて内蔵液晶が初期化されず、ランチャーが固まる。引数で `/dev/dri/cardputer-zero-internal` を指定（画像は 16bit BMP が必須）。

## 戻し方

```bash
sudo cp /boot/firmware/config.txt.bak-ds /boot/firmware/config.txt
sudo rm /etc/udev/rules.d/99-ds-display.rules /etc/systemd/system/fb_load.service.d/override.conf
sudo systemctl daemon-reload && sudo reboot
```
