"use client"

import type React from "react"
import { useCallback, useState } from "react"
import { Upload, X, FileText, FileSpreadsheet } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { useToast } from "@/hooks/use-toast"

interface FileUploadProps {
  onUploadComplete?: (fileId: string) => void
  className?: string
}

export function FileUpload({ onUploadComplete, className }: FileUploadProps) {
  const { toast } = useToast()
  const [isDragging, setIsDragging] = useState(false)
  const [uploadingFiles, setUploadingFiles] = useState<Array<{ file: File; progress: number; error?: string }>>([])

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return

      const validFiles = Array.from(files).filter((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase()
        return ext === "pdf" || ext === "xlsx"
      })

      if (validFiles.length === 0) {
        toast({
          title: "잘못된 파일 형식",
          description: "PDF 또는 XLSX 파일만 업로드 가능합니다.",
          variant: "destructive",
        })
        return
      }

      setUploadingFiles(validFiles.map((file) => ({ file, progress: 0 })))

      for (let i = 0; i < validFiles.length; i++) {
        const file = validFiles[i]
        try {
          setUploadingFiles((prev) => prev.map((item, idx) => (idx === i ? { ...item, progress: 50 } : item)))

          const result = await api.uploadFile(file)

          setUploadingFiles((prev) => prev.map((item, idx) => (idx === i ? { ...item, progress: 100 } : item)))

          onUploadComplete?.(result.file_id)

          toast({
            title: "업로드 완료",
            description: `${file.name}이(가) 업로드되었습니다.`,
          })
        } catch (error) {
          setUploadingFiles((prev) =>
            prev.map((item, idx) =>
              idx === i
                ? {
                    ...item,
                    error: error instanceof Error ? error.message : "업로드 실패",
                  }
                : item,
            ),
          )

          toast({
            title: "업로드 실패",
            description: `${file.name}: ${error instanceof Error ? error.message : "알 수 없는 오류"}`,
            variant: "destructive",
          })
        }
      }

      setTimeout(() => setUploadingFiles([]), 3000)
    },
    [onUploadComplete, toast],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles],
  )

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFiles(e.target.files)
    },
    [handleFiles],
  )

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase()
    return ext === "pdf" ? <FileText className="h-4 w-4" /> : <FileSpreadsheet className="h-4 w-4" />
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors",
          isDragging ? "border-sk-red bg-sk-red/5" : "border-border hover:border-sk-red/50",
        )}
      >
        <Upload className={cn("mb-4 h-10 w-10", isDragging ? "text-sk-red" : "text-muted-foreground")} />
        <p className="mb-2 text-sm font-medium">파일을 드래그하거나 클릭하여 업로드</p>
        <p className="text-xs text-muted-foreground">PDF, XLSX 파일 지원</p>
        <input
          type="file"
          multiple
          accept=".pdf,.xlsx"
          onChange={handleFileInput}
          className="absolute inset-0 cursor-pointer opacity-0"
        />
      </div>

      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          {uploadingFiles.map((item, idx) => (
            <div key={idx} className="rounded-lg border bg-card p-3">
              <div className="flex items-center gap-2 mb-2">
                {getFileIcon(item.file.name)}
                <span className="flex-1 text-sm truncate">{item.file.name}</span>
                {item.error && <X className="h-4 w-4 text-destructive" />}
              </div>
              <Progress value={item.progress} className="h-1" />
              {item.error && <p className="mt-1 text-xs text-destructive">{item.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
