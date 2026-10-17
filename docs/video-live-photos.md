# Browser-friendly video and Live Photos

SharedMoments preserves each original upload. MOV/HEVC and other videos can be played through an on-demand H.264/AAC MP4 derivative. The derivative is cached under the existing private uploads directory. Original downloads continue using the original media route.

- **Requirements:** ffmpeg with libx264 and AAC encoders (or imageio-ffmpeg). First playback uses additional CPU, storage and time. Conversion has a five-minute timeout.
- **Compatibility:** H.264 in MP4 with AAC audio is supported by major browsers. Conversion failure never modifies the original.
- **Access:** Authenticated playback uses the existing session. Shared-link playback requires a valid, unexpired item share and the same password verification as its original media.
- **Quality:** Playback derivatives are optimised; original uploads retain their original resolution, codecs and metadata. Derivatives remove source metadata.

## Live Photos

A Live Photo contains **two original files**: a still image and its short MOV/MP4 motion track. During online Home-item creation, files with the same original basename (for example IMG_001.jpg and IMG_001.mov) are automatically associated. Their gallery shows a single playable Live Photo tile while keeping both originals.

Automatic pairing currently applies to new online Home entries, not historical uploads, renamed pairs, edits or offline queued posts. JPEG/PNG/WebP images are accepted by the original app. The independent HEIC/HEIF support PR #15 is required to upload/display HEIC stills directly.

The feature adds no new media server. Tests use synthetic video bytes and a generated synthetic MOV clip.
