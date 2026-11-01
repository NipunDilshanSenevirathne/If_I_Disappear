/** Which of a job clip's two formats this browser can play. Phones play the H.264 MP4; some
    browsers (Chromium built without H.264, as in the automated tests) need the WebM. */
export function canPlay(kind: 'mp4' | 'webm'): boolean {
  try {
    const type = kind === 'mp4' ? 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"' : 'video/webm; codecs="vp8, vorbis"';
    return !!document.createElement('video').canPlayType(type);
  } catch {
    return false;
  }
}
