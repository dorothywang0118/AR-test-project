/**
 * Campaign manifest — the single JSON document the customer app needs to run
 * one campaign version. In the final platform the admin CMS generates it and
 * stores it as an immutable file (see docs/architecture.md, "Versioning").
 * For the Task 01 POC it is a hand-written file: frontend/customer/public/campaign/campaign.json
 */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface TargetDef {
  /** Stable business ID, e.g. "TARGET-001". Never the engine's numeric index. */
  id: string;
  name: string;
}

export interface TrackingAssetDef {
  /** Engine-specific compiled recognition data (MindAR: a .mind file). */
  url: string;
  /** Engine: which AR engine this asset was compiled for. */
  engine: 'mindar';
  /** Order of targets inside the compiled file. Index i === engine targetIndex i. */
  targetOrder: string[];
}

export interface CharacterDef {
  id: string;
  name: string;
  /** GLB / glTF model URL (versioned file name or ?v=hash to defeat caches). */
  modelUrl: string;
}

export interface ExperienceDef {
  targetId: string;
  characterId: string;
  /** Uniform scale. 1 unit = the width of the printed target image. */
  scale: number;
  position: Vec3;
  /** Euler rotation in DEGREES. x:0 = model upright against the target plane (wall posters); x:90 = standing out of a flat table target. */
  rotation: Vec3;
  idleAnimation: string;
  /** false = no random self-play (used when a show director drives the characters). Default true. */
  autoPlay?: boolean;
  /** Pool of clips; each tap (or the idle timer) plays one at random, never the same twice in a row, then back to idle. */
  interactionAnimations: string[];
}

/** A scripted scene for characters sharing one target: steps run one after another, then loop. */
export interface ShowDef {
  targetId: string;
  steps: {
    /** characterId → clip name. Every clip in a step starts together; the step ends when the longest finishes. */
    clips: Record<string, string>;
  }[];
}

export interface CampaignManifest {
  schemaVersion: 1;
  campaignId: string;
  /** Human-readable version label, e.g. "v3" or a content hash. */
  version: string;
  name: string;
  description: string;
  trackingAsset: TrackingAssetDef;
  targets: TargetDef[];
  characters: CharacterDef[];
  experiences: ExperienceDef[];
  shows?: ShowDef[];
}
