# ClipForge Processing Worker

The web app is intentionally separated from heavy media processing.

Recommended worker pipeline:
1. Validate that the requester is authorized to process the source.
2. Resolve an allowed source through the platform/provider's permitted mechanism.
3. Extract audio/transcript with a locally hosted speech-to-text model.
4. Detect scene, speech, silence and audio peaks.
5. Score candidate windows.
6. Cut/transcode with FFmpeg.
7. Store temporary artifacts and return clip metadata.

Do not bypass access controls, DRM, private videos, or platform restrictions.