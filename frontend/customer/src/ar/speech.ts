/**
 * Reads speech-bubble lines aloud: pre-recorded neural voices (tools/make_voices.py) first,
 * the phone's built-in text-to-speech (Web Speech API) as a fallback. Voice quality depends on the phone (iPhone: "Mei-Jia" zh-TW).
 */
export interface VoiceDef {
  pitch?: number; // 0.1 – 2, default 1
  rate?: number; // 0.1 – 2, default 1
}

/** Remove things a voice would read out loud badly (decorations, stage directions). */
function speakable(text: string): string {
  return text
    .replace(/（[^）]*）/g, '')
    .replace(/[～~]/g, '')
    .replace(/QQ/gi, '')
    .replace(/…+/g, '，')
    .trim();
}

const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';

export class Speaker {
  enabled = true;
  /** Pre-recorded lines: characterId -> line -> mp3 url. Lines without a recording fall back to the phone's voice. */
  private clips: Record<string, Record<string, string>> = {};
  private audio: HTMLAudioElement | null = typeof Audio !== 'undefined' ? new Audio() : null;
  private playing = false;

  async loadClips(manifestUrl: string): Promise<void> {
    try {
      const r = await fetch(manifestUrl);
      if (r.ok) this.clips = await r.json();
    } catch {
      /* recordings are optional */
    }
  }
  private voice: SpeechSynthesisVoice | null = null;

  get supported(): boolean {
    return typeof speechSynthesis !== 'undefined' && typeof SpeechSynthesisUtterance !== 'undefined';
  }

  constructor() {
    if (!this.supported) return;
    const pick = () => {
      const all = speechSynthesis.getVoices();
      this.voice = all.find((v) => /zh[-_]TW/i.test(v.lang)) ?? all.find((v) => /^zh/i.test(v.lang)) ?? null;
    };
    pick();
    speechSynthesis.addEventListener?.('voiceschanged', pick);
  }

  /** iOS only lets speech start after a tap: call this inside the Start-button tap. */
  unlock(): void {
    if (this.audio) {
      this.audio.onended = () => (this.playing = false);
      this.audio.onerror = () => (this.playing = false);
      this.audio.src = SILENCE;
      this.audio.play().catch(() => undefined);
    }
    if (!this.supported) return;
    try {
      const u = new SpeechSynthesisUtterance(' ');
      u.volume = 0;
      speechSynthesis.speak(u);
    } catch {
      /* speech is optional */
    }
  }

  /** @param force true when the customer tapped the character (always speak, interrupting older speech). */
  speak(text: string, voice: VoiceDef = {}, force = false, characterId = ''): void {
    if (!this.enabled) return;
    const busy = this.playing || (this.supported && speechSynthesis.speaking);
    if (!force && (busy || Math.random() > 0.5)) return; // keep self-play from chattering
    const url = this.clips[characterId]?.[text];
    if (url && this.audio) {
      if (this.supported) speechSynthesis.cancel();
      this.audio.src = url;
      this.playing = true;
      this.audio.play().catch(() => (this.playing = false));
      return;
    }
    if (!this.supported) return;
    const t = speakable(text);
    if (!t) return;
    try {
      if (force) speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(t);
      u.lang = 'zh-TW';
      if (this.voice) u.voice = this.voice;
      u.pitch = voice.pitch ?? 1;
      u.rate = voice.rate ?? 1;
      speechSynthesis.speak(u);
    } catch {
      /* speech is optional */
    }
  }

  cancel(): void {
    if (this.audio && this.playing) this.audio.pause();
    this.playing = false;
    if (this.supported) speechSynthesis.cancel();
  }

  toggle(): boolean {
    this.enabled = !this.enabled;
    if (!this.enabled) this.cancel();
    return this.enabled;
  }
}
