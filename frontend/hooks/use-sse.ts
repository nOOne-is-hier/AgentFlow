"use client"

import { useEffect, useRef, useState } from "react"
import type { SSEEvent, EventType } from "@/types"

interface UseSSEOptions {
  onEvent?: (event: SSEEvent) => void
  onError?: (error: Error) => void
  onConnect?: () => void
  onDisconnect?: () => void
}

export function useSSE(url: string | null, options: UseSSEOptions = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [events, setEvents] = useState<SSEEvent[]>([])
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttempts = 5
  const optionsRef = useRef(options)
  const pipelineCompletedRef = useRef(false)

  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    if (!url) {
      return
    }

    pipelineCompletedRef.current = false

    if (eventSourceRef.current) {
      console.log("[v0] Cleaning up existing SSE connection before reconnecting")
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }

    if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
      console.error("[v0] Max reconnection attempts reached")
      optionsRef.current.onError?.(new Error("최대 재연결 시도 횟수를 초과했습니다"))
      return
    }

    console.log("[v0] Creating new SSE connection to:", url)

    try {
      const eventSource = new EventSource(url, { withCredentials: true })
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        console.log("[v0] SSE connected")
        setIsConnected(true)
        reconnectAttemptsRef.current = 0
        optionsRef.current.onConnect?.()
      }

      eventSource.onmessage = (e) => {
        try {
          const rawData = JSON.parse(e.data)
          console.log("[v0] Raw SSE data:", rawData)

          const event: SSEEvent = {
            id: e.lastEventId || rawData.seq?.toString() || Date.now().toString(),
            event: rawData.type as EventType,
            data: {
              node_id: rawData.nodeId,
              node_type: rawData.detail?.node_type,
              message: rawData.message,
              detail: rawData.detail,
              __compact__: rawData.__compact__,
              validation_report: rawData.detail?.validation_report,
              text: rawData.detail?.text,
            },
            timestamp: rawData.ts || new Date().toISOString(),
          }

          if (event.event === "SUMMARY") {
            console.log("[v0] Pipeline completed, marking as finished")
            pipelineCompletedRef.current = true
          }

          console.log("[v0] Parsed SSE event:", event)
          setEvents((prev) => [...prev, event])
          optionsRef.current.onEvent?.(event)
        } catch (error) {
          console.error("[v0] Failed to parse SSE event:", error, "Raw data:", e.data)
        }
      }

      eventSource.onerror = (error) => {
        console.log("[v0] SSE connection closed")
        setIsConnected(false)
        eventSource.close()
        eventSourceRef.current = null

        if (pipelineCompletedRef.current) {
          console.log("[v0] Pipeline completed, not reconnecting")
          optionsRef.current.onDisconnect?.()
          return
        }

        console.error("[v0] SSE error:", error)
        optionsRef.current.onDisconnect?.()

        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
          reconnectAttemptsRef.current++

          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(`[v0] Reconnecting SSE (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`)
          }, delay)
        }
      }
    } catch (error) {
      console.error("[v0] Failed to create EventSource:", error)
      optionsRef.current.onError?.(error as Error)
    }

    return () => {
      console.log("[v0] Cleaning up SSE connection")
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setIsConnected(false)
    }
  }, [url])

  return {
    isConnected,
    events,
    clearEvents: () => setEvents([]),
    disconnect: () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setIsConnected(false)
      reconnectAttemptsRef.current = 0
      pipelineCompletedRef.current = false
    },
  }
}
