import type { TopoIconPreset } from './types';

const PALETTE = [
  '#8b5cf6',
  '#f97316',
  '#22c55e',
  '#ec4899',
  '#0891b2',
  '#0ea5e9',
  '#6366f1',
  '#f43f5e',
  '#d946ef',
  '#84cc16',
  '#eab308',
  '#14b8a6',
  '#64748b',
];

export const TOPO_ICON_RING_WIDTH = 2;
export const TOPO_ICON_GLYPH_STROKE_WIDTH = 1.8;

export interface TopoVisualIdentity {
  iconClass?: string;
  iconFill: string;
  iconPreset: TopoIconPreset;
  iconUrl?: string;
  lucideIcon?: string;
  ringWidth: number;
}

export function createTopoHashColorResolver(seeds: string[]) {
  const assigned = new Map<string, string>();
  const sortedSeeds = Array.from(new Set(seeds)).sort();
  sortedSeeds.forEach((seed, index) => {
    assigned.set(seed, PALETTE[index % PALETTE.length]);
  });
  return (seed: string) =>
    assigned.get(seed) || PALETTE[Math.floor(hashToUnit(seed) * PALETTE.length) % PALETTE.length];
}

export function getTopoTypeColorSeed(
  cluster: string,
  title?: string,
  data?: Record<string, unknown>,
  style?: Record<string, unknown>
) {
  const explicit = readString(style?.iconFill) || readString(style?.fill) || readString(data?.color);
  if (explicit) {return explicit;}
  return `${cluster || 'default'}:${title || ''}`;
}

export function resolveTopoVisualIdentity({
  cluster,
  title,
  data,
  style,
  fallbackColor,
}: {
  cluster: string;
  title?: string;
  data?: Record<string, unknown>;
  style?: Record<string, unknown>;
  fallbackColor?: string;
}): TopoVisualIdentity {
  const iconFill =
    readString(style?.iconFill) || readString(style?.fill) || readString(data?.color) || fallbackColor || '#6366f1';
  const iconPreset =
    normalizeTopoIconPreset(readString(style?.iconPreset) || readString(data?.iconPreset)) ||
    inferPreset(`${cluster} ${title || ''}`);
  return {
    iconClass: readString(style?.iconClass) || readString(data?.iconClass),
    iconFill,
    iconPreset,
    iconUrl: readString(style?.iconUrl) || readString(data?.iconUrl),
    lucideIcon: readString(style?.lucideIcon) || readString(data?.lucideIcon),
    ringWidth: Number(style?.ringWidth) > 0 ? Number(style?.ringWidth) : 2,
  };
}

export function getSvgIconId(iconClass?: string) {
  const value = readString(iconClass);
  if (!value) {return undefined;}
  return value.startsWith('#') ? value.slice(1) : value;
}

export function isGenericIconClass(iconClass?: string) {
  const value = readString(iconClass);
  if (!value) {return true;}
  return value === 'icon-ahas' || value === 'icon-default' || value === 'default';
}

export function resolveLucideIconPreset(value?: string): TopoIconPreset | undefined {
  if (!value) {return undefined;}
  const normalized = value.toLowerCase();
  if (normalized.includes('database')) {return 'database';}
  if (normalized.includes('server') || normalized.includes('box')) {return 'instance';}
  if (normalized.includes('network') || normalized.includes('globe')) {return 'network';}
  if (normalized.includes('route') || normalized.includes('workflow')) {return 'service';}
  if (normalized.includes('arrow') || normalized.includes('endpoint')) {return 'endpoint';}
  return undefined;
}

function inferPreset(value: string): TopoIconPreset {
  const text = value.toLowerCase();
  if (text.includes('service')) {return 'service';}
  if (text.includes('operation') || text.includes('endpoint') || text.includes('http')) {return 'endpoint';}
  if (text.includes('database') || text.includes('db')) {return 'database';}
  if (text.includes('redis')) {return 'redis';}
  if (text.includes('instance') || text.includes('host') || text.includes('node')) {return 'instance';}
  if (text.includes('pod')) {return 'pod';}
  if (text.includes('network') || text.includes('vpc')) {return 'network';}
  return 'default';
}

export function normalizeTopoIconPreset(value: string | undefined): TopoIconPreset | undefined {
  if (!value) {return undefined;}
  const normalized = value.toLowerCase();
  const allowed: TopoIconPreset[] = [
    'default',
    'service',
    'application',
    'deployment',
    'node',
    'instance',
    'pod',
    'database',
    'disk',
    'redis',
    'network',
    'loadbalancer',
    'endpoint',
  ];
  return allowed.includes(normalized as TopoIconPreset) ? (normalized as TopoIconPreset) : undefined;
}

function readString(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function hashToUnit(value: string) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}
