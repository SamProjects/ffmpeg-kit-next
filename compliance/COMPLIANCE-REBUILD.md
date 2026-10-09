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
  --debug \
  --enable-libvpx \
  --enable-lame \
  --enable-android-media-codec
```

## GPLv3 all-ABI AAR

```sh
./nix-android.sh -p android-r27d \
  --debug \
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
com/arthenica/ffmpeg-kit-next/<version>/ffmpeg-kit-next-<version>.aar
```

For an exact audit, compare the configure line in the rebuilt
`libavutil.so` with the matching line in `BUILD_INFO.txt`.

## Full native debug information

The Android release uses `--debug` while keeping release optimization for the
NDK wrapper. The native build generates GNU Build IDs, retains DWARF information
for FFmpeg, libvpx, LAME and the wrapper, and prevents NDK/AGP from stripping the
library AAR. Debug information contains source paths and line mappings; it does
not embed the corresponding source files. Use the matching source archives for
source-level debugging.

Before archiving the Maven repository or publishing the AAR, run the same
packaging step as the release workflow (replace `<version>`):

```sh
python3 scripts/ci/package-android-debug-symbols.py \
  --aar prebuilt/bundle-android-aar-24-maven/com/arthenica/ffmpeg-kit-next/<version>/ffmpeg-kit-next-<version>.aar \
  --native-root android/obj/local \
  --abis arm64-v8a armeabi-v7a x86 x86_64 \
  --symbols-zip native-debug-symbols.zip
```

The packager requires `.symtab`, `.debug_info`, `.debug_line` and a nonempty GNU
Build ID for **every** packaged JNI library. It checks the ELF architecture,
Build ID and all allocated sections against the AAR before replacing its JNI
entries with `android/obj/local` outputs from the same build. The ZIP contains
the identical full libraries under `<abi>/<library>.so`. Missing information,
including in a newly enabled prebuilt dependency, fails the release rather than
silently publishing partial symbols. Such a dependency must be built with debug
information or supplied with matching unstripped binaries.

### Including symbols automatically in the app bundle

Use this AAR and set the following in the consuming app module's Groovy Gradle
configuration:

```groovy
android {
    buildTypes {
        release {
            ndk {
                debugSymbolLevel 'FULL'
            }
        }
    }
}
```

Keep the app's normal native stripping enabled; do not add `keepDebugSymbols`
to the app solely for uploading symbols. That setting belongs to this library's
AAR packaging. After running `bundleRelease`, inspect the generated AAB and
confirm that `BUNDLE-METADATA/com.android.tools.build.debugsymbols/` contains
symbols for the packaged FFmpeg libraries and ABIs. Uploading that AAB to Play
then supplies its matching symbols. Upgrading to a newly built AAR supplies
the new symbols automatically through the same app build configuration.
