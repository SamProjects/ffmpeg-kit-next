# Third-Party Notices

This distribution contains FFmpegKitNext and prebuilt FFmpeg libraries. The
corresponding source archives, license texts, build metadata, and checksums are
published as assets of the same GitHub Release.

## Android LGPLv3 artifacts

Files whose names end in `android-*-lgpl3` are built without `--enable-gpl`
and without `--enable-nonfree`. They contain or link the following components:

| Component | Source revision | License summary |
| --- | --- | --- |
| FFmpeg | `n8.1.2` | LGPL 2.1-or-later; this build is LGPLv3-or-later |
| GNU config | `v20210814` | GPL with a special exception; build-time helper only |
| LAME / libmp3lame | `RELEASE__3_100` | LGPL |
| libvpx | `v1.16.0` | BSD-style license |
| GNU libiconv | `v1.17` | LGPL library code; see its bundled notices |
| cpu_features | `v0.11.0` | Apache License 2.0 |
| Android MediaCodec | Android platform API | Android platform component |

These are the Android artifacts intended for compliant use in a proprietary
application. LGPL obligations still apply, including notices, relinking or
replacement rights where applicable, and availability of corresponding source.

## Android GPLv3 artifact

The file ending in `android-all-gpl3` additionally enables x264 and x265 and is
distributed under GPLv3-or-later as a combined FFmpeg build. It is not a
commercial/proprietary license and should not be incorporated into a
closed-source application unless the complete application is distributed in a
GPL-compatible manner.

| Additional component | Source revision | License summary |
| --- | --- | --- |
| x264 | `b35605ace3ddf7c1a5d67a2eb553f034aef41d55` | GPL |
| x265 | `4.2` | GPL |

## Complete license texts

The authoritative license files are included inside
`third-party-sources-<tag>.tar.gz` with each component's corresponding source.
`COPYING.LGPLv3` in the Release is the license governing the LGPLv3 build of
FFmpegKitNext. If this summary conflicts with an upstream license file, the
upstream license file controls.

This notice is compliance information, not legal advice.
