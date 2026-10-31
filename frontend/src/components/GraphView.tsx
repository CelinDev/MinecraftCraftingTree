import React from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Position,
  MarkerType,
  type Node,
  type Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { DependencyNode } from '../types';
import { formatItemName } from '../utils';

interface GraphViewProps {
  rootNode: DependencyNode;
  onSelectNode: (itemKey: string) => void;
}

export const GraphView: React.FC<GraphViewProps> = ({ rootNode, onSelectNode }) => {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Build hierarchical layout coordinates with depth-layer grouping
  // Limit nodes to prevent browser freeze on gigantic 400+ step trees
  const MAX_GRAPH_NODES = 120;
  let nodeCount = 0;

  // Track Y offset per depth column
  const depthYMap: Record<number, number> = {};
  const levelXSpacing = 280;
  const nodeYSpacing = 100;

  function traverse(node: DependencyNode, depth: number, parentId?: string) {
    if (nodeCount >= MAX_GRAPH_NODES) return;
    nodeCount++;

    const currentDepthY = depthYMap[depth] || 50;
    const x = depth * levelXSpacing + 50;
    const y = currentDepthY;
    depthYMap[depth] = currentDepthY + nodeYSpacing;

    const isRaw = node.status === 'raw_material';
    const isCycle = node.status === 'circular';
    const isCatalyst = node.is_catalyst || node.status === 'catalyst';

    let borderColor = '#3b82f6';
    let bgColor = '#1e293b';

    if (isRaw) {
      borderColor = '#10b981';
      bgColor = '#064e3b';
    } else if (isCycle) {
      borderColor = '#ef4444';
      bgColor = '#7f1d1d';
    } else if (isCatalyst) {
      borderColor = '#eab308';
      bgColor = '#713f12';
    }

    const iconUrl = `/api/items/${encodeURIComponent(node.resource_id)}/icon`;

    nodes.push({
      id: node.node_id,
      position: { x, y },
      data: {
        label: (
          <div
            onClick={() => onSelectNode(node.item_key)}
            style={{
              cursor: 'pointer',
              padding: '8px 12px',
              borderRadius: '8px',
              backgroundColor: bgColor,
              border: `2px solid ${borderColor}`,
              color: '#f8fafc',
              fontSize: '11px',
              minWidth: '210px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.3)',
            }}
          >
            {/* Minecraft Item Texture Icon */}
            <div
              style={{
                width: '32px',
                height: '32px',
                minWidth: '32px',
                backgroundColor: '#0b1120',
                border: '1px solid #334155',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
              }}
            >
              <img
                src={iconUrl}
                alt={node.resource_id}
                style={{
                  width: '28px',
                  height: '28px',
                  imageRendering: 'pixelated',
                  objectFit: 'contain',
                }}
                onError={(e) => {
                  // Hide broken image placeholder
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            </div>

            <div style={{ flex: 1, overflow: 'hidden' }}>
              <div style={{ fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '125px', fontSize: '12px' }}
                  title={`${node.display_name || formatItemName(node.resource_id)} (${node.resource_id})`}
                >
                  {node.display_name || formatItemName(node.resource_id)}
                </span>
                <span style={{ color: '#93c5fd', marginLeft: '6px', fontSize: '11px', fontWeight: 'bold' }}>x{node.count}</span>
              </div>
              <div style={{ fontSize: '9px', color: '#94a3b8', marginTop: '1px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '85px' }}>
                  {node.mod_name || node.resource_id.split(':')[0]}
                </span>
                {node.station_id && (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }} title={`Máquina: ${node.station_name || node.station_id}`}>
                    <img
                      src={`/api/items/${encodeURIComponent(node.station_id)}/icon`}
                      alt="machine"
                      style={{ width: '16px', height: '16px', imageRendering: 'pixelated', objectFit: 'contain', borderRadius: '3px', border: '1px solid #475569', backgroundColor: '#0f172a' }}
                      onError={(e) => ((e.target as HTMLElement).style.display = 'none')}
                    />
                  </span>
                )}
              </div>
              {isCycle && (
                <div style={{ color: '#fca5a5', fontSize: '9px', marginTop: '2px' }}>
                  ⚠️ Ciclo detectado
                </div>
              )}
              {isCatalyst && (
                <div style={{ color: '#fde047', fontSize: '9px', marginTop: '2px' }}>
                  ⭐ Catalisador
                </div>
              )}
            </div>
          </div>
        ),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });

    if (parentId) {
      edges.push({
        id: `e_${parentId}_${node.node_id}`,
        source: parentId,
        target: node.node_id,
        animated: isCycle,
        style: { stroke: isCycle ? '#ef4444' : '#64748b', strokeWidth: 1.5 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isCycle ? '#ef4444' : '#64748b',
        },
      });
    }

    for (const child of node.children) {
      traverse(child, depth + 1, node.node_id);
    }
  }

  traverse(rootNode, 0);

  return (
    <div style={{ width: '100%', height: '550px', backgroundColor: '#0f172a', borderRadius: '12px' }}>
      {nodeCount >= MAX_GRAPH_NODES && (
        <div style={{ position: 'absolute', top: '12px', right: '12px', zIndex: 10, backgroundColor: '#1e293b', padding: '4px 10px', borderRadius: '6px', fontSize: '11px', color: '#94a3b8', border: '1px solid #334155' }}>
          Exibindo os primeiros 120 nós da árvore (veja a aba "Etapas" para a lista completa de passos)
        </div>
      )}
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background color="#334155" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            if (n.id.includes('raw')) return '#10b981';
            if (n.id.includes('circular')) return '#ef4444';
            return '#3b82f6';
          }}
          style={{ backgroundColor: '#1e293b' }}
        />
      </ReactFlow>
    </div>
  );
};
