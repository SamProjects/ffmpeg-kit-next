# Reproducing the Android Builds

The GitHub Release's `BUILD_INFO.txt` contains the exact release tag, source
commit, dependency revisions, Android package commands, and FFmpeg configure
strings extracted from the resulting AAR files.

## Prerequisites

- Linux x86_64
- Nix installed by `DeterminateSystems/determinate-nix-action`
- Android NDK package selected by `android-r27d`
- Git and standard archive tools

## LGPLv3 all-ABI AAR

```sh
./nix-android.sh -p android-r27d \
  --enable-libvpx \
  --enable-lame \
  --enable-android-media-codec
```

## GPLv3 all-ABI AAR

```sh
./nix-android.sh -p android-r27d \
  --enable-libvpx \
  --enable-lame \
  --enable-android-media-codec \
  --enable-gpl \
  --enable-x264 \
  --enable-x265
```

Single-ABI LGPLv3 packages use the first command plus the architecture-disable
flags recorded in `.github/workflows/all-platform-release.yml`.

The build produces the Maven repository under
`prebuilt/bundle-android-aar-24-maven`. The published AAR is located at:

```text
com/arthenica/ffmpeg-kit-next/8.1.1/ffmpeg-kit-next-8.1.1.aar
```

For an exact audit, compare the configure line in the rebuilt
`libavutil.so` with the matching line in `BUILD_INFO.txt`.
