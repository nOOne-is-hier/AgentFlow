"use client";

import { useState } from "react";
import {
  Calendar,
  Play,
  Eye,
  CheckCircle2,
  AlertCircle,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { SSEEvent, ValidationReport } from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AssistantSummary } from "@/components/assistant-summary";
import ReactMarkdown from "react-markdown";

interface EventCardProps {
  event: SSEEvent;
  className?: string;
  artifactId?: string | null;
}

const EVENT_CONFIG = {
  PLAN: {
    icon: Calendar,
    color: "ev-plan",
    label: "실행 계획",
  },
  ACTION: {
    icon: Play,
    color: "ev-action",
    label: "작업 시작",
  },
  OBS: {
    icon: Eye,
    color: "ev-obs",
    label: "관찰",
  },
  SUMMARY: {
    icon: CheckCircle2,
    color: "ev-summary",
    label: "요약",
  },
  WAITING_HITL: {
    icon: AlertCircle,
    color: "ev-hitl",
    label: "승인 대기",
  },
  ASSISTANT_REPLY: {
    icon: MessageSquare,
    color: "ev-assistant",
    label: "어시스턴트",
  },
  USER: {
    icon: MessageSquare,
    color: "ev-user",
    label: "사용자",
  },
  ASSISTANT: {
    icon: MessageSquare,
    color: "ev-assistant",
    label: "어시스턴트",
  },
  ERROR: {
    icon: AlertCircle,
    color: "destructive",
    label: "오류",
  },
};

export function EventCard({ event, className, artifactId }: EventCardProps) {
  const [isExpanded, setIsExpanded] = useState(
    !(event.data?.__compact__ ?? false)
  );
  const config = EVENT_CONFIG[event.event] || EVENT_CONFIG.OBS;
  const Icon = config.icon;

  const renderValidationReport = (report: ValidationReport) => {
    const getStatusColor = (status: string) => {
      switch (status) {
        case "ok":
          return "text-green-600";
        case "warn":
          return "text-yellow-600";
        case "fail":
          return "text-red-600";
        default:
          return "text-muted-foreground";
      }
    };

    if (report.summary) {
      // Backend format: {summary: {ok, warn, fail}, items: [...]}
      const { ok = 0, warn = 0, fail = 0 } = report.summary;

      return (
        <div className="space-y-2 mt-2">
          <div className="flex gap-4 text-sm">
            <span className="text-green-600">✓ {ok}</span>
            <span className="text-yellow-600">⚠ {warn}</span>
            <span className="text-red-600">✗ {fail}</span>
          </div>

          {isExpanded && report.items && report.items.length > 0 && (
            <div className="space-y-2 mt-3">
              {report.items.map((item, idx) => (
                <div
                  key={idx}
                  className="text-xs pl-2 border-l-2 border-muted mb-1"
                >
                  <div className="flex items-center gap-2">
                    <span className={getStatusColor(item.status)}>
                      {item.policy || item.message}
                    </span>
                    {item.dept && (
                      <span className="text-muted-foreground">
                        ({item.dept})
                      </span>
                    )}
                  </div>
                  {item.evidence && item.evidence.length > 0 && (
                    <div className="mt-1 space-y-1">
                      {item.evidence.map((ev, eidx) => (
                        <p key={eidx} className="text-muted-foreground">
                          {ev.page && `페이지 ${ev.page}: `}
                          {ev.snippet}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    // Legacy format: {exists_check, sum_check}
    const allChecks = [
      ...(report.exists_check || []),
      ...(report.sum_check || []),
    ];
    const okCount = allChecks.filter((c) => c.status === "ok").length;
    const warnCount = allChecks.filter((c) => c.status === "warn").length;
    const failCount = allChecks.filter((c) => c.status === "fail").length;

    return (
      <div className="space-y-2 mt-2">
        <div className="flex gap-4 text-sm">
          <span className="text-green-600">✓ {okCount}</span>
          <span className="text-yellow-600">⚠ {warnCount}</span>
          <span className="text-red-600">✗ {failCount}</span>
        </div>

        {isExpanded && (
          <div className="space-y-2 mt-3">
            {report.exists_check.length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-1">존재 여부 검증</p>
                {report.exists_check.map((item, idx) => (
                  <div
                    key={idx}
                    className="text-xs pl-2 border-l-2 border-muted mb-1"
                  >
                    <span className={getStatusColor(item.status)}>
                      {item.message}
                    </span>
                    {item.evidence && (
                      <p className="text-muted-foreground mt-0.5">
                        {item.evidence.page && `페이지 ${item.evidence.page}: `}
                        {item.evidence.snippet}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {report.sum_check.length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-1">합계 검증</p>
                {report.sum_check.map((item, idx) => (
                  <div
                    key={idx}
                    className="text-xs pl-2 border-l-2 border-muted mb-1"
                  >
                    <span className={getStatusColor(item.status)}>
                      {item.message}
                    </span>
                    {item.evidence && (
                      <p className="text-muted-foreground mt-0.5">
                        {item.evidence.page && `페이지 ${item.evidence.page}: `}
                        {item.evidence.snippet}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderContent = () => {
    if (!event.data) {
      return null;
    }

    if (
      (event.event === "USER" || event.event === "ASSISTANT") &&
      event.data.text
    ) {
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown>{event.data.text}</ReactMarkdown>
        </div>
      );
    }

    if (event.event === "PLAN" && event.data.detail?.text) {
      return (
        <div className="space-y-2">
          <p className="text-sm font-medium">{event.data.message}</p>
          <div className="text-sm text-muted-foreground whitespace-pre-wrap">
            {event.data.detail.text}
          </div>
        </div>
      );
    }

    if (event.event === "ASSISTANT_REPLY" && event.data.text) {
      // Check if this is a summary event (contains markdown formatting)
      if (event.data.text.includes("##") || event.data.text.length > 200) {
        return (
          <AssistantSummary text={event.data.text} artifactId={artifactId} />
        );
      }
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown>{event.data.text}</ReactMarkdown>
        </div>
      );
    }

    if (event.event === "SUMMARY" && event.data.text) {
      return (
        <AssistantSummary text={event.data.text} artifactId={artifactId} />
      );
    }

    if (event.data.validation_report) {
      return renderValidationReport(event.data.validation_report);
    }

    if (event.data.message) {
      return <p className="text-sm">{event.data.message}</p>;
    }

    if (event.event === "OBS" && event.data.detail?.text) {
      return (
        <div className="space-y-2">
          <p className="text-sm font-medium">{event.data.message}</p>
          <div className="text-sm text-muted-foreground whitespace-pre-wrap">
            {event.data.detail.text}
          </div>
        </div>
      );
    }

    if (event.data.detail && typeof event.data.detail === "object") {
      return (
        <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
          {JSON.stringify(event.data.detail, null, 2)}
        </pre>
      );
    }

    return null;
  };

  if (
    event.data &&
    (event.event === "ASSISTANT_REPLY" || event.event === "SUMMARY") &&
    event.data.text &&
    (event.data.text.includes("##") || event.data.text.length > 200)
  ) {
    return renderContent();
  }

  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="flex">
        <div className={cn("w-1 shrink-0", `bg-${config.color}`)} />
        <div className="flex-1 p-3">
          <div className="flex items-start gap-2">
            <Icon
              className={cn("h-4 w-4 mt-0.5 shrink-0", `text-${config.color}`)}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold">{config.label}</span>
                {event.data?.node_type && (
                  <span className="text-xs text-muted-foreground">
                    ({event.data.node_type})
                  </span>
                )}
              </div>

              {renderContent()}

              {event.data?.__compact__ && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="mt-2 h-6 text-xs"
                >
                  {isExpanded ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      접기
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      더보기
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
