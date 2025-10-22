"use client"

import { useEffect, useState } from "react"
import { FileText, FileSpreadsheet, Download, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"
import { formatFileSize, formatTimestamp } from "@/lib/utils"
import type { FileInfo } from "@/types"
import { useToast } from "@/hooks/use-toast"

interface FileListProps {
  refreshTrigger?: number
}

export function FileList({ refreshTrigger }: FileListProps) {
  const { toast } = useToast()
  const [files, setFiles] = useState<FileInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchFiles = async () => {
      try {
        setIsLoading(true)
        const data = await api.getFiles()
        setFiles(data)
      } catch (error) {
        toast({
          title: "파일 목록 로드 실패",
          description: error instanceof Error ? error.message : "다시 시도해주세요.",
          variant: "destructive",
        })
      } finally {
        setIsLoading(false)
      }
    }

    fetchFiles()
  }, [refreshTrigger, toast])

  const getFileIcon = (fileType: string) => {
    return fileType === "pdf" ? (
      <FileText className="h-4 w-4 text-sk-red" />
    ) : (
      <FileSpreadsheet className="h-4 w-4 text-sk-orange" />
    )
  }

  const handleDownload = (fileId: string, filename: string) => {
    const url = api.downloadFile(fileId)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)

    toast({
      title: "다운로드 시작",
      description: `${filename} 다운로드를 시작합니다.`,
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <FileText className="h-12 w-12 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">업로드된 파일이 없습니다</p>
      </div>
    )
  }

  const uploadedFiles = files.filter((f) => !f.is_artifact)
  const artifactFiles = files.filter((f) => f.is_artifact)

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        {uploadedFiles.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-2">업로드된 파일</h3>
            <div className="space-y-2">
              {uploadedFiles.map((file) => (
                <div key={file.file_id} className="rounded-lg border bg-card p-3 hover:bg-accent/50 transition-colors">
                  <div className="flex items-start gap-2">
                    {getFileIcon(file.file_type)}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{file.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(file.size)} • {formatTimestamp(file.uploaded_at)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {artifactFiles.length > 0 && (
          <>
            <Separator />
            <div>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full bg-sk-orange animate-pulse" />
                생성된 파일
              </h3>
              <div className="space-y-2">
                {artifactFiles.map((file) => (
                  <div
                    key={file.file_id}
                    className="rounded-lg border border-sk-orange/30 bg-sk-orange/5 p-3 hover:bg-sk-orange/10 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      {getFileIcon(file.file_type)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{file.filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatFileSize(file.size)} • {formatTimestamp(file.uploaded_at)}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDownload(file.file_id, file.filename)}
                        className="shrink-0 hover:bg-sk-orange/20 hover:text-sk-orange"
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </ScrollArea>
  )
}
