"use client";
import { useState } from "react";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { ValidationReport } from "@/types";

interface HITLApprovalBarProps {
  runId: string;
  validationReport?: ValidationReport;
  onApprovalComplete?: () => void;
}

export function HITLApprovalBar({
  runId,
  validationReport,
  onApprovalComplete,
}: HITLApprovalBarProps) {
  const { toast } = useToast();
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleApproval = async (approve: boolean) => {
    setIsSubmitting(true);

    try {
      await api.continueRun(runId, {
        approve,
        comment: comment.trim() || undefined,
      });

      toast({
        title: approve ? "승인 완료" : "거절 완료",
        description: approve
          ? "파이프라인이 계속 실행됩니다."
          : "파이프라인이 중단되었습니다.",
      });

      onApprovalComplete?.();
      setComment("");
    } catch (error) {
      toast({
        title: "요청 실패",
        description:
          error instanceof Error ? error.message : "다시 시도해주세요.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusSummary = () => {
    if (!validationReport) return null;

    const summary = validationReport.summary || { ok: 0, warn: 0, fail: 0 };
    return {
      okCount: summary.ok,
      warnCount: summary.warn,
      failCount: summary.fail,
      total: summary.ok + summary.warn + summary.fail,
    };
  };

  const summary = getStatusSummary();

  return (
    <Card className="sticky bottom-0 border-t-2 border-sk-orange bg-card/95 backdrop-blur">
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-sk-orange animate-pulse" />
          <h3 className="text-sm font-semibold text-sk-orange">승인 대기 중</h3>
        </div>

        {summary && (
          <div className="flex gap-4 text-sm">
            <span className="text-green-600">✓ {summary.okCount}</span>
            <span className="text-yellow-600">⚠ {summary.warnCount}</span>
            <span className="text-red-600">✗ {summary.failCount}</span>
            <span className="text-muted-foreground">
              총 {summary.total}개 검증
            </span>
          </div>
        )}

        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="코멘트 입력 (선택사항)"
          className="min-h-[60px] resize-none"
          disabled={isSubmitting}
        />

        <div className="flex gap-2">
          <Button
            onClick={() => handleApproval(true)}
            disabled={isSubmitting}
            className="flex-1 bg-green-600 hover:bg-green-700"
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <CheckCircle2 className="h-4 w-4 mr-2" />
            )}
            승인
          </Button>
          <Button
            onClick={() => handleApproval(false)}
            disabled={isSubmitting}
            variant="destructive"
            className="flex-1"
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <XCircle className="h-4 w-4 mr-2" />
            )}
            거절
          </Button>
        </div>
      </div>
    </Card>
  );
}
