"use client"

import React from "react"
import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

interface ErrorBoundaryProps {
  children: React.ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[v0] Error caught by boundary:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center p-4 bg-background">
          <Card className="max-w-md p-6">
            <div className="flex flex-col items-center text-center">
              <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
              <h2 className="text-xl font-bold mb-2">오류가 발생했습니다</h2>
              <p className="text-sm text-muted-foreground mb-4">
                {this.state.error?.message || "알 수 없는 오류가 발생했습니다."}
              </p>
              <Button onClick={() => window.location.reload()} className="bg-sk-red hover:bg-sk-red-dark">
                페이지 새로고침
              </Button>
            </div>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}
