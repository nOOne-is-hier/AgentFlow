"use client";

import type React from "react";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EventCard } from "@/components/event-card";
import { CardShimmer } from "@/components/card-shimmer";
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

const CARD_RENDER_DELAY = 800; // ms

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
  const [eventQueue, setEventQueue] = useState<SSEEvent[]>([]);
  const [isProcessingQueue, setIsProcessingQueue] = useState(false);
  const [pendingWorkflow, setPendingWorkflow] = useState<Workflow | null>(null);
  const [expectingMoreEvents, setExpectingMoreEvents] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const processingTimeoutRef = useRef<NodeJS.Timeout>();

  const sseUrl = currentRunId ? api.getEventStream(currentRunId) : null;

  const { events: sseEvents, isConnected } = useSSE(sseUrl, {
    onEvent: (event) => {
      console.log("[v0] SSE Event received:", event);

      if (event.has_more !== undefined) {
        setExpectingMoreEvents(event.has_more);
        console.log("[v0] Server signals more events:", event.has_more);
      }

      // Store validation report when received
      if (event.event === "OBS" && event.data?.node_id === "hitl") {
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
      setEventQueue((prev) => {
        const existingIds = new Set([
          ...messages.map((m) => m.id),
          ...prev.map((e) => e.id),
        ]);
        const newEvents = sseEvents.filter((e) => !existingIds.has(e.id));
        return [...prev, ...newEvents];
      });
    }
  }, [sseEvents, messages]);

  useEffect(() => {
    // Check if the most recent message is a HITL event
    const lastMessage = messages[messages.length - 1];
    if (
      lastMessage?.event === "OBS" &&
      lastMessage.data?.node_id === "hitl" &&
      lastMessage.data?.message === "WAITING_HITL"
    ) {
      setIsWaitingHITL(true);
    }
  }, [messages]);

  useEffect(() => {
    // Skip if queue is empty or already processing
    if (eventQueue.length === 0 || isProcessingQueue) {
      return;
    }

    const nextEvent = eventQueue[0];
    if (nextEvent?.event === "ASSISTANT") {
      console.log(
        "[v0] ASSISTANT card is next in queue, shimmer should be visible"
      );
    }

    console.log(
      "[v0] Starting queue processing, queue length:",
      eventQueue.length
    );
    setIsProcessingQueue(true);

    // Process one item after delay
    processingTimeoutRef.current = setTimeout(() => {
      setEventQueue((currentQueue) => {
        if (currentQueue.length === 0) {
          console.log("[v0] Queue is empty, skipping processing");
          return currentQueue;
        }

        const [nextEvent, ...remainingQueue] = currentQueue;
        console.log(
          "[v0] Processing event:",
          nextEvent.event,
          "Remaining:",
          remainingQueue.length
        );

        if (nextEvent.event === "ASSISTANT") {
          console.log(
            "[v0] ASSISTANT card is now being rendered after shimmer delay"
          );
        }

        setMessages((prev) => [...prev, nextEvent]);
        return remainingQueue;
      });

      // Mark processing as complete
      setIsProcessingQueue(false);
    }, CARD_RENDER_DELAY);

    // No cleanup function - let timeout complete naturally
    // The isProcessingQueue flag prevents multiple timeouts
  }, [eventQueue, isProcessingQueue]); // Depend on both queue length and processing state

  useEffect(() => {
    if (currentRunId) {
      setIsExecuting(true);
      setPipelineCompleted(false);
      setArtifactId(null);
      setExpectingMoreEvents(true);
    }
  }, [currentRunId]);

  useEffect(() => {
    if (scrollRef.current) {
      // Use requestAnimationFrame to ensure DOM has been updated
      requestAnimationFrame(() => {
        if (scrollRef.current) {
          // Radix ScrollArea has a viewport element that's the actual scrollable container
          const viewport = scrollRef.current.querySelector(
            "[data-radix-scroll-area-viewport]"
          ) as HTMLElement;
          if (viewport) {
            console.log(
              "[v0] Scrolling viewport to bottom, scrollHeight:",
              viewport.scrollHeight
            );
            viewport.scrollTo({
              top: viewport.scrollHeight,
              behavior: "smooth",
            });
          } else {
            console.log("[v0] Viewport not found, trying direct scroll");
            scrollRef.current.scrollTo({
              top: scrollRef.current.scrollHeight,
              behavior: "smooth",
            });
          }
        }
      });
    }
  }, [messages]);

  useEffect(() => {
    if (pendingWorkflow) {
      const hasAssistantCard = messages.some(
        (msg) => msg.event === "ASSISTANT"
      );
      if (hasAssistantCard) {
        console.log("[v0] ASSISTANT card rendered, updating graph");
        onWorkflowUpdate?.(pendingWorkflow);
        setPendingWorkflow(null); // Clear pending workflow
      }
    }
  }, [messages, pendingWorkflow, onWorkflowUpdate]);

  useEffect(() => {
    console.log("[v0] Shimmer state:", {
      showShimmer,
      queueLength: eventQueue.length,
      isProcessing: isProcessingQueue,
      pipelineCompleted,
      nextEventType: eventQueue[0]?.event,
    });
  }, [eventQueue, isProcessingQueue, pipelineCompleted]); // Depend on both queue length and processing state

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
    setEventQueue((prev) => [...prev, userEvent]);

    try {
      const response = await api.chatTurn({ message: userInput });

      const planningCards: SSEEvent[] = [];

      // 1. Input understanding card
      planningCards.push({
        id: (Date.now() + 1).toString(),
        event: "PLAN",
        data: {
          type: "PLAN",
          node_id: "system",
          message: "입력 이해",
          detail: {
            text: `서버가 다음 요청을 받았습니다: "${userInput}"\n\n분석 중...`,
          },
        },
        timestamp: new Date().toISOString(),
      });

      // 2. Planning card (from tot)
      if (response.tot && response.tot.steps) {
        planningCards.push({
          id: (Date.now() + 2).toString(),
          event: "PLAN",
          data: {
            type: "PLAN",
            node_id: "system",
            message: "계획 수립",
            detail: {
              text: `다음 단계로 처리합니다:\n${response.tot.steps
                .map((s: string, i: number) => `${i + 1}. ${s}`)
                .join("\n")}`,
            },
          },
          timestamp: new Date().toISOString(),
        });
      }

      // 3. Pipeline creation card (from graphPatch)
      if (response.graphPatch) {
        const workflow: Workflow = {
          id: `wf-${Date.now()}`,
          name: "Budget Validation",
          nodes: response.graphPatch.addNodes,
          edges: response.graphPatch.addEdges,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        // Store workflow to be applied after first PLAN card renders
        setPendingWorkflow(workflow);

        planningCards.push({
          id: (Date.now() + 3).toString(),
          event: "OBS",
          data: {
            type: "OBS",
            node_id: "system",
            message: "파이프라인 생성 완료",
            detail: {
              text: `워크플로우가 생성되었습니다.\n- 노드 수: ${response.graphPatch.addNodes.length}개\n- 연결 수: ${response.graphPatch.addEdges.length}개`,
            },
          },
          timestamp: new Date().toISOString(),
        });
      }

      // 4. Assistant response card
      planningCards.push({
        id: (Date.now() + 4).toString(),
        event: "ASSISTANT",
        data: {
          type: "ASSISTANT",
          text: response.assistant,
        },
        timestamp: new Date().toISOString(),
      });

      setEventQueue((prev) => [...prev, ...planningCards]);
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

  const showShimmer =
    eventQueue.length > 0 || isProcessingQueue || expectingMoreEvents;

  const hasAssistantSummary = messages.some((msg) => msg.event === "ASSISTANT");
  const shouldShowValidationReport =
    validationReport &&
    !isWaitingHITL &&
    hasAssistantSummary &&
    eventQueue.length === 0;

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
          {messages.length === 0 && !showShimmer ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-muted-foreground">
                메시지를 입력하여 대화를 시작하세요
              </p>
            </div>
          ) : (
            <>
              {messages.map((event) => (
                <EventCard
                  key={event.id}
                  event={event}
                  artifactId={artifactId}
                />
              ))}
              {showShimmer && <CardShimmer />}
            </>
          )}

          {shouldShowValidationReport && (
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
