"use client";

import { useEffect, useState, useCallback, use } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { getThreads, deleteThread, updateThreadTitle } from "@/lib/api";

interface Thread {
  thread_id: string;
  title: string;
  created_at: string;
}

export function AgentChatSidebar({
  paramsPromise,
}: {
  paramsPromise: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(paramsPromise);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const router = useRouter();
  const pathname = usePathname();

  const chatBase = `/agents/${agentId}/chat`;

  // Extract current threadId from URL
  const activeThreadId = pathname.startsWith(`${chatBase}/`)
    ? pathname.replace(`${chatBase}/`, "")
    : null;

  const loadThreads = useCallback(() => {
    getThreads(agentId)
      .then((data) => setThreads(data.threads))
      .catch((err) => console.error("Failed to load threads:", err));
  }, [agentId]);

  useEffect(() => {
    loadThreads();
    const interval = setInterval(loadThreads, 5000);
    return () => clearInterval(interval);
  }, [loadThreads]);

  useEffect(() => {
    const handler = () => loadThreads();
    document.addEventListener("oi:refresh-threads", handler);
    return () => document.removeEventListener("oi:refresh-threads", handler);
  }, [loadThreads]);

  async function handleDelete(threadId: string) {
    try {
      await deleteThread(threadId);
    } catch (err) {
      console.error("Failed to delete thread:", err);
    }
    setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
    if (activeThreadId === threadId) {
      router.push(chatBase);
    }
  }

  function startEdit(thread: Thread) {
    setEditingId(thread.thread_id);
    setEditTitle(thread.title);
  }

  async function saveEdit(threadId: string) {
    if (editTitle.trim()) {
      try {
        await updateThreadTitle(threadId, editTitle.trim());
      } catch (err) {
        console.error("Failed to update thread title:", err);
      }
      setThreads((prev) =>
        prev.map((t) =>
          t.thread_id === threadId ? { ...t, title: editTitle.trim() } : t,
        ),
      );
    }
    setEditingId(null);
  }

  return (
    <div className="w-56 border-r flex flex-col">
      <div className="p-3 space-y-2">
        <Link
          href="/agents"
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          &larr; All Agents
        </Link>
        <Button
          onClick={() => router.push(chatBase)}
          variant="outline"
          className="w-full"
        >
          + New Chat
        </Button>
      </div>
      <Separator />
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {threads.map((thread) => (
            <div
              key={thread.thread_id}
              className={`group flex items-center rounded-md px-2 py-1.5 text-sm cursor-pointer ${
                activeThreadId === thread.thread_id
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              }`}
              onClick={() => router.push(`${chatBase}/${thread.thread_id}`)}
            >
              {editingId === thread.thread_id ? (
                <Input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => saveEdit(thread.thread_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveEdit(thread.thread_id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="h-6 text-xs"
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <span className="truncate flex-1">
                    {thread.title ||
                      `Thread ${thread.thread_id.slice(0, 8)}`}
                  </span>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-xs text-muted-foreground ml-1"
                    onClick={(e) => {
                      e.stopPropagation();
                      startEdit(thread);
                    }}
                    title="Rename"
                  >
                    ✎
                  </button>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-xs text-destructive ml-1"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(thread.thread_id);
                    }}
                    title="Delete"
                  >
                    ×
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
