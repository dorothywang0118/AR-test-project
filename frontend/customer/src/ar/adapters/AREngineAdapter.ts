import type { Object3D, Scene, Camera, WebGLRenderer } from 'three';

/**
 * Everything the rest of the app is allowed to know about an AR engine.
 * UI, character logic and (later) CMS preview code depend ONLY on this file,
 * so swapping MindAR for another engine means writing one new adapter.
 *
 * Differences from the sketch in the spec (SRS §3.3), and why:
 *  - `initialize(container)` receives the DOM node the engine renders into.
 *  - `loadTargets` also takes the business target IDs, so callers never see engine indexes.
 *  - `getAnchor()` / `getRenderContext()` let the app attach 3D content without
 *    knowing the engine's internals. (Engines that own the Three.js scene, like
 *    MindAR, expose it here; an engine with its own renderer would need extra work.)
 *  - `startCamera()` starts camera AND tracking, because MindAR cannot do one without the other.
 */
export type ARErrorCode =
  | 'INSECURE_CONTEXT' // page is not HTTPS
  | 'UNSUPPORTED' // no camera API in this browser / in-app browser
  | 'CAMERA_DENIED' // user (or OS) refused camera permission
  | 'CAMERA_UNAVAILABLE' // no camera, or camera busy
  | 'TARGET_LOAD_FAILED' // recognition data could not be fetched / parsed
  | 'UNKNOWN';

export class ARError extends Error {
  constructor(
    public readonly code: ARErrorCode,
    message: string,
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = 'ARError';
  }
}

export interface ARRenderContext {
  scene: Scene;
  camera: Camera;
  renderer: WebGLRenderer;
}

export interface AREngineAdapter {
  initialize(container: HTMLElement): Promise<void>;
  loadTargets(trackingAssetUrl: string, targetIds: string[]): Promise<void>;
  startCamera(): Promise<void>;
  onTargetFound(callback: (targetId: string) => void): void;
  onTargetLost(callback: (targetId: string) => void): void;
  /** Called once per rendered frame with seconds since the previous frame. */
  onFrame(callback: (deltaSeconds: number) => void): void;
  /** Object3D that follows the physical target. Add your 3D content as its child. */
  getAnchor(targetId: string): Object3D;
  getRenderContext(): ARRenderContext;
  /** Stop camera and tracking. Safe to call more than once. */
  stop(): Promise<void>;
  /** Free GPU / DOM resources. After this the adapter must not be reused. */
  dispose(): void;
}
