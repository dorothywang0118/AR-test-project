import type { ShowDef } from '@shared/types/campaign';
import type { CharacterController } from './CharacterController';

/**
 * Runs a scripted group scene: each step starts a clip on several characters at once
 * (e.g. two neighbours high-five), waits for the longest clip, then moves on and loops.
 */
export class ShowDirector {
  private index = -1;
  private wait = 0;
  private running = false;

  constructor(
    private readonly def: ShowDef,
    private readonly chars: Map<string, CharacterController>,
  ) {}

  start(): void {
    this.index = -1;
    this.wait = 1.0;
    this.running = true;
  }

  stop(): void {
    this.running = false;
  }

  update(dt: number): void {
    if (!this.running || this.def.steps.length === 0) return;
    this.wait -= dt;
    if (this.wait > 0) return;
    this.index = (this.index + 1) % this.def.steps.length;
    const step = this.def.steps[this.index];
    let longest = 0;
    for (const [charId, clip] of Object.entries(step.clips)) {
      longest = Math.max(longest, this.chars.get(charId)?.play(clip) ?? 0);
    }
    const isLast = this.index === this.def.steps.length - 1;
    this.wait = longest + (isLast ? 2.5 : 0.5);
  }
}
