// engine/dist/schema.js 的最小替身：CI 里不装 remotion 也能测 store 的会话/空项目逻辑
export const parseTimeline = (t) => ({
  version: 7,
  meta: { fps: 30, width: 1280, height: 720, ...(t?.meta ?? {}) },
  videoTracks: t?.videoTracks ?? [],
  audioTracks: t?.audioTracks ?? [],
  overlays: t?.overlays ?? [],
  markers: t?.markers ?? [],
});
export const validateTimeline = () => {};
export class TimelineVersionError extends Error {}
