// MindAR ships no TypeScript types for its prebuilt Three.js bundle.
// Only the parts we actually use are declared here (checked against mind-ar@1.2.5 src/image-target/three.js).
declare module 'mind-ar/dist/mindar-image-three.prod.js' {
  import type { Scene, PerspectiveCamera, WebGLRenderer, Group } from 'three';

  export interface MindARAnchor {
    group: Group;
    targetIndex: number;
    onTargetFound: (() => void) | null;
    onTargetLost: (() => void) | null;
    onTargetUpdate: (() => void) | null;
  }

  export interface MindARThreeOptions {
    container: HTMLElement;
    imageTargetSrc: string;
    maxTrack?: number;
    uiLoading?: string;
    uiScanning?: string;
    uiError?: string;
    filterMinCF?: number | null;
    filterBeta?: number | null;
    warmupTolerance?: number | null;
    missTolerance?: number | null;
  }

  export class MindARThree {
    constructor(options: MindARThreeOptions);
    scene: Scene;
    camera: PerspectiveCamera;
    renderer: WebGLRenderer;
    video: HTMLVideoElement | null;
    controller: { dispose(): void } | undefined;
    addAnchor(targetIndex: number): MindARAnchor;
    start(): Promise<void>;
    stop(): void;
    resize(): void;
  }
}
