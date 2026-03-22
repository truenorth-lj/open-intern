"use client";

import { useEffect, useState, useMemo } from "react";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getTokenUsageSummary,
  getTokenUsageTimeseries,
  listAgents,
  type AgentInfo,
} from "@/lib/api";
import { formatTokenCount } from "@/lib/utils";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const AGENT_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#db2777",
  "#ea580c",
  "#16a34a",
  "#0891b2",
  "#ca8a04",
  "#6366f1",
];

interface SummaryAgent {
  agent_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  request_count: number;
}

interface TimeseriesPoint {
  date: string;
  agent_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  request_count: number;
}

type RangePreset = "7d" | "14d" | "30d" | "90d" | "custom";

function getPresetRange(preset: RangePreset): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  switch (preset) {
    case "7d":
      start.setDate(end.getDate() - 7);
      break;
    case "14d":
      start.setDate(end.getDate() - 14);
      break;
    case "30d":
      start.setDate(end.getDate() - 30);
      break;
    case "90d":
      start.setDate(end.getDate() - 90);
      break;
    default:
      start.setDate(end.getDate() - 30);
  }
  // Add 1 day to end so the current day's data is included
  // (backend filters by created_at <= end, and date-only parses as midnight)
  const endInclusive = new Date(end);
  endInclusive.setDate(endInclusive.getDate() + 1);
  return {
    start: start.toISOString().split("T")[0],
    end: endInclusive.toISOString().split("T")[0],
  };
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function UsagePage() {
  const { loading: authLoading } = useAuth();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [summary, setSummary] = useState<{
    agents: SummaryAgent[];
    total: SummaryAgent;
  } | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [rangePreset, setRangePreset] = useState<RangePreset>("30d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<string>("");

  // Load summary + agents on mount
  useEffect(() => {
    if (authLoading) return;
    Promise.all([getTokenUsageSummary(), listAgents()])
      .then(([sum, agentData]) => {
        setSummary(sum);
        setAgents(agentData.agents?.filter((a: AgentInfo) => a.is_active) ?? []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [authLoading]);

  // Load timeseries when range/agent changes
  useEffect(() => {
    if (authLoading) return;
    const range =
      rangePreset === "custom"
        ? { start: customStart, end: customEnd }
        : getPresetRange(rangePreset);
    if (!range.start || !range.end) return;

    setError("");
    getTokenUsageTimeseries({
      start: range.start,
      end: range.end,
      agent_id: selectedAgent || undefined,
    })
      .then((data) => setTimeseries(data.points ?? []))
      .catch((err) => setError(err.message));
  }, [authLoading, rangePreset, customStart, customEnd, selectedAgent]);

  // Build agent name map
  const agentNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const a of agents) map[a.agent_id] = a.name;
    return map;
  }, [agents]);

  // Build agent color map from summary
  const agentColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    const ids = summary?.agents?.map((a) => a.agent_id) ?? [];
    ids.forEach((id, i) => {
      map[id] = AGENT_COLORS[i % AGENT_COLORS.length];
    });
    return map;
  }, [summary]);

  // Transform timeseries into recharts format: [{date, agent1: N, agent2: N, ...}]
  const chartData = useMemo(() => {
    const byDate: Record<string, Record<string, number>> = {};
    for (const pt of timeseries) {
      if (!byDate[pt.date]) byDate[pt.date] = {};
      byDate[pt.date][pt.agent_id] = pt.total_tokens;
    }
    const dates = Object.keys(byDate).sort();
    return dates.map((date) => ({
      date,
      ...byDate[date],
    }));
  }, [timeseries]);

  // All agent IDs appearing in the timeseries data
  const chartAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const pt of timeseries) ids.add(pt.agent_id);
    return Array.from(ids);
  }, [timeseries]);

  if (authLoading || loading) {
    return <p className="text-muted-foreground p-4">Loading...</p>;
  }

  if (error) {
    return <p className="text-destructive text-sm p-4">Error: {error}</p>;
  }

  const presets: { label: string; value: RangePreset }[] = [
    { label: "7D", value: "7d" },
    { label: "14D", value: "14d" },
    { label: "30D", value: "30d" },
    { label: "90D", value: "90d" },
    { label: "Custom", value: "custom" },
  ];

  return (
    <div className="space-y-6 max-w-5xl">
      <h2 className="text-2xl font-bold">Token Usage</h2>

      {/* Summary cards */}
      {summary && summary.agents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {summary.agents.map((agent) => (
            <Card key={agent.agent_id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span>{agentNameMap[agent.agent_id] || agent.agent_id}</span>
                  <div
                    className="size-3 rounded-full"
                    style={{
                      backgroundColor: agentColorMap[agent.agent_id] ?? "#888",
                    }}
                  />
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  {agent.agent_id}
                </p>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-muted-foreground text-xs">Total</p>
                    <p className="font-semibold">
                      {formatTokenCount(agent.total_tokens)}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Requests</p>
                    <p className="font-semibold">{agent.request_count}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Input</p>
                    <p>{formatTokenCount(agent.input_tokens)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Output</p>
                    <p>{formatTokenCount(agent.output_tokens)}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Grand total */}
          <Card className="border-primary/30">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">All Agents</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className="text-muted-foreground text-xs">Total</p>
                  <p className="font-semibold">
                    {formatTokenCount(summary.total.total_tokens)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">Requests</p>
                  <p className="font-semibold">
                    {summary.total.request_count}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">Input</p>
                  <p>{formatTokenCount(summary.total.input_tokens)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">Output</p>
                  <p>{formatTokenCount(summary.total.output_tokens)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Controls: date range + agent filter */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Usage Over Time</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            {/* Range presets */}
            <div className="space-y-1">
              <Label className="text-xs">Time Range</Label>
              <div className="flex gap-1">
                {presets.map((p) => (
                  <Button
                    key={p.value}
                    variant={rangePreset === p.value ? "default" : "outline"}
                    size="sm"
                    onClick={() => setRangePreset(p.value)}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Custom date inputs */}
            {rangePreset === "custom" && (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Start</Label>
                  <Input
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="w-40"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">End</Label>
                  <Input
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="w-40"
                  />
                </div>
              </>
            )}

            {/* Agent filter */}
            <div className="space-y-1">
              <Label className="text-xs">Agent</Label>
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="flex h-8 rounded-md border border-input bg-background px-3 text-sm shadow-xs"
              >
                <option value="">All Agents</option>
                {agents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.name} ({a.agent_id})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Chart */}
          {chartData.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatDate}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis
                    tickFormatter={(v: number) => formatTokenCount(v)}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    labelFormatter={(label) => String(label)}
                    formatter={(value, name) => [
                      formatTokenCount(Number(value)),
                      agentNameMap[String(name)] || String(name),
                    ]}
                  />
                  <Legend
                    formatter={(value: string) =>
                      agentNameMap[value] || value
                    }
                  />
                  {chartAgentIds.map((agentId) => (
                    <Area
                      key={agentId}
                      type="monotone"
                      dataKey={agentId}
                      stackId="1"
                      stroke={agentColorMap[agentId] ?? "#888"}
                      fill={agentColorMap[agentId] ?? "#888"}
                      fillOpacity={0.3}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-80 flex items-center justify-center text-muted-foreground text-sm">
              No usage data for this time range.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Empty state */}
      {summary && summary.agents.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              No token usage recorded yet. Start chatting with an agent to see
              usage data here.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
