"use client";

import type React from "react";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EventCard } from "@/components/event-card";
import { HITLApprovalBar } from "@/components/hitl-approval-bar";
import { ValidationReportCard } from "@/components/validation-report";
import { useSSE } from "@/hooks/use-sse";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { SSEEvent, ValidationReport, Workflow } from "@/types";

interface ChatPanelProps {
  onWorkflowUpdate?: (workflow: Workflow) => void;
  onRunStart?: (runId: string) => void;
  currentRunId?: string | null;
  onPipelineComplete?: () => void;
}

export function ChatPanel({
  onWorkflowUpdate,
  onRunStart,
  currentRunId,
  onPipelineComplete,
}: ChatPanelProps) {
  const { toast } = useToast();
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<SSEEvent[]>([]);
  const [isWaitingHITL, setIsWaitingHITL] = useState(false);
  const [validationReport, setValidationReport] = useState<
    ValidationReport | undefined
  >();
  const [isExecuting, setIsExecuting] = useState(false);
  const [pipelineCompleted, setPipelineCompleted] = useState(false);
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sseUrl = currentRunId ? api.getEventStream(currentRunId) : null;

  const { events: sseEvents, isConnected } = useSSE(sseUrl, {
    onEvent: (event) => {
      console.log("[v0] SSE Event received:", event);

      if (event.event === "OBS" && event.data?.node_id === "hitl") {
        if (event.data?.message === "WAITING_HITL") {
          setIsWaitingHITL(true);
        }
        if (
          event.data?.message === "STATE_CHECKPOINT" &&
          event.data?.detail?.state?.validation_report
        ) {
          setValidationReport(event.data.detail.state.validation_report);
        }
      }

      if (
        event.event === "OBS" &&
        event.data?.node_id === "export" &&
        event.data?.detail?.artifact_id
      ) {
        setArtifactId(event.data.detail.artifact_id);
      }

      if (event.event === "SUMMARY") {
        setIsExecuting(false);
        setPipelineCompleted(true);
        onPipelineComplete?.();

        if (event.data?.message?.includes("실패")) {
          toast({
            title: "파이프라인 오류",
            description: event.data.message || "실행 중 오류가 발생했습니다.",
            variant: "destructive",
          });
        }
      }
    },
  });

  useEffect(() => {
    if (sseEvents.length > 0) {
      setMessages((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const newEvents = sseEvents.filter((e) => !existingIds.has(e.id));
        return [...prev, ...newEvents];
      });
    }
  }, [sseEvents]);

  useEffect(() => {
    if (currentRunId) {
      setIsExecuting(true);
      setPipelineCompleted(false);
      setArtifactId(null);
    }
  }, [currentRunId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userInput = input.trim();
    setInput("");
    setIsLoading(true);

    const userEvent: SSEEvent = {
      id: Date.now().toString(),
      event: "USER",
      data: {
        text: `**사용자:** ${userInput}`,
      },
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userEvent]);

    try {
      const response = await api.chatTurn({ message: userInput });

      const assistantEvent: SSEEvent = {
        id: (Date.now() + 1).toString(),
        event: "ASSISTANT",
        data: {
          text: response.assistant,
        },
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantEvent]);

      if (response.graphPatch) {
        const workflow: Workflow = {
          id: `wf-${Date.now()}`,
          name: "Budget Validation",
          nodes: response.graphPatch.addNodes,
          edges: response.graphPatch.addEdges,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        onWorkflowUpdate?.(workflow);

        toast({
          title: "워크플로우 생성 완료",
          description: "그래프 툴바에서 '실행' 버튼을 클릭하세요.",
        });
      }
    } catch (error) {
      console.error("[v0] Chat turn error:", error);
      toast({
        title: "메시지 전송 실패",
        description:
          error instanceof Error ? error.message : "다시 시도해주세요.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprovalComplete = () => {
    setIsWaitingHITL(false);
    toast({
      title: "승인 처리 완료",
      description: "파이프라인이 계속 진행됩니다.",
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="p-4 border-b shrink-0">
        <h2 className="text-lg font-semibold">채팅</h2>
        <div className="flex items-center gap-2 mt-1">
          {isExecuting && (
            <div className="flex items-center gap-1 text-xs text-sk-orange">
              <Loader2 className="h-3 w-3 animate-spin" />
              파이프라인 실행 중...
            </div>
          )}
          {currentRunId &&
            isConnected &&
            !isExecuting &&
            !pipelineCompleted && (
              <p className="text-xs text-green-600">● 실시간 연결됨</p>
            )}
          {currentRunId && !isConnected && !pipelineCompleted && (
            <div className="flex items-center gap-1 text-xs text-destructive">
              <AlertCircle className="h-3 w-3" />
              연결 끊김 (재연결 시도 중...)
            </div>
          )}
          {pipelineCompleted && (
            <p className="text-xs text-green-600">✓ 파이프라인 완료</p>
          )}
        </div>
      </div>

      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="space-y-3" aria-live="polite" aria-atomic="false">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-sm text-muted-foreground">
                메시지를 입력하여 대화를 시작하세요
              </p>
            </div>
          ) : (
            messages.map((event) => (
              <EventCard key={event.id} event={event} artifactId={artifactId} />
            ))
          )}

          {validationReport && !isWaitingHITL && (
            <ValidationReportCard report={validationReport} className="mt-4" />
          )}
        </div>
      </ScrollArea>

      {isWaitingHITL && currentRunId ? (
        <HITLApprovalBar
          runId={currentRunId}
          validationReport={validationReport}
          onApprovalComplete={handleApprovalComplete}
        />
      ) : (
        <div className="p-4 border-t shrink-0">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="예: PDF와 XLSX 파일을 병합하고 검증해주세요"
              className="min-h-[60px] resize-none"
              disabled={isLoading}
              aria-label="메시지 입력"
            />
            <Button
              type="submit"
              size="icon"
              disabled={isLoading || !input.trim()}
              className="shrink-0"
              aria-label="메시지 전송"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}

function MessageSquare({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}
