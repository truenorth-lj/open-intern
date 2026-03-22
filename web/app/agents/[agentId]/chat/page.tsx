"use client";

import { useState, useRef, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sendMessage, listAgents } from "@/lib/api";
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

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

    try {
      const data = await sendMessage(text, undefined, agentId);
      const initialMessages: ChatMessage[] = [
        { role: "user", content: text },
        { role: "assistant", content: data.response },
      ];
      sessionStorage.setItem(
        `thread_${data.thread_id}`,
        JSON.stringify(initialMessages),
      );
      document.dispatchEvent(new CustomEvent("oi:refresh-threads"));
      router.push(`/agents/${agentId}/chat/${data.thread_id}`);
    } catch (err) {
      const msg =
        err instanceof Error && err.message.includes("NO_API_KEY")
          ? "This agent has no API key configured. Please set one in the agent's Edit page, or configure a system default in Settings."
          : "Error: Could not reach the agent.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: msg },
      ]);
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
      <h2 className="text-lg font-bold mb-3">
        {agentName || agentId}
      </h2>

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
