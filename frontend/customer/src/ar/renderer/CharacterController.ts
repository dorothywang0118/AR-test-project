import {
  AnimationAction,
  AnimationClip,
  AnimationMixer,
  AmbientLight,
  Camera,
  DirectionalLight,
  Euler,
  LoopOnce,
  LoopRepeat,
  MathUtils,
  Mesh,
  Object3D,
  Raycaster,
  Vector2,
  type Scene,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ExperienceDef } from '@shared/types/campaign';

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
  private root: Object3D | null = null;
  private mixer: AnimationMixer | null = null;
  private clips = new Map<string, AnimationClip>();
  private idle: AnimationAction | null = null;
  private current: AnimationAction | null = null;
  private queue: string[] = [];
  private lastName = '';
  private autoTimer = 0;
  private raycaster = new Raycaster();

  constructor(private readonly cfg: ExperienceDef) {
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
    root.scale.setScalar(this.cfg.scale);
    root.position.set(this.cfg.position.x, this.cfg.position.y, this.cfg.position.z);
    root.rotation.copy(
      new Euler(
        MathUtils.degToRad(this.cfg.rotation.x),
        MathUtils.degToRad(this.cfg.rotation.y),
        MathUtils.degToRad(this.cfg.rotation.z),
      ),
    );
    parent.add(root);
    this.root = root;

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
    if (this.queue.length === 0 && this.root && this.isShown()) {
      this.autoTimer -= deltaSeconds;
      if (this.autoTimer <= 0) this.triggerInteraction();
    }
  }

  /** Target found again → restart from idle so the character never reappears mid-jump. */
  reset(targetId?: string): void {
    if (targetId && targetId !== this.cfg.targetId) return;
    this.queue = [];
    this.autoTimer = this.nextAutoDelay();
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
    if (!this.root || !this.root.visible) return false;
    this.raycaster.setFromCamera(ndc, camera);
    const hits = this.raycaster.intersectObject(this.root, true).filter((h) => h.object instanceof Mesh);
    if (hits.length === 0) return false;
    this.triggerInteraction();
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
    const action = this.mixer.clipAction(this.clips.get(name)!);
    action.reset().setLoop(LoopOnce, 1);
    action.clampWhenFinished = false;
    this.current?.fadeOut(0.15);
    action.fadeIn(0.15).play();
    this.current = action;
  }

  private onClipFinished(): void {
    if (this.queue.length === 0) return;
    this.queue = [];
    this.playIdle();
  }

  dispose(): void {
    this.mixer?.stopAllAction();
    if (this.root) {
      this.mixer?.uncacheRoot(this.root);
      this.root.removeFromParent();
      this.root.traverse((o) => {
        if (o instanceof Mesh) {
          o.geometry.dispose();
          const mats = Array.isArray(o.material) ? o.material : [o.material];
          mats.forEach((m) => m.dispose());
        }
      });
    }
    this.root = null;
    this.mixer = null;
    this.clips.clear();
  }
}
