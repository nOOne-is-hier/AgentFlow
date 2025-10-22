"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { FileUpload } from "@/components/file-upload";
import { FileList } from "@/components/file-list";
import { ChatPanel } from "@/components/chat-panel";
import { GraphCanvas } from "@/components/graph-canvas";
import { GraphToolbar } from "@/components/graph-toolbar";
import { Separator } from "@/components/ui/separator";
import type { Workflow } from "@/types";

export default function WorkspacePage() {
  const [fileRefreshTrigger, setFileRefreshTrigger] = useState(0);
  const [currentWorkflow, setCurrentWorkflow] = useState<Workflow | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [isPipelineComplete, setIsPipelineComplete] = useState(false);
  const [user] = useState({
    email: "user@sk.com",
    emp_id: "12345",
    name: "홍길동",
  });

  const handleUploadComplete = () => {
    setFileRefreshTrigger((prev) => prev + 1);
  };

  const handleWorkflowUpdate = (workflow: Workflow) => {
    setCurrentWorkflow(workflow);
  };

  const handleRunStart = (runId: string) => {
    setCurrentRunId(runId);
    setIsPipelineComplete(false);
  };

  const handlePipelineComplete = () => {
    setIsPipelineComplete(true);
  };

  return (
    <AppShell
      user={user}
      leftPanel={
        <div className="flex h-full flex-col">
          <div className="p-4">
            <h2 className="text-lg font-semibold mb-4">파일 관리</h2>
            <FileUpload onUploadComplete={handleUploadComplete} />
          </div>
          <Separator />
          <div className="flex-1 overflow-hidden">
            <FileList refreshTrigger={fileRefreshTrigger} />
          </div>
        </div>
      }
      centerPanel={
        <div className="flex h-full flex-col">
          <GraphToolbar
            workflow={currentWorkflow}
            onExecute={handleRunStart}
            isPipelineComplete={isPipelineComplete}
          />
          <div className="flex-1">
            <GraphCanvas workflow={currentWorkflow} />
          </div>
        </div>
      }
      rightPanel={
        <ChatPanel
          onWorkflowUpdate={handleWorkflowUpdate}
          onRunStart={handleRunStart}
          currentRunId={currentRunId}
          onPipelineComplete={handlePipelineComplete}
        />
      }
    >
      <div />
    </AppShell>
  );
}
