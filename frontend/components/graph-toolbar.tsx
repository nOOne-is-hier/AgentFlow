"use client";

import { useState } from "react";
import { Play, Save, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { Workflow } from "@/types";

interface GraphToolbarProps {
  workflow?: Workflow | null;
  onExecute?: (runId: string) => void;
  onSave?: () => void;
  className?: string;
  isPipelineComplete?: boolean;
}

export function GraphToolbar({
  workflow,
  onExecute,
  onSave,
  className,
  isPipelineComplete,
}: GraphToolbarProps) {
  const { toast } = useToast();
  const [isExecuting, setIsExecuting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const effectiveIsExecuting = isExecuting && !isPipelineComplete;

  const handleExecute = async () => {
    if (!workflow) {
      toast({
        title: "워크플로우 없음",
        description: "실행할 워크플로우가 없습니다.",
        variant: "destructive",
      });
      return;
    }

    setIsExecuting(true);
    try {
      const saveResponse = await api.saveWorkflow(workflow);
      const workflowId = saveResponse.id;

      if (!workflowId) {
        throw new Error("워크플로우 ID를 받지 못했습니다.");
      }

      const executeResponse = await api.executePipeline(workflowId);
      onExecute?.(executeResponse.runId);

      toast({
        title: "파이프라인 실행 시작",
        description: `실행 ID: ${executeResponse.runId.slice(0, 8)}...`,
      });
    } catch (error) {
      console.error("[v0] Execute error:", error);
      toast({
        title: "실행 실패",
        description:
          error instanceof Error ? error.message : "다시 시도해주세요.",
        variant: "destructive",
      });
      setIsExecuting(false);
    }
  };

  const handleSave = async () => {
    if (!workflow) {
      toast({
        title: "워크플로우 없음",
        description: "저장할 워크플로우가 없습니다.",
        variant: "destructive",
      });
      return;
    }

    setIsSaving(true);
    try {
      await api.saveWorkflow(workflow);
      onSave?.();

      toast({
        title: "저장 완료",
        description: "워크플로우가 저장되었습니다.",
      });
    } catch (error) {
      toast({
        title: "저장 실패",
        description:
          error instanceof Error ? error.message : "다시 시도해주세요.",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={className}>
      <div className="flex items-center gap-2 p-2 border-b bg-card">
        <Button
          variant="default"
          size="sm"
          onClick={handleExecute}
          disabled={!workflow || effectiveIsExecuting}
          className="bg-sk-red hover:bg-sk-red/90"
        >
          {effectiveIsExecuting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Play className="h-4 w-4 mr-2" />
          )}
          실행
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={handleSave}
          disabled={!workflow || isSaving}
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Save className="h-4 w-4 mr-2" />
          )}
          저장
        </Button>

        <div className="flex-1" />

        {workflow && (
          <div className="text-xs text-muted-foreground">
            {workflow.nodes.length}개 노드 • {workflow.edges.length}개 엣지
          </div>
        )}
      </div>
    </div>
  );
}
