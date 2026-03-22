"use client";

import { useState, useRef, useEffect, use } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sendMessage, getThreadTokenUsage, listAgents } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function AgentThreadPage({
  params,
}: {
  params: Promise<{ agentId: string; threadId: string }>;
}) {
  const { agentId, threadId } = use(params);
  const [agentName, setAgentName] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<{
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    request_count: number;
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const key = `thread_${threadId}`;
    const stored = sessionStorage.getItem(key);
    if (stored) {
      try {
        setMessages(JSON.parse(stored));
      } catch {
        setMessages([]);
      }
    } else {
      setMessages([]);
    }
    getThreadTokenUsage(threadId)
      .then(setTokenUsage)
      .catch(() => {});
  }, [threadId]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => {
      const updated = [...prev, { role: "user" as const, content: text }];
      sessionStorage.setItem(`thread_${threadId}`, JSON.stringify(updated));
      return updated;
    });
    setLoading(true);

    try {
      const data = await sendMessage(text, threadId, agentId);
      setMessages((prev) => {
        const updated = [
          ...prev,
          { role: "assistant" as const, content: data.response },
        ];
        sessionStorage.setItem(`thread_${threadId}`, JSON.stringify(updated));
        return updated;
      });
      getThreadTokenUsage(threadId)
        .then(setTokenUsage)
        .catch(() => {});
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error: Could not reach the agent." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold">{agentName || agentId}</h2>
        {tokenUsage && tokenUsage.total_tokens > 0 && (
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span>Tokens: {formatTokenCount(tokenUsage.total_tokens)}</span>
            <span>In: {formatTokenCount(tokenUsage.input_tokens)}</span>
            <span>Out: {formatTokenCount(tokenUsage.output_tokens)}</span>
            <span>Requests: {tokenUsage.request_count}</span>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1 mb-4">
        <div className="space-y-4 pr-4">
          {messages.length === 0 && (
            <p className="text-center text-muted-foreground py-20">
              Continue this conversation.
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
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </Card>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <Card className="bg-muted px-4 py-3">
                <p className="text-sm text-muted-foreground">Thinking...</p>
              </Card>
            </div>
          )}
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
