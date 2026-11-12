import { Vector2 } from 'three';
import type { CampaignManifest } from '@shared/types/campaign';
import { ARError, type AREngineAdapter } from '../ar/adapters/AREngineAdapter';
import { addDefaultLights, CharacterController } from '../ar/renderer/CharacterController';
import { ShowDirector } from '../ar/renderer/ShowDirector';
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
  private removeLights: (() => void) | null = null;
  private manifest: CampaignManifest | null = null;
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

      this.show('loading', '載入 3D 角色…');
      for (const exp of m.experiences) {
        const def = m.characters.find((c) => c.id === exp.characterId);
        if (!def) throw new Error(`character ${exp.characterId} missing in manifest`);
        const ctrl = new CharacterController(exp);
        await ctrl.load(resolveUrl(def.modelUrl), adapter.getAnchor(exp.targetId));
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
        $('hint').textContent = '請將相機對準禮物盒圖案';
        $('hint').classList.remove('found');
      });
      adapter.onFrame((dt) => {
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
    this.characters.forEach((c) => c.dispose());
    this.characters = [];
    this.shows.clear();
    this.removeLights?.();
    this.removeLights = null;
    if (this.adapter) {
      await this.adapter.stop();
      this.adapter.dispose();
      this.adapter = null;
    }
  }
}
