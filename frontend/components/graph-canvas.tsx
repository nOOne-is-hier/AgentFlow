"use client";

import { useEffect, memo, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  MarkerType,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import type { Workflow } from "@/types";
import { cn } from "@/lib/utils";

interface GraphCanvasProps {
  workflow?: Workflow | null;
  className?: string;
}

const NODE_TYPES_CONFIG = {
  parse_pdf: {
    label: "PDF 파싱",
    color: "bg-blue-500",
    textColor: "text-white",
  },
  embed_pdf: {
    label: "PDF 임베딩",
    color: "bg-purple-500",
    textColor: "text-white",
  },
  merge_xlsx: {
    label: "XLSX 병합",
    color: "bg-green-500",
    textColor: "text-white",
  },
  validate: {
    label: "검증",
    color: "bg-yellow-500",
    textColor: "text-white",
  },
  export: {
    label: "내보내기",
    color: "bg-sk-red",
    textColor: "text-white",
  },
};

const CustomNode = memo(function CustomNode({ data }: { data: any }) {
  const config = NODE_TYPES_CONFIG[
    data.type as keyof typeof NODE_TYPES_CONFIG
  ] || {
    label: data.label,
    color: "bg-gray-500",
    textColor: "text-white",
  };

  return (
    <div
      className={cn(
        "px-4 py-3 rounded-lg border-2 shadow-lg min-w-[150px]",
        config.color,
        config.textColor,
        "border-white/20"
      )}
    >
      <Handle type="target" position={Position.Left} />
      <div className="font-semibold text-sm">{config.label}</div>
      {data.label && data.label !== config.label && (
        <div className="text-xs opacity-80 mt-1">{data.label}</div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
});

const nodeTypes = {
  custom: CustomNode,
};

export function GraphCanvas({ workflow, className }: GraphCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const memoizedNodeTypes = useMemo(() => nodeTypes, []);

  useEffect(() => {
    if (!workflow) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const flowNodes: Node[] = workflow.nodes.map((node, index) => {
      const config =
        NODE_TYPES_CONFIG[node.type as keyof typeof NODE_TYPES_CONFIG];

      return {
        id: node.id,
        type: "custom",
        position: node.position || {
          x: 100 + (index % 3) * 250,
          y: 100 + Math.floor(index / 3) * 150,
        },
        data: {
          label: node.label,
          type: node.type,
        },
      };
    });

    const flowEdges: Edge[] = workflow.edges.map((edge, index) => ({
      id: `edge-${edge.from}-${edge.to}-${index}`,
      source: edge.from,
      target: edge.to,
      sourceHandle: null,
      targetHandle: null,
      type: "smoothstep",
      animated: true,
      style: { stroke: "#ea0029", strokeWidth: 2 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#ea0029",
      },
    }));

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [workflow, setNodes, setEdges]);

  if (!workflow) {
    return (
      <div
        className={cn(
          "flex h-full items-center justify-center bg-muted/20",
          className
        )}
      >
        <div className="text-center">
          <h2 className="text-2xl font-bold text-muted-foreground mb-2">
            그래프 캔버스
          </h2>
          <p className="text-sm text-muted-foreground">
            워크플로우를 생성하면 여기에 표시됩니다
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("h-full w-full", className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={memoizedNodeTypes}
        fitView
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const config =
              NODE_TYPES_CONFIG[
                node.data.type as keyof typeof NODE_TYPES_CONFIG
              ];
            return config?.color.replace("bg-", "#") || "#6b7280";
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
        />
      </ReactFlow>
    </div>
  );
}
