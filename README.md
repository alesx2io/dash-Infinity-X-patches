# Infinity-X fixes for POCO X8 Pro Max (dash)

Source patches used for the unofficial **Project Infinity-X 4.2 (Android 17)** builds for the
POCO X8 Pro Max / Redmi Turbo 5 Max (`dash`, MediaTek `mt6991`).

Each fix is a plain `git format-patch` file, grouped by the AOSP/Infinity project it applies to.
They are small and self-contained, so they can be picked one by one for other ROMs on `dash`,
and several of them are generic enough for other devices.

> **About these fixes:** they were developed with the help of AI (Claude), but every fix was
> built, flashed and tested by a human on a real POCO X8 Pro Max before being published here.

- ROM builds: <https://sourceforge.net/projects/dash-roms/>
- Device tree, kernel and hardware: [oss-dash](https://github.com/oss-dash) ([local manifests](https://github.com/oss-dash/android_local_manifests))
- ROM: [ProjectInfinity-X](https://github.com/ProjectInfinity-X)

## Fixes

| Area | Project | Problem | Fix |
|---|---|---|---|
| Charging time | `frameworks/base`, `hardware/mediatek` | Lock screen showed "Full in 45 days". The Xiaomi battery driver fills `time_to_full_now` with a capacity-derived number (missing levels × 75200 or 150400), not seconds. | The MediaTek health HAL reports the value as unknown, and `BatteryStatsImpl` ignores anything above 24 h, so the framework uses its own charge-step estimate. |
| Charging stats | `frameworks/base` | The lock screen "Charging stats" toggle looked ignored: the stats line is appended as a third line and the indication text allowed only two. | Keyguard indication text allows three lines. |
| Auto brightness | `vendor/xiaomi/dash` (merged in oss-dash) | In dim light the under-display sensor (`tsl2525_als`) reports integer lux toggling 0 ↔ 1, and the brightening threshold at 0 lux is 0, so the screen jumped between 3.5 and 6.4 nits every few seconds. | Display config requires more than 1 lux of change before brightening. |
| Brightness ramps | `vendor/xiaomi/dash` (merged in oss-dash) | Auto brightness jumped instead of fading: without per-display ramps the framework used `config_brightness_ramp_rate_*`, which the overlay sets above the 0-255 scale, so every ramp was clamped to 1.0/s. | Display config ramps: auto 0.15/s up and 0.10/s down (max 2 s / 3 s), manual 0.6/s up and 0.5/s down. |
| Custom fingerprint icon | `frameworks/base` | The fingerprint icon picked in the Infinity settings was used only on the lock screen: on AOD, notification pulses and the first frames of a wake-up the stock fingerprint animation was shown. | The AOD fingerprint state uses the custom icon too. |
| Notification wake | `frameworks/base` | With the screen off, a notification started an AOD-style doze pulse, which is buggy on this device: the display came on at minimum brightness and the lock screen faded in from black, so it looked like a dark frame followed by a jump in brightness. A slower pulse fade did not fix it. | The AOD pulse is replaced by a normal wake: notifications turn the screen on like the power button (normal screen-on transition and auto brightness), after the same pocket check. Still controlled by *Wake screen for notifications*. |
| Volume | `device/xiaomi/dash` | The vendor audio config declares 30 media steps and a default of 20, but the framework used 15, so each step was twice as large and the lowest step louder than stock. | 30 media volume steps, safe headphone index scaled to 20/30. |
| Settings search | `frameworks/base` | Settings search returned almost nothing: Settings Services updated from the Play Store only indexes Pixel Settings (0 entries vs 1952 with the bundled version). | New `config_pinnedSystemPackages`: updates to listed system packages are rejected unless they come from adb or root. Settings Services is pinned to the bundled build. |
| Sound picker lag | `frameworks/base` | Google Sound Picker calls `ContentResolver.canonicalize()` for ~450 sounds on the main thread at every tap, freezing the UI for 0.7–0.85 s. | `canonicalize()` answers for the `media` authority are cached per process (30 s for hits, 2 s for misses). |
| Lock screen camera | `frameworks/base`, `device/xiaomi/dash` | The lock screen camera shortcut showed a chooser with MiuiCamera twice: the app handles the secure camera intent with `.Camera` and `.AssistantCamera`. | New SystemUI `config_cameraSecureActivity`; the device overlay points it to `com.android.camera/.Camera`. |
| Build | `build/soong`, `device/xiaomi/dash` | The `mediatek-ims-common` boot jar contains `com.xiaomi.ims` classes; the device tree only had a Lineage product. | Allow `com.xiaomi.ims` in the boot jar package list; add the `infinity_dash` product. |

## Kernel variants

The device tree is kept in two branches with the same fixes:

| Variant | Branch | Kernel |
|---|---|---|
| `prebuilt` | `infinity` | Stock HyperOS kernel and modules from `device/xiaomi/dash-kernel` (OS3.0.304.0 global) |
| `kleaf` | `infinity-kleaf` | Built from source with Kleaf from [oss-dash-kernel](https://github.com/oss-dash-kernel). Experimental: several Xiaomi modules are reverse engineered, see its README |

```bash
./switch-variant.sh /path/to/infinity prebuilt   # or: kleaf
```

`manifest/dash.xml` is the local manifest used for these builds (`.repo/local_manifests/dash.xml`).
It includes both the prebuilt kernel repo and the Kleaf kernel platform; Infinity already excludes
`kernel/platform` from Soong, so the kernel sources do not affect the prebuilt variant.

## Usage

```bash
git clone https://github.com/alesx2io/dash-Infinity-X-patches
cd dash-Infinity-X-patches
./apply-patches.sh /path/to/infinity                       # everything
./apply-patches.sh /path/to/infinity frameworks/base       # one project
```

The script creates a `dash-fixes` branch in each project (`repo start`) and applies the patches
with `git am --3way`. You can also apply a single file by hand:

```bash
cd /path/to/infinity/frameworks/base
git am --3way /path/to/dash-Infinity-X-patches/patches/frameworks/base/0003-*.patch
```

## Upstream update check

`tools/check-updates.py` checks every project of the local manifest (plus the patched
`frameworks/base` and `build/soong`) for new upstream commits and judges whether to merge them.
It never merges anything: it fetches only when the remote tip moved (shallow clones with a
limited depth), replays our commits on the new upstream with `git merge-tree`, and writes a
report to `reports/`:

- **SAFE**: our commits apply cleanly and nothing sensitive changed;
- **REVIEW**: applies, but upstream touched files we patch or sensitive build files
  (BoardConfig, init scripts, sepolicy, VINTF manifests, overlays, props);
- **CONFLICT**: our commits do not apply as they are;
- **KERNEL-UPDATE**: the oss-dash-kernel sources moved; they are taken as is, never patched here.

It also compares our local manifest with the oss-dash one. `tools/session-start.sh` is a
Claude Code `SessionStart` hook that runs the check in the background (at most every 6 hours)
and passes the latest report to the session.

```bash
python3 tools/check-updates.py --src /path/to/infinity
```

## Compatibility

- Generated against Infinity-X 4.2 (`17` branch, `BUILD_ID=CP2A.260605.016`) and the oss-dash
  `lineage-24.0` trees as of 2026-11-16.
- Device tree and `hardware/mediatek` patches are based on the oss-dash trees of 2026-11-19
  (device tree without the Kleaf commit for the `prebuilt` variant).
- The auto brightness threshold and brightness ramp fixes, first made here, are now part of
  oss-dash (`vendor/xiaomi/dash` and `extract-files.py`), so they are no longer shipped as
  patches. oss-dash also fixed the minimum refresh rate reset after boot in the same way.
- `0001-dash-add-Infinity-X-product.patch` contains the maintainer name and product
  properties for these builds: adapt it before using it in your own build.

## Known issues and workarounds

| Issue | Cause | Workaround |
|---|---|---|
| Auto brightness may briefly oscillate with the slider at max in a dark room | The Xiaomi compensation of the under-display light sensor subtracts too much when the screen is very bright (around half brightness it already reads 0 lux), which starts a short brightness loop. The slower ramps make it softer but do not remove it. | Use one-shot auto brightness or manual brightness, or avoid pushing the slider to max in the dark. |
| Blurred rectangle on the lock screen right after closing the shade | Lock screen "translucent notifications" (Infinity setting): the blur region of the notification background stays on screen for ~300 ms after the row is tucked away. | Turn off *Notifications → Translucent notifications on lock screen*. |
| Compact lock screen notifications have broken animations: black frame when closing the shade, notifications appearing late when opening the shade by tapping the icon pill | Animation bug of the compact lock screen notifications (icon pill) with a secure lock screen. Not fixed. | Use the full list of notifications on the lock screen (*Notifications on lock screen → show all*) instead of the compact pill. |
| Screen flickering may occur with max refresh rate 120 Hz and min 60 Hz | Not investigated yet. | Set both minimum and maximum refresh rate to 120 Hz. |
| Settings search finds almost nothing after a dirty flash | Settings Services marks its index as up to date for the new build even when indexing ran before unlock and stored nothing. | *Settings → Apps → Settings Services → Storage → Clear data*, then open the search again: it re-indexes everything. |
| Ringtone, message and alarm sounds cannot be selected | Not the ROM: the *Hide vendor sepolicy* option of the susfs4ksu root module breaks `vold_prepare_subdirs`, so user storage is never marked as ready. | Turn off *Hide vendor sepolicy* in the susfs4ksu WebUI and reboot. |

## License

The patches modify Apache 2.0 licensed AOSP / LineageOS / Infinity-X code and are provided under
the same license as the files they change.
