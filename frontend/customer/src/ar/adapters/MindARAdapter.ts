import { Clock, Vector2, type Object3D } from 'three';
import { MindARThree, type MindARAnchor } from 'mind-ar/dist/mindar-image-three.prod.js';
import { ARError, type AREngineAdapter, type ARRenderContext } from './AREngineAdapter';

/** MindAR (MIT) implementation of AREngineAdapter. Verified against mind-ar@1.2.5 + three@0.160.0. */
export class MindARAdapter implements AREngineAdapter {
  private container: HTMLElement | null = null;
  private mindar: MindARThree | null = null;
  private anchors = new Map<string, MindARAnchor>();
  private foundCb: (id: string) => void = () => {};
  private lostCb: (id: string) => void = () => {};
  private frameCb: (dt: number) => void = () => {};
  private clock = new Clock();
  private running = false;
  private disposed = false;

  async initialize(container: HTMLElement): Promise<void> {
    if (!window.isSecureContext) {
      throw new ARError('INSECURE_CONTEXT', '此頁面不是 HTTPS，手機瀏覽器不允許開啟相機。');
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new ARError('UNSUPPORTED', '此瀏覽器不支援相機功能。');
    }
    this.container = container;
  }

  async loadTargets(trackingAssetUrl: string, targetIds: string[]): Promise<void> {
    if (!this.container) throw new ARError('UNKNOWN', 'initialize() must be called first');
    // Fail early with a clear error instead of an opaque failure deep inside MindAR.
    try {
      const res = await fetch(trackingAssetUrl, { method: 'HEAD' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      throw new ARError('TARGET_LOAD_FAILED', '無法載入圖案辨識資料。', e);
    }
    this.mindar = new MindARThree({
      container: this.container,
      imageTargetSrc: trackingAssetUrl,
      maxTrack: 1, // one scan image → one scene; never show two targets at once
      // We draw our own loading / scanning / error UI, so turn MindAR's built-in UI off.
      uiLoading: 'no',
      uiScanning: 'no',
      uiError: 'no',
      // Tolerances: how many frames to keep the target after it is briefly lost / before showing it.
      missTolerance: 5,
      warmupTolerance: 5,
      // One-euro filter: lower cutoff = steadier picture when the phone is held still (less shaking).
      filterMinCF: 0.0002,
      filterBeta: 500,
    });
    targetIds.forEach((id, index) => {
      const anchor = this.mindar!.addAnchor(index);
      anchor.onTargetFound = () => this.foundCb(id);
      anchor.onTargetLost = () => this.lostCb(id);
      this.anchors.set(id, anchor);
    });
  }

  async startCamera(): Promise<void> {
    const mindar = this.mindar;
    if (!mindar) throw new ARError('UNKNOWN', 'loadTargets() must be called first');

    // MindAR rejects with no error object when the camera fails, so probe the camera
    // ourselves first to tell "permission denied" apart from "no camera".
    await this.probeCamera();

    try {
      await mindar.start();
    } catch (e) {
      throw new ARError('UNKNOWN', 'AR 引擎啟動失敗。', e);
    }
    this.running = true;
    this.clock.start();
    // Heat: cap the render resolution and draw at most ~30 frames per second.
    const size = mindar.renderer.getSize(new Vector2());
    mindar.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    mindar.renderer.setSize(size.x, size.y, false);
    let lastDraw = 0;
    mindar.renderer.setAnimationLoop((now: number) => {
      this.frameCb(this.clock.getDelta());
      if (now - lastDraw >= 30) {
        lastDraw = now;
        mindar.renderer.render(mindar.scene, mindar.camera);
      }
    });
  }

  private async probeCamera(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      stream.getTracks().forEach((t) => t.stop());
    } catch (e) {
      const name = (e as DOMException)?.name;
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        throw new ARError('CAMERA_DENIED', '相機權限被拒絕。', e);
      }
      throw new ARError('CAMERA_UNAVAILABLE', '找不到可用的相機，或相機正被其他程式使用。', e);
    }
  }

  onTargetFound(cb: (id: string) => void): void {
    this.foundCb = cb;
  }
  onTargetLost(cb: (id: string) => void): void {
    this.lostCb = cb;
  }
  onFrame(cb: (dt: number) => void): void {
    this.frameCb = cb;
  }

  getAnchor(targetId: string): Object3D {
    const a = this.anchors.get(targetId);
    if (!a) throw new ARError('UNKNOWN', `Unknown target id: ${targetId}`);
    return a.group;
  }

  getRenderContext(): ARRenderContext {
    if (!this.mindar) throw new ARError('UNKNOWN', 'loadTargets() must be called first');
    return { scene: this.mindar.scene, camera: this.mindar.camera, renderer: this.mindar.renderer };
  }

  async stop(): Promise<void> {
    const m = this.mindar;
    if (!m || !this.running) return;
    this.running = false;
    m.renderer.setAnimationLoop(null);
    try {
      // MindAR.stop() stops tracking + camera tracks, but throws if no stream was attached.
      if (m.video?.srcObject) m.stop();
    } catch (e) {
      console.warn('[MindARAdapter] stop() raised', e);
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    const m = this.mindar;
    if (!m) return;
    this.running = false;
    m.renderer.setAnimationLoop(null);
    try {
      m.controller?.dispose(); // terminates MindAR's tracking web worker
    } catch (e) {
      console.warn('[MindARAdapter] controller.dispose() raised', e);
    }
    // MindAR registers an un-removable window 'resize' listener. Detaching `video`
    // makes that listener return immediately (see MindARThree.resize) instead of crashing.
    // Also stop any camera tracks left open when start() failed half-way.
    (m.video?.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
    m.video?.remove();
    m.video = null;
    m.scene.clear();
    m.renderer.dispose();
    m.renderer.forceContextLoss();
    m.renderer.domElement.remove();
    this.container?.querySelectorAll('video, canvas, div').forEach((el) => el.remove()); // CSS3D layer
    this.anchors.clear();
    this.mindar = null;
  }
}
