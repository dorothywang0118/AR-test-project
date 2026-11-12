import { Color, DoubleSide, Group, Mesh, MeshBasicMaterial, PlaneGeometry, Quaternion, Vector2, Vector3, type Object3D } from 'three';
import type { CampaignManifest } from '@shared/types/campaign';
import { ARError, type AREngineAdapter } from '../ar/adapters/AREngineAdapter';
import { addDefaultLights, CharacterController } from '../ar/renderer/CharacterController';
import { ShowDirector } from '../ar/renderer/ShowDirector';
import { Speaker } from '../ar/speech';
import { loadManifest, resolveUrl } from '../services/campaignService';

type Screen = 'intro' | 'loading' | 'error' | 'ar';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const ERROR_TEXT: Record<string, { title: string; body: string }> = {
  CAMERA_DENIED: {
    title: '需要相機權限',
    body:
      '您沒有允許使用相機。請這樣開啟：\n' +
      'iPhone：設定 → Safari → 相機 → 選「詢問」或「允許」，回到此頁重新整理。\n' +
      'Android Chrome：點網址列左側的鎖頭圖示 → 權限 → 相機 → 允許，然後重新整理。',
  },
  CAMERA_UNAVAILABLE: { title: '找不到相機', body: '請確認手機相機沒有被其他 App 佔用，然後重新嘗試。' },
  INSECURE_CONTEXT: { title: '網址不安全', body: '相機只能在 HTTPS 網址使用。請使用門市提供的正式 QR Code。' },
  UNSUPPORTED: { title: '瀏覽器不支援', body: '請改用 iPhone 的 Safari 或 Android 的 Chrome 開啟本頁。' },
  TARGET_LOAD_FAILED: { title: '活動資料載入失敗', body: '請檢查網路連線後重新嘗試。' },
  UNKNOWN: { title: '發生未預期的問題', body: '請重新嘗試；若仍失敗，請告知店員。' },
};

/** Orchestrates one AR session: manifest → engine → characters → camera. Re-startable. */
export class ArExperience {
  private adapter: AREngineAdapter | null = null;
  private characters: CharacterController[] = []; // several characters can share one target
  private shows = new Map<string, ShowDirector>(); // targetId → scripted group scene
  /** One stage per target: follows the tracked anchor through a smoothing filter (steadier picture), holds backdrop + characters. */
  private stages = new Map<string, { group: Group; backdrop: Mesh | null; init: boolean; t: number; prev: Vector3 }>();
  private removeLights: (() => void) | null = null;
  private manifest: CampaignManifest | null = null;
  private speaker = new Speaker();
  private debug = new URLSearchParams(location.search).has('debug');
  private startedAt = 0;
  private firstFoundMs: number | null = null;
  private foundEvents = 0;
  private lostEvents = 0;
  private lastTargetState = '—';
  private visible = new Set<string>();
  private taps = 0;
  private tapHits = 0;
  private frames = 0;
  private fps = 0;
  private fpsStamp = 0;
  private tapHandler: ((e: PointerEvent) => void) | null = null;

  async boot(): Promise<void> {
    $('btn-start').addEventListener('click', () => void this.start());
    $('btn-retry').addEventListener('click', () => void this.start());
    $('btn-stop').addEventListener('click', () => void this.stop());
    $('btn-sound').addEventListener('click', () => {
      $('btn-sound').textContent = this.speaker.toggle() ? '🔊' : '🔇';
    });
    if (/Line\/|FBAN|FBAV|Instagram|MicroMessenger/i.test(navigator.userAgent)) $('inapp-warning').hidden = false;
    try {
      this.manifest = await loadManifest();
      $('intro-title').textContent = this.manifest.name;
      $('intro-desc').textContent = this.manifest.description;
    } catch (e) {
      console.error(e);
      this.showError(new ARError('TARGET_LOAD_FAILED', 'manifest', e));
    }
  }

  private show(s: Screen, text?: string): void {
    $('screen-intro').hidden = s !== 'intro';
    $('screen-loading').hidden = s !== 'loading';
    $('screen-error').hidden = s !== 'error';
    $('hud').hidden = s !== 'ar';
    if (text) $('loading-text').textContent = text;
  }

  private showError(err: unknown): void {
    const code = err instanceof ARError ? err.code : 'UNKNOWN';
    console.error('[AR error]', code, err);
    const t = ERROR_TEXT[code] ?? ERROR_TEXT.UNKNOWN;
    $('error-title').textContent = t.title;
    $('error-body').textContent = t.body;
    $('error-body').style.whiteSpace = 'pre-line';
    this.show('error');
  }

  private async start(): Promise<void> {
    if (!this.manifest) {
      this.manifest = await loadManifest().catch(() => null);
      if (!this.manifest) return this.showError(new ARError('TARGET_LOAD_FAILED', 'manifest'));
    }
    const m = this.manifest;
    this.speaker.unlock(); // iOS: speech may only start from a tap, and this runs inside the Start tap
    await this.teardown(); // clean slate on retry
    this.show('loading', '準備 AR 引擎…');
    this.startedAt = performance.now();
    this.firstFoundMs = null;
    this.foundEvents = this.lostEvents = 0;
    this.lastTargetState = '—';
    this.taps = this.tapHits = 0;
    try {
      // Code-split: the ~2.5 MB engine is only downloaded when the customer taps Start.
      const { MindARAdapter } = await import('../ar/adapters/MindARAdapter');
      const adapter = new MindARAdapter();
      this.adapter = adapter;
      await adapter.initialize($('ar-container'));

      this.show('loading', '載入圖案辨識資料…');
      await adapter.loadTargets(resolveUrl(m.trackingAsset.url), m.trackingAsset.targetOrder);

      const ctx = adapter.getRenderContext();
      this.removeLights = addDefaultLights(ctx.scene);
      this.renderer = ctx.renderer;

      this.show('loading', '載入 3D 角色…');
      for (const tgt of m.targets) {
        const group = new Group();
        group.visible = false;
        ctx.scene.add(group);
        let backdrop: Mesh | null = null;
        if (m.backdrop) {
          backdrop = new Mesh(
            new PlaneGeometry(1.06, 1.06),
            new MeshBasicMaterial({ color: new Color(m.backdrop.color), side: DoubleSide, toneMapped: false }),
          );
          backdrop.position.z = 0.003;
          group.add(backdrop);
        }
        this.stages.set(tgt.id, { group, backdrop, init: false, t: 0, prev: new Vector3() });
      }
      for (const exp of m.experiences) {
        const def = m.characters.find((c) => c.id === exp.characterId);
        if (!def) throw new Error(`character ${exp.characterId} missing in manifest`);
        const ctrl = new CharacterController(exp, def.phrases);
        ctrl.onSay = (text, _id, force) => this.speaker.speak(text, def.voice, force);
        await ctrl.load(resolveUrl(def.modelUrl), this.stages.get(exp.targetId)!.group);
        this.characters.push(ctrl);
      }

      for (const show of m.shows ?? []) {
        const chars = new Map<string, CharacterController>();
        this.characters.filter((c) => c.targetId === show.targetId).forEach((c) => chars.set(c.characterId, c));
        this.shows.set(show.targetId, new ShowDirector(show, chars));
      }

      adapter.onTargetFound((id) => {
        this.foundEvents++;
        this.visible.add(id);
        this.lastTargetState = `found ${id}`;
        if (this.firstFoundMs === null) this.firstFoundMs = Math.round(performance.now() - this.startedAt);
        this.characters.forEach((c) => c.reset(id));
        this.shows.get(id)?.start();
        $('hint').textContent = '找到了！點一下小人偶試試看';
        $('hint').classList.add('found');
      });
      adapter.onTargetLost((id) => {
        this.lostEvents++;
        this.visible.delete(id);
        this.lastTargetState = `lost ${id}`;
        this.shows.get(id)?.stop();
        this.speaker.cancel();
        $('hint').textContent = '請將相機對準禮物盒圖案';
        $('hint').classList.remove('found');
      });
      const anchors = new Map(m.targets.map((t) => [t.id, adapter.getAnchor(t.id)]));
      adapter.onFrame((dt) => {
        this.followAnchors(anchors, dt);
        this.shows.forEach((s) => s.update(dt));
        this.characters.forEach((c) => c.update(dt));
        this.tickDebug();
      });

      // Taps are caught on the container (MindAR layers a CSS3D element on top of the canvas).
      const container = $('ar-container');
      this.tapHandler = (e) => {
        const r = container.getBoundingClientRect();
        const ndc = new Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
        let hit = false;
        this.characters.forEach((c) => (hit = c.tryTap(ndc, ctx.camera) || hit));
        this.taps++;
        if (hit) this.tapHits++;
      };
      container.addEventListener('pointerdown', this.tapHandler);

      this.show('loading', '啟動相機…');
      await adapter.startCamera();
      this.show('ar');
      $('debug').hidden = !this.debug;
      $('hint').textContent = '請將相機對準禮物盒圖案';
      $('hint').classList.remove('found');
    } catch (e) {
      await this.teardown();
      this.showError(e);
    }
  }

  private renderer: { info: { render: { calls: number; triangles: number } } } | null = null;
  private p = new Vector3();
  private q = new Quaternion();
  private sc = new Vector3();

  /**
   * Copy each tracked anchor's pose onto its stage through a low-pass filter: tiny tracking noise is
   * smoothed away (no more trembling), fast phone movement is followed quickly.
   */
  private followAnchors(anchors: Map<string, Object3D>, dt: number): void {
    this.stages.forEach((st, id) => {
      const a = anchors.get(id);
      st.group.visible = !!a?.visible;
      if (!a || !a.visible) {
        st.init = false;
        return;
      }
      a.matrix.decompose(this.p, this.q, this.sc);
      if (!st.init) {
        st.group.position.copy(this.p);
        st.group.quaternion.copy(this.q);
        st.group.scale.copy(this.sc);
        st.prev.copy(this.p);
        st.init = true;
        st.t = 0;
      } else {
        const dist = this.p.distanceTo(st.group.position) / Math.max(this.sc.x, 1e-6);
        const rate = 10 + 60 * Math.min(1, dist / 0.15); // still → 10/s (steady), moving fast → 70/s (keeps up)
        const k = 1 - Math.exp(-dt * rate);
        st.group.position.lerp(this.p, k);
        st.group.quaternion.slerp(this.q, k);
        st.group.scale.lerp(this.sc, k);
      }
      if (st.backdrop && st.t < 1) {
        st.t = Math.min(1, st.t + dt / 0.35); // backdrop pops in
        const e = 1 - Math.pow(1 - st.t, 3);
        st.backdrop.scale.setScalar(Math.max(e, 0.001));
      }
    });
  }

  private tickDebug(): void {
    this.frames++;
    const now = performance.now();
    if (now - this.fpsStamp >= 1000) {
      this.fps = Math.round((this.frames * 1000) / (now - this.fpsStamp));
      this.frames = 0;
      this.fpsStamp = now;
      if (this.debug) {
        $('debug').textContent =
          `render fps: ${this.fps}\n` +
          `draw calls: ${this.renderer?.info.render.calls ?? '—'}  tris: ${this.renderer?.info.render.triangles ?? '—'}\n` +
          `first detect: ${this.firstFoundMs ?? '—'} ms (from tap Start)\n` +
          `found/lost events: ${this.foundEvents}/${this.lostEvents}\n` +
          `target: ${this.lastTargetState}\n` +
          `visible: ${[...this.visible].join(',') || '—'}\n` +
          `taps hit/total: ${this.tapHits}/${this.taps}\n` +
          `dpr: ${window.devicePixelRatio}  ${innerWidth}x${innerHeight}\n` +
          `UA: ${navigator.userAgent}`;
      }
    }
  }

  async stop(): Promise<void> {
    await this.teardown();
    $('intro-status').textContent = '相機已關閉。';
    this.show('intro');
  }

  /** Release camera, GPU, web worker, DOM listeners. Must leave nothing behind. */
  private async teardown(): Promise<void> {
    if (this.tapHandler) $('ar-container').removeEventListener('pointerdown', this.tapHandler);
    this.tapHandler = null;
    this.speaker.cancel();
    this.characters.forEach((c) => c.dispose());
    this.characters = [];
    this.shows.clear();
    this.stages.forEach((s) => {
      s.group.removeFromParent();
      s.group.traverse((o) => {
        if (o instanceof Mesh) {
          o.geometry.dispose();
          (o.material as MeshBasicMaterial).dispose();
        }
      });
    });
    this.stages.clear();
    this.removeLights?.();
    this.removeLights = null;
    if (this.adapter) {
      await this.adapter.stop();
      this.adapter.dispose();
      this.adapter = null;
    }
  }
}
