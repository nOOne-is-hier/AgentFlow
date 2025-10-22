"use client";

import { Card } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import type { ValidationReport } from "@/types";
import { cn } from "@/lib/utils";

interface ValidationReportProps {
  report: ValidationReport;
  className?: string;
}

export function ValidationReportCard({
  report,
  className,
}: ValidationReportProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ok":
        return <CheckCircle2 className="h-4 w-4 text-green-600" />;
      case "warn":
        return <AlertTriangle className="h-4 w-4 text-yellow-600" />;
      case "fail":
        return <XCircle className="h-4 w-4 text-red-600" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "ok":
        return "border-green-600";
      case "warn":
        return "border-yellow-600";
      case "fail":
        return "border-red-600";
      default:
        return "border-muted";
    }
  };

  let okCount = 0;
  let warnCount = 0;
  let failCount = 0;
  let existsItems: any[] = [];
  let sumItems: any[] = [];

  if (report.summary && report.items) {
    // Backend format: {summary: {ok, warn, fail}, items: [...]}
    okCount = report.summary.ok || 0;
    warnCount = report.summary.warn || 0;
    failCount = report.summary.fail || 0;
    existsItems = report.items.filter((item) => item.policy === "exists_check");
    sumItems = report.items.filter((item) => item.policy === "sum_check");
  } else if (report.exists_check || report.sum_check) {
    // Legacy format: {exists_check: [], sum_check: []}
    const allChecks = [
      ...(report.exists_check || []),
      ...(report.sum_check || []),
    ];
    okCount = allChecks.filter((c) => c.status === "ok").length;
    warnCount = allChecks.filter((c) => c.status === "warn").length;
    failCount = allChecks.filter((c) => c.status === "fail").length;
    existsItems = report.exists_check || [];
    sumItems = report.sum_check || [];
  }

  const renderItem = (item: any, index: number) => {
    const message =
      item.message || `${item.dept || ""} - ${item.policy || ""}`.trim();
    const evidence = Array.isArray(item.evidence)
      ? item.evidence[0]
      : item.evidence;

    return (
      <div
        key={index}
        className={cn(
          "p-3 rounded-lg border-l-4",
          getStatusColor(item.status),
          "bg-card"
        )}
      >
        <div className="flex items-start gap-2">
          {getStatusIcon(item.status)}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">{message}</p>
            {item.dept && (
              <p className="text-xs text-muted-foreground mt-1">
                부서: {item.dept}
              </p>
            )}
            {evidence && (
              <div className="mt-2 text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                {evidence.page && (
                  <p className="font-semibold mb-1">페이지 {evidence.page}</p>
                )}
                {evidence.snippet && (
                  <p className="font-mono">{evidence.snippet}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <Card className={cn("p-4", className)}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">검증 리포트</h3>
          <div className="flex gap-3 text-sm">
            <span className="flex items-center gap-1 text-green-600">
              <CheckCircle2 className="h-4 w-4" />
              {okCount}
            </span>
            <span className="flex items-center gap-1 text-yellow-600">
              <AlertTriangle className="h-4 w-4" />
              {warnCount}
            </span>
            <span className="flex items-center gap-1 text-red-600">
              <XCircle className="h-4 w-4" />
              {failCount}
            </span>
          </div>
        </div>

        {existsItems.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2 text-muted-foreground">
              존재 여부 검증
            </h4>
            <div className="space-y-2">
              {existsItems.map((item, idx) => renderItem(item, idx))}
            </div>
          </div>
        )}

        {sumItems.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2 text-muted-foreground">
              합계 검증
            </h4>
            <div className="space-y-2">
              {sumItems.map((item, idx) => renderItem(item, idx))}
            </div>
          </div>
        )}

        {report.overall_status && (
          <div
            className={cn(
              "p-3 rounded-lg text-center font-semibold",
              report.overall_status === "ok" &&
                "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400",
              report.overall_status === "warn" &&
                "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400",
              report.overall_status === "fail" &&
                "bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400"
            )}
          >
            전체 상태: {report.overall_status.toUpperCase()}
          </div>
        )}
      </div>
    </Card>
  );
}
