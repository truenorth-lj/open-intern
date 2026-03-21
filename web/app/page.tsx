"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getStatus, getTokenUsageSummary } from "@/lib/api";
import type { AgentStatus } from "@/lib/types";

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

interface TokenSummary {
  agents: {
    agent_id: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    request_count: number;
  }[];
  total: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    request_count: number;
  };
}

export default function StatusPage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [tokenSummary, setTokenSummary] = useState<TokenSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch(() => setError("Cannot connect to agent. Is the backend running on port 8000?"));
    getTokenUsageSummary()
      .then(setTokenSummary)
      .catch(() => {});
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Connection Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{error}</p>
            <p className="text-sm mt-2">
              Start the backend: <code className="bg-muted px-1 rounded">open_intern start</code>
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!status) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Agent</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{status.name}</p>
            <p className="text-sm text-muted-foreground">{status.role}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">LLM</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{status.llm_model}</p>
            <Badge variant="secondary">{status.llm_provider}</Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Platform</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold capitalize">{status.platform}</p>
            <Badge variant="outline" className="text-green-600 border-green-600">Online</Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Memories</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{status.memory_stats.total}</p>
            <p className="text-xs text-muted-foreground">
              {status.memory_stats.shared} shared / {status.memory_stats.channel} channel / {status.memory_stats.personal} personal
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Token Usage Summary */}
      {tokenSummary && tokenSummary.total.total_tokens > 0 && (
        <>
          <h3 className="text-lg font-semibold mt-6">Token Usage</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Total Tokens</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{formatTokenCount(tokenSummary.total.total_tokens)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatTokenCount(tokenSummary.total.input_tokens)} in / {formatTokenCount(tokenSummary.total.output_tokens)} out
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Requests</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{tokenSummary.total.request_count}</p>
                <p className="text-xs text-muted-foreground">total API calls</p>
              </CardContent>
            </Card>
          </div>

          {tokenSummary.agents.length > 1 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">Per Agent</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {tokenSummary.agents.map((agent) => (
                  <Card key={agent.agent_id} className="p-4">
                    <div className="flex justify-between items-center">
                      <div>
                        <p className="font-medium text-sm">{agent.agent_id}</p>
                        <p className="text-xs text-muted-foreground">
                          {agent.request_count} requests
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-sm">{formatTokenCount(agent.total_tokens)}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatTokenCount(agent.input_tokens)} / {formatTokenCount(agent.output_tokens)}
                        </p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
