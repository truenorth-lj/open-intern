"use client";

import { useState, useRef, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sendMessageStream, listAgents, reloadAgent } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

export default function AgentNewChatPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const [agentName, setAgentName] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [toolStatus, setToolStatus] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  // Track accumulated response text for sessionStorage on redirect
  const streamedTextRef = useRef("");

  const [reloading, setReloading] = useState(false);
  const [reloadStatus, setReloadStatus] = useState<"" | "ok" | "error">("");

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    listAgents()
      .then((data) => {
        const agent = data.agents.find((a) => a.agent_id === agentId);
        if (agent) setAgentName(agent.name);
      })
      .catch(() => {});
  }, [agentId]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    // Add empty assistant message for streaming
    setMessages((prev) => [...prev, { role: "assistant" as const, content: "" }]);
    setStreaming(true);
    streamedTextRef.current = "";

    try {
      await sendMessageStream(
        text,
        (token) => {
          setToolStatus("");
          streamedTextRef.current += token;
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === "assistant") {
              updated[updated.length - 1] = { ...last, content: last.content + token };
            }
            return updated;
          });
        },
        (data) => {
          setStreaming(false);
          setToolStatus("");
          const initialMessages: ChatMessage[] = [
            { role: "user", content: text },
            { role: "assistant", content: streamedTextRef.current },
          ];
          sessionStorage.setItem(
            `thread_${data.thread_id}`,
            JSON.stringify(initialMessages),
          );
          document.dispatchEvent(new CustomEvent("oi:refresh-threads"));
          router.push(`/agents/${agentId}/chat/${data.thread_id}`);
        },
        (error) => {
          setStreaming(false);
          setToolStatus("");
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === "assistant") {
              const prefix = last.content ? last.content + "\n\n" : "";
              updated[updated.length - 1] = { ...last, content: prefix + `[Error: ${error}]` };
            }
            return updated;
          });
          setLoading(false);
        },
        undefined,
        agentId,
        undefined,
        (data) => {
          if (data.status === "running") {
            setToolStatus(`Calling ${data.tool}...`);
          } else {
            setToolStatus("");
          }
        },
      );
    } catch (err) {
      setStreaming(false);
      const msg =
        err instanceof Error && err.message.includes("NO_API_KEY")
          ? "This agent has no API key configured. Please set one in the agent's Edit page, or configure a system default in Settings."
          : "Error: Could not reach the agent.";
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, content: msg };
        } else {
          updated.push({ role: "assistant", content: msg });
        }
        return updated;
      });
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleReload() {
    setReloading(true);
    setReloadStatus("");
    try {
      await reloadAgent(agentId);
      setReloadStatus("ok");
    } catch {
      setReloadStatus("error");
    } finally {
      setReloading(false);
      setTimeout(() => setReloadStatus(""), 3000);
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-lg font-bold">
          {agentName || agentId}
        </h2>
        <Button
          variant="outline"
          size="sm"
          onClick={handleReload}
          disabled={reloading}
          title="Reload agent runtime"
        >
          {reloading ? "Reloading..." : reloadStatus === "ok" ? "Reloaded!" : reloadStatus === "error" ? "Failed" : "Reload"}
        </Button>
      </div>

      <ScrollArea className="flex-1 mb-4">
        <div className="space-y-4 pr-4">
          {messages.length === 0 && (
            <p className="text-center text-muted-foreground py-20">
              Send a message to start a conversation with{" "}
              {agentName || agentId}.
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={`${msg.role}-${i}`}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <Card
                className={`max-w-[75%] px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">
                  {msg.content || (streaming && i === messages.length - 1 ? (toolStatus || "Thinking...") : "")}
                </p>
              </Card>
            </div>
          ))}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      <div className="flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
          className="resize-none"
          rows={2}
          disabled={loading}
        />
        <Button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="self-end"
        >
          Send
        </Button>
      </div>
    </>
  );
}
