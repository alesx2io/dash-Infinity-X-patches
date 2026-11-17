# Infinity-X fixes for POCO X8 Pro Max (dash)

Source patches used for the unofficial **Project Infinity-X 4.2 (Android 17)** builds for the
POCO X8 Pro Max / Redmi Turbo 5 Max (`dash`, MediaTek `mt6991`).

Each fix is a plain `git format-patch` file, grouped by the AOSP/Infinity project it applies to.
They are small and self-contained, so they can be picked one by one for other ROMs on `dash`,
and several of them are generic enough for other devices.

- ROM builds: <https://sourceforge.net/projects/dash-roms/>
- Device tree, kernel and hardware: [oss-dash](https://github.com/oss-dash) ([local manifests](https://github.com/oss-dash/android_local_manifests))
- ROM: [ProjectInfinity-X](https://github.com/ProjectInfinity-X)

## Fixes

| Area | Project | Problem | Fix |
|---|---|---|---|
| Charging time | `frameworks/base`, `hardware/mediatek` | Lock screen showed "Full in 45 days". The Xiaomi battery driver fills `time_to_full_now` with a capacity-derived number (missing levels × 75200 or 150400), not seconds. | The MediaTek health HAL reports the value as unknown, and `BatteryStatsImpl` ignores anything above 24 h, so the framework uses its own charge-step estimate. |
| Charging stats | `frameworks/base` | The lock screen "Charging stats" toggle looked ignored: the stats line is appended as a third line and the indication text allowed only two. | Keyguard indication text allows three lines. |
| Auto brightness | `vendor/xiaomi/dash` | In dim light the under-display sensor (`tsl2525_als`) reports integer lux toggling 0 ↔ 1, and the brightening threshold at 0 lux is 0, so the screen jumped between 3.5 and 6.4 nits every few seconds. | Display config requires more than 1 lux of change before brightening. |
| Min refresh rate | `device/xiaomi/dash` | A minimum refresh rate of 120 Hz went back to 60 Hz after each boot: `MinRefreshRateCtrl` wrote 60 Hz unconditionally on `BOOT_COMPLETED`. | The 60 Hz floor is written only when the current value is lower. |
| Volume | `device/xiaomi/dash` | The vendor audio config declares 30 media steps and a default of 20, but the framework used 15, so each step was twice as large and the lowest step louder than stock. | 30 media volume steps, safe headphone index scaled to 20/30. |
| Settings search | `frameworks/base` | Settings search returned almost nothing: Settings Services updated from the Play Store only indexes Pixel Settings (0 entries vs 1952 with the bundled version). | New `config_pinnedSystemPackages`: updates to listed system packages are rejected unless they come from adb or root. Settings Services is pinned to the bundled build. |
| Sound picker lag | `frameworks/base` | Google Sound Picker calls `ContentResolver.canonicalize()` for ~450 sounds on the main thread at every tap, freezing the UI for 0.7–0.85 s. | `canonicalize()` answers for the `media` authority are cached per process (30 s for hits, 2 s for misses). |
| Lock screen camera | `frameworks/base`, `device/xiaomi/dash` | The lock screen camera shortcut showed a chooser with MiuiCamera twice: the app handles the secure camera intent with `.Camera` and `.AssistantCamera`. | New SystemUI `config_cameraSecureActivity`; the device overlay points it to `com.android.camera/.Camera`. |
| Build | `build/soong`, `device/xiaomi/dash` | The `mediatek-ims-common` boot jar contains `com.xiaomi.ims` classes; the device tree only had a Lineage product. | Allow `com.xiaomi.ims` in the boot jar package list; add the `infinity_dash` product. |

## Usage

```bash
git clone https://github.com/alesx2io/dash-infinity-fixes
cd dash-infinity-fixes
./apply-patches.sh /path/to/infinity                       # everything
./apply-patches.sh /path/to/infinity frameworks/base       # one project
```

The script creates a `dash-fixes` branch in each project (`repo start`) and applies the patches
with `git am --3way`. You can also apply a single file by hand:

```bash
cd /path/to/infinity/frameworks/base
git am --3way /path/to/dash-infinity-fixes/patches/frameworks/base/0003-*.patch
```

## Compatibility

- Generated against Infinity-X 4.2 (`17` branch, `BUILD_ID=CP2A.260605.016`) and the oss-dash
  `lineage-24.0` trees as of 2026-11-16.
- The `device/xiaomi/dash` and `hardware/mediatek` patches also apply cleanly on the oss-dash
  trees updated on 2026-11-17.
- `0001-dash-add-Infinity-X-product.patch` contains the maintainer name and product
  properties for these builds: adapt it before using it in your own build.

## Known limitations

- **Auto brightness oscillation with the slider at max in the dark.** The Xiaomi compensation of
  the under-display sensor subtracts too much when the screen is very bright (around 0.48 of
  max brightness it reads 0 lux), which can start a short brightness loop. Not fixed yet;
  workaround: one-shot auto brightness or manual brightness.
- The sound picker cache shortens repeated freezes but the first load of each screen is still
  slow: the root cause is in the closed-source Google app.
- Pinning Settings Services means the Play Store keeps offering its update, which fails. This is
  intended.

## License

The patches modify Apache 2.0 licensed AOSP / LineageOS / Infinity-X code and are provided under
the same license as the files they change.
