import type { TopoData, TopoGraphvizEngine } from './types';

export interface GraphvizLayoutResult {
  positions: Map<string, [number, number]>;
  clusterPositions: Map<string, [number, number]>;
}

export interface GraphvizLayoutOptions {
  engine: TopoGraphvizEngine;
  rankdir: 'TB' | 'BT' | 'LR' | 'RL';
  packClusters: boolean;
  packMode: 'cluster' | 'component';
}

export async function computeGraphvizLayout(
  data: TopoData,
  _options: GraphvizLayoutOptions
): Promise<GraphvizLayoutResult> {
  const positions = new Map<string, [number, number]>();
  const clusterPositions = new Map<string, [number, number]>();
  const byCluster = new Map<string, typeof data.nodes>();
  data.nodes.forEach((node) => {
    const key = String(node.data?.cluster || node.type || 'default');
    const list = byCluster.get(key);
    if (list) {list.push(node);}
    else {byCluster.set(key, [node]);}
  });

  const clusters = Array.from(byCluster.entries()).sort((left, right) => right[1].length - left[1].length);
  const columns = Math.max(1, Math.ceil(Math.sqrt(clusters.length || 1)));
  const spacingX = 720;
  const spacingY = 560;

  clusters.forEach(([cluster, nodes], clusterIndex) => {
    const col = clusterIndex % columns;
    const row = Math.floor(clusterIndex / columns);
    const cx = col * spacingX;
    const cy = row * spacingY;
    clusterPositions.set(cluster, [cx, cy]);
    nodes.forEach((node, index) => {
      const angle = index * 2.399963229728653;
      const radius = Math.sqrt(index + 0.5) * 42;
      positions.set(node.id, [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]);
    });
  });

  return { positions, clusterPositions };
}
