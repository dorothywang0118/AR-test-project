import type { CampaignManifest } from '@shared/types/campaign';

/**
 * Loads the campaign manifest. POC: static JSON next to the app.
 * Later: GET /api/campaigns/:id/manifest (published version only, SRS §7).
 * URLs inside the manifest are resolved relative to the page, so the app works on any sub-path.
 */
export async function loadManifest(url = 'campaign/campaign.json'): Promise<CampaignManifest> {
  const res = await fetch(new URL(url, document.baseURI), { cache: 'no-cache' });
  if (!res.ok) throw new Error(`manifest HTTP ${res.status}`);
  const m = (await res.json()) as CampaignManifest;
  if (m.schemaVersion !== 1) throw new Error(`unsupported manifest schema ${m.schemaVersion}`);
  return m;
}

export function resolveUrl(relative: string): string {
  return new URL(relative, document.baseURI).toString();
}
