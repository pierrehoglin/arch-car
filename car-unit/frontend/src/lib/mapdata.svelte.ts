import * as api from './api/map';
import { RequestFailed } from './api/client';
import { on } from './api/stream.svelte';
import type { MapEstimate, MapInfo } from './api/map';

/* The offline map's files, for Settings > Map.
 *
 * Downloads run in the daemon and report over the event stream, so
 * a screen opened halfway through picks the progress up from the
 * replay, and leaving the screen does not stop anything.
 */

interface Store {
  info: MapInfo | null;
  /** Size of Sweden at the detail being looked at. */
  estimate: MapEstimate | null;
  estimating: boolean;
  checking: boolean;
  error: string;
}

export const mapData = $state<Store>({
  info: null,
  estimate: null,
  estimating: false,
  checking: false,
  error: ''
});

/* Plain, not reactive: which estimate is wanted now. A slow answer
   for a level the user has already moved off is dropped. */
let wanted: number | null = null;

function report(cause: unknown): void {
  mapData.error =
    cause instanceof RequestFailed || cause instanceof Error ? cause.message : String(cause);
}

export async function refresh(): Promise<void> {
  try {
    mapData.info = await api.status();
  } catch (cause) {
    report(cause);
  }
}

export async function checkLatest(): Promise<void> {
  mapData.checking = true;
  mapData.error = '';
  try {
    mapData.info = await api.checkLatest();
  } catch (cause) {
    report(cause);
  } finally {
    mapData.checking = false;
  }
}

export async function estimate(maxzoom: number): Promise<void> {
  wanted = maxzoom;
  mapData.estimating = true;
  mapData.estimate = null;
  try {
    const answer = await api.estimate(maxzoom);
    if (wanted === maxzoom) mapData.estimate = answer;
  } catch (cause) {
    if (wanted === maxzoom) report(cause);
  } finally {
    if (wanted === maxzoom) mapData.estimating = false;
  }
}

async function run(action: () => Promise<MapInfo>): Promise<void> {
  mapData.error = '';
  try {
    mapData.info = await action();
  } catch (cause) {
    report(cause);
  }
}

export const download = (maxzoom: number) => run(() => api.download(maxzoom));
export const downloadLabels = () => run(api.downloadLabels);
export const cancel = () => run(api.cancel);

/** Follow downloads. Returns the unsubscribe, for an $effect. */
export function watch(): () => void {
  return on('map', (data) => {
    mapData.info = data as MapInfo;
  });
}

/** A newer build than the one installed. False when either is
 *  unknown -- an archive put there by hand has no build to compare. */
export function updateAvailable(info: MapInfo | null): boolean {
  return !!(info?.latest && info.build && info.latest.build > info.build);
}

export const DETAIL_NAMES: Record<number, string> = {
  12: 'Low',
  13: 'Medium',
  14: 'High',
  15: 'Full'
};
