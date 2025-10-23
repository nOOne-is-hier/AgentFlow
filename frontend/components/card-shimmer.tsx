"use client";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface CardShimmerProps {
  className?: string;
}

export function CardShimmer({ className }: CardShimmerProps) {
  return (
    <Card className={cn("overflow-hidden animate-pulse", className)}>
      <div className="flex">
        <div className="w-1 shrink-0 bg-muted" />
        <div className="flex-1 p-3">
          <div className="flex items-start gap-2">
            <div className="h-4 w-4 mt-0.5 shrink-0 bg-muted rounded" />
            <div className="flex-1 min-w-0 space-y-2">
              <div className="h-4 bg-muted rounded w-24" />
              <div className="h-3 bg-muted rounded w-full" />
              <div className="h-3 bg-muted rounded w-3/4" />
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
