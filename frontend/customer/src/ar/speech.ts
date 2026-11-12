/**
 * Reads speech-bubble lines aloud with the phone's built-in text-to-speech (Web Speech API).
 * Free, works offline, no audio files. Voice quality depends on the phone (iPhone: "Mei-Jia" zh-TW).
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

export class Speaker {
  enabled = true;
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
  speak(text: string, voice: VoiceDef = {}, force = false): void {
    if (!this.enabled || !this.supported) return;
    if (!force && (speechSynthesis.speaking || Math.random() > 0.5)) return; // keep self-play from chattering
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
    if (this.supported) speechSynthesis.cancel();
  }

  toggle(): boolean {
    this.enabled = !this.enabled;
    if (!this.enabled) this.cancel();
    return this.enabled;
  }
}
