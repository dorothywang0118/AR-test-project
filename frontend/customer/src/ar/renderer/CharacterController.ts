import {
  AnimationAction,
  AnimationClip,
  AnimationMixer,
  AmbientLight,
  Box3,
  Camera,
  CanvasTexture,
  DirectionalLight,
  Euler,
  Group,
  LoopOnce,
  LoopRepeat,
  MathUtils,
  Mesh,
  Object3D,
  Raycaster,
  SRGBColorSpace,
  Sprite,
  SpriteMaterial,
  Vector2,
  type Scene,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ExperienceDef } from '@shared/types/campaign';

/** Hidden expression / prop nodes are shrunk to ~0 by the animation; we turn them fully invisible so they cost no draw call. */
const HIDDEN_SCALE = 0.02;

/** Basic lighting so un-lit GLB materials look 3D. Returns a function that removes the lights. */
export function addDefaultLights(scene: Scene): () => void {
  const ambient = new AmbientLight(0xffffff, 1.0);
  const sun = new DirectionalLight(0xffffff, 1.6);
  sun.position.set(0.5, 1, 1.5);
  scene.add(ambient, sun);
  return () => scene.remove(ambient, sun);
}

/**
 * Loads one GLB, places it under an AR anchor using the experience config,
 * plays idle, and plays interaction clips on tap.
 * Knows nothing about MindAR — only about three.js objects.
 */
export class CharacterController {
  private holder: Group | null = null;
  private root: Object3D | null = null;
  private toggled: Object3D[] = []; // nodes whose visibility follows their animated scale
  private bubble: Sprite | null = null;
  private bubbleTime = 0;
  private bubbleTotal = 0;
  private bubbleTop = 1.2;
  /** Set by the page: read a bubble line aloud. force = the customer tapped this character. */
  onSay: ((text: string, characterId: string, force: boolean) => void) | null = null;
  private forceSpeak = false;
  private bubbleTex = new Map<string, { tex: CanvasTexture; aspect: number; hpx: number }>();
  private mixer: AnimationMixer | null = null;
  private clips = new Map<string, AnimationClip>();
  private idle: AnimationAction | null = null;
  private current: AnimationAction | null = null;
  private queue: string[] = [];
  private lastName = '';
  private autoTimer = 0;
  private raycaster = new Raycaster();

  get characterId(): string {
    return this.cfg.characterId;
  }

  get targetId(): string {
    return this.cfg.targetId;
  }

  constructor(
    private readonly cfg: ExperienceDef,
    private readonly phrases: Record<string, string[]> = {},
  ) {
    this.autoTimer = this.nextAutoDelay();
  }

  /** Seconds until the character performs a random action by itself (so it feels alive without taps). */
  private nextAutoDelay(): number {
    return 6 + Math.random() * 8;
  }

  private isShown(): boolean {
    for (let o: Object3D | null = this.root; o; o = o.parent) if (!o.visible) return false;
    return true;
  }

  async load(modelUrl: string, parent: Object3D): Promise<void> {
    const gltf = await new GLTFLoader().loadAsync(modelUrl);
    const root = gltf.scene;
    const holder = new Group();
    holder.add(root);
    holder.updateMatrixWorld(true);
    // Height of the visible parts (ignoring hidden props) → where the speech bubble floats.
    const box = new Box3();
    root.traverse((o) => {
      if (!(o instanceof Mesh)) return;
      for (let n: Object3D | null = o; n && n !== root.parent; n = n.parent) if (n.scale.x < HIDDEN_SCALE) return;
      box.expandByObject(o);
    });
    this.bubbleTop = Number.isFinite(box.max.y) ? box.max.y : 1.1;
    holder.scale.setScalar(this.cfg.scale);
    holder.position.set(this.cfg.position.x, this.cfg.position.y, this.cfg.position.z);
    holder.rotation.copy(
      new Euler(
        MathUtils.degToRad(this.cfg.rotation.x),
        MathUtils.degToRad(this.cfg.rotation.y),
        MathUtils.degToRad(this.cfg.rotation.z),
      ),
    );
    parent.add(holder);
    this.holder = holder;
    this.root = root;

    // Nodes whose scale is animated to toggle them (expressions, props) — but not the legs (they squash).
    const names = new Set<string>();
    gltf.animations.forEach((c) =>
      c.tracks.forEach((t) => {
        if (t.name.endsWith('.scale') && !t.name.startsWith('Leg')) names.add(t.name.slice(0, -'.scale'.length));
      }),
    );
    names.forEach((n) => {
      const o = root.getObjectByName(n);
      if (o) this.toggled.push(o);
    });
    this.syncVisibility();

    gltf.animations.forEach((c) => this.clips.set(c.name, c));
    this.mixer = new AnimationMixer(root);
    const idleClip = this.clips.get(this.cfg.idleAnimation);
    if (idleClip) {
      this.idle = this.mixer.clipAction(idleClip).setLoop(LoopRepeat, Infinity);
    } else {
      console.warn(`[Character] idle clip "${this.cfg.idleAnimation}" not found; have`, [...this.clips.keys()]);
    }
    this.mixer.addEventListener('finished', () => this.onClipFinished());
    this.playIdle();
  }

  /** Call every frame. */
  update(deltaSeconds: number): void {
    this.mixer?.update(deltaSeconds);
    this.syncVisibility();
    this.updateBubble(deltaSeconds);
    if (this.cfg.autoPlay !== false && this.queue.length === 0 && this.root && this.isShown()) {
      this.autoTimer -= deltaSeconds;
      if (this.autoTimer <= 0) this.triggerInteraction();
    }
  }

  private syncVisibility(): void {
    for (const o of this.toggled) o.visible = o.scale.x > HIDDEN_SCALE;
  }

  // ---- speech bubble (口頭禪) ------------------------------------------------------------
  private makeBubble(text: string): { tex: CanvasTexture; aspect: number; hpx: number } {
    const cached = this.bubbleTex.get(text);
    if (cached) return cached;
    const fs = 44;
    const pad = 26;
    const font = `700 ${fs}px "PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif`;
    const probe = document.createElement('canvas').getContext('2d')!;
    probe.font = font;
    // Wrap long lines: break at commas first, then every 9 characters.
    const lines: string[] = [];
    for (const part of text.split(/(?<=，)/)) {
      const n = Math.ceil(part.length / 9);
      const per = Math.ceil(part.length / n); // even split, avoids a lone trailing character
      for (let i = 0; i < part.length; i += per) lines.push(part.slice(i, i + per));
    }
    const lineH = Math.round(fs * 1.25);
    const w = Math.ceil(Math.max(...lines.map((l) => probe.measureText(l).width))) + pad * 2;
    const h = lineH * lines.length + pad * 2 - (lineH - fs);
    const tail = 22;
    const cv = document.createElement('canvas');
    cv.width = w + 12;
    cv.height = h + tail + 12;
    const g = cv.getContext('2d')!;
    g.translate(6, 6);
    g.lineWidth = 5;
    g.strokeStyle = '#26232b';
    g.fillStyle = '#ffffff';
    g.beginPath();
    g.roundRect(0, 0, w, h, 26);
    g.fill();
    g.stroke();
    g.beginPath(); // tail
    g.moveTo(w / 2 - 14, h - 2);
    g.lineTo(w / 2, h + tail);
    g.lineTo(w / 2 + 14, h - 2);
    g.closePath();
    g.fill();
    g.beginPath();
    g.moveTo(w / 2 - 14, h);
    g.lineTo(w / 2, h + tail);
    g.lineTo(w / 2 + 14, h);
    g.stroke();
    g.fillStyle = '#26232b';
    g.font = font;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    lines.forEach((l, i) => g.fillText(l, w / 2, pad + (lineH - (lineH - fs)) / 2 + i * lineH + 2));
    const tex = new CanvasTexture(cv);
    tex.colorSpace = SRGBColorSpace;
    const entry = { tex, aspect: cv.width / cv.height, hpx: cv.height };
    this.bubbleTex.set(text, entry);
    return entry;
  }

  /** Show one of the clip's catchphrases above the character for a moment. */
  private say(clipName: string, seconds: number): void {
    if (!this.holder) return;
    const list = this.phrases[clipName] ?? this.phrases['*'];
    if (!list || list.length === 0) return;
    const text = list[Math.floor(Math.random() * list.length)];
    const { tex, aspect, hpx } = this.makeBubble(text);
    this.onSay?.(text, this.cfg.characterId, this.forceSpeak);
    if (!this.bubble) {
      const mat = new SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false });
      this.bubble = new Sprite(mat);
      this.bubble.renderOrder = 20;
      this.holder.add(this.bubble);
    }
    const mat = this.bubble.material as SpriteMaterial;
    mat.map = tex;
    mat.needsUpdate = true;
    const height = (0.3 * hpx) / 130; // same text size for 1 or several lines
    this.bubble.userData.h = height;
    this.bubble.userData.w = height * aspect;
    this.bubble.center.set(0.5, 0); // anchor at the tail tip
    this.bubble.position.set(0, this.bubbleTop + 0.05, 0.05);
    this.bubbleTotal = this.bubbleTime = Math.min(Math.max(seconds, 1.6), 3.2);
    this.bubble.visible = true;
  }

  private updateBubble(dt: number): void {
    const b = this.bubble;
    if (!b || !b.visible) return;
    this.bubbleTime -= dt;
    if (this.bubbleTime <= 0) {
      b.visible = false;
      return;
    }
    const age = this.bubbleTotal - this.bubbleTime;
    const pop = Math.min(1, age / 0.18); // quick pop-in
    const k = 0.7 + 0.3 * (1 - (1 - pop) * (1 - pop)) * (1 + 0.12 * (1 - pop));
    b.scale.set(b.userData.w * k * pop, b.userData.h * k * pop, 1);
    (b.material as SpriteMaterial).opacity = Math.min(1, this.bubbleTime / 0.3);
  }

  /** Target found again → restart from idle so the character never reappears mid-jump. */
  reset(targetId?: string): void {
    if (targetId && targetId !== this.cfg.targetId) return;
    this.queue = [];
    this.autoTimer = this.nextAutoDelay();
    if (this.bubble) this.bubble.visible = false;
    this.mixer?.stopAllAction();
    this.current = null;
    this.playIdle();
  }

  private playIdle(): void {
    if (!this.idle) return;
    this.current?.fadeOut(0.15);
    this.idle.reset().fadeIn(0.15).play();
    this.current = this.idle;
  }

  /** @returns true if the tap hit the character. pointer is in normalized device coords (-1..1). */
  tryTap(ndc: Vector2, camera: Camera): boolean {
    if (!this.root || !this.isShown()) return false;
    this.raycaster.setFromCamera(ndc, camera);
    const hits = this.raycaster.intersectObject(this.root, true).filter((h) => h.object instanceof Mesh);
    if (hits.length === 0) return false;
    this.forceSpeak = true;
    this.triggerInteraction();
    this.forceSpeak = false;
    return true;
  }

  triggerInteraction(): void {
    if (this.queue.length > 0) return; // ignore taps while an interaction is playing
    const names = this.cfg.interactionAnimations.filter((n) => this.clips.has(n));
    if (names.length === 0 || !this.mixer) return;
    // Random pick, never the same clip twice in a row.
    const pool = names.length > 1 ? names.filter((n) => n !== this.lastName) : names;
    const name = pool[Math.floor(Math.random() * pool.length)];
    this.lastName = name;
    this.autoTimer = this.nextAutoDelay();
    this.queue = [name];
    this.say(name, this.clips.get(name)!.duration);
    const action = this.mixer.clipAction(this.clips.get(name)!);
    action.reset().setLoop(LoopOnce, 1);
    action.clampWhenFinished = false;
    this.current?.fadeOut(0.15);
    action.fadeIn(0.15).play();
    this.current = action;
  }

  /** Play one named clip now (used by the show director). @returns clip length in seconds, 0 if missing. */
  play(name: string): number {
    const clip = this.clips.get(name);
    if (!clip || !this.mixer) return 0;
    this.queue = [name];
    this.lastName = name;
    this.autoTimer = this.nextAutoDelay();
    this.say(name, clip.duration);
    const action = this.mixer.clipAction(clip);
    action.reset().setLoop(LoopOnce, 1);
    action.clampWhenFinished = false;
    this.current?.fadeOut(0.15);
    action.fadeIn(0.15).play();
    this.current = action;
    return clip.duration;
  }

  private onClipFinished(): void {
    if (this.queue.length === 0) return;
    this.queue = [];
    this.playIdle();
  }

  dispose(): void {
    this.mixer?.stopAllAction();
    this.bubbleTex.forEach((e) => e.tex.dispose());
    this.bubbleTex.clear();
    this.bubble?.material.dispose();
    this.bubble = null;
    if (this.root) {
      this.mixer?.uncacheRoot(this.root);
      this.holder?.removeFromParent();
      this.root.traverse((o) => {
        if (o instanceof Mesh) {
          o.geometry.dispose();
          const mats = Array.isArray(o.material) ? o.material : [o.material];
          mats.forEach((m) => m.dispose());
        }
      });
    }
    this.root = null;
    this.holder = null;
    this.toggled = [];
    this.mixer = null;
    this.clips.clear();
  }
}
