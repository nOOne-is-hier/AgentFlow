"use client";

import type React from "react";
import { useState } from "react";
import { LogOut, Menu, X, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useToast } from "@/hooks/use-toast";

interface AppShellProps {
  children: React.ReactNode;
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  centerPanel: React.ReactNode;
  user?: {
    email: string;
    emp_id: string;
    name?: string;
  };
}

export function AppShell({
  children,
  leftPanel,
  rightPanel,
  centerPanel,
  user,
}: AppShellProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);

  const handleLogout = async () => {
    try {
      await api.logout();
      router.push("/login");
    } catch (error) {
      toast({
        title: "로그아웃 실패",
        description:
          error instanceof Error ? error.message : "다시 시도해주세요.",
        variant: "destructive",
      });
    }
  };

  const userInitials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
    : user?.email[0].toUpperCase() || "U";

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Top App Bar */}
      <header className="flex h-14 items-center gap-4 border-b bg-card px-4 shrink-0 shadow-sm">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setLeftPanelOpen(!leftPanelOpen)}
            className="hidden lg:flex"
            aria-label={leftPanelOpen ? "좌측 패널 닫기" : "좌측 패널 열기"}
          >
            {leftPanelOpen ? (
              <ChevronLeft className="h-5 w-5" />
            ) : (
              <ChevronRight className="h-5 w-5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setLeftPanelOpen(!leftPanelOpen)}
            className="lg:hidden"
            aria-label="메뉴"
          >
            {leftPanelOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </Button>
          <h1 className="text-lg font-bold sk-gradient-text">
            Budget Validation System
          </h1>
        </div>

        <div className="flex-1" />

        {user && (
          <div className="flex items-center gap-3">
            <div className="hidden sm:block text-right">
              <p className="text-sm font-medium">{user.name || user.email}</p>
              <p className="text-xs text-muted-foreground">{user.emp_id}</p>
            </div>
            <Avatar>
              <AvatarFallback className="bg-sk-red text-white font-semibold">
                {userInitials}
              </AvatarFallback>
            </Avatar>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleLogout}
              aria-label="로그아웃"
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        )}

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setRightPanelOpen(!rightPanelOpen)}
          className="hidden xl:flex"
          aria-label={rightPanelOpen ? "우측 패널 닫기" : "우측 패널 열기"}
        >
          {rightPanelOpen ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <ChevronLeft className="h-5 w-5" />
          )}
        </Button>
      </header>

      {/* 3-Pane Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel */}
        <aside
          className={cn(
            "border-r bg-card transition-all duration-300 overflow-hidden",
            leftPanelOpen ? "w-80" : "w-0 border-0",
            "max-lg:absolute max-lg:inset-y-14 max-lg:left-0 max-lg:z-50 max-lg:shadow-lg",
            !leftPanelOpen && "max-lg:-translate-x-full"
          )}
        >
          <div className="h-full">{leftPanel}</div>
        </aside>

        {/* Center Panel (Graph Canvas) */}
        <main className="flex-1 overflow-hidden" role="main">
          {centerPanel}
        </main>

        {/* Right Panel */}
        <aside
          className={cn(
            "border-l bg-card transition-all duration-300 overflow-hidden",
            rightPanelOpen ? "w-[420px]" : "w-0 border-0",
            "max-xl:absolute max-xl:inset-y-14 max-xl:right-0 max-xl:z-50 max-xl:shadow-lg",
            !rightPanelOpen && "max-xl:translate-x-full"
          )}
        >
          <div className="h-full">{rightPanel}</div>
        </aside>
      </div>

      {/* Overlay for mobile */}
      {(leftPanelOpen || rightPanelOpen) && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => {
            setLeftPanelOpen(false);
            setRightPanelOpen(false);
          }}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
