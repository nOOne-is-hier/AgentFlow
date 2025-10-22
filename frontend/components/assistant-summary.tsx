"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles, Download } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

interface AssistantSummaryProps {
  text: string;
  className?: string;
  maxLength?: number;
  artifactId?: string | null;
}

export function AssistantSummary({
  text,
  className,
  maxLength = 500,
  artifactId,
}: AssistantSummaryProps) {
  const safeText = text || "";
  const [isExpanded, setIsExpanded] = useState(safeText.length <= maxLength);
  const shouldTruncate = safeText.length > maxLength;

  const handleDownload = () => {
    if (artifactId) {
      const downloadUrl = `${
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      }/artifacts/${artifactId}`;
      window.open(downloadUrl, "_blank");
    }
  };

  if (!safeText) {
    return null;
  }

  return (
    <Card className={cn("overflow-hidden border-sk-orange/50", className)}>
      <div className="flex">
        <div className="w-1 shrink-0 bg-sk-orange" />
        <div className="flex-1 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-sk-orange" />
              <h3 className="text-lg font-semibold text-sk-orange">
                어시스턴트 요약
              </h3>
            </div>
            {artifactId && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="text-sk-orange border-sk-orange hover:bg-sk-orange hover:text-white bg-transparent"
              >
                <Download className="h-4 w-4 mr-2" />
                결과 다운로드
              </Button>
            )}
          </div>

          <div
            className={cn(
              "prose prose-sm max-w-none dark:prose-invert",
              "prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground",
              "prose-ul:text-foreground prose-ol:text-foreground prose-li:text-foreground",
              !isExpanded && "line-clamp-6"
            )}
          >
            <ReactMarkdown>{safeText}</ReactMarkdown>
          </div>

          {shouldTruncate && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-3 text-sk-orange hover:text-sk-orange-dark hover:bg-sk-orange/10"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="h-4 w-4 mr-1" />
                  접기
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4 mr-1" />
                  더보기
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
