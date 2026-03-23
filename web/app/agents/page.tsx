"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  testTelegramConnection,
  type AgentInfo,
} from "@/lib/api";

const LLM_PRESETS: Record<string, { provider: string; model: string }> = {
  "Claude Sonnet 4.6": { provider: "claude", model: "claude-sonnet-4-6" },
  "Claude Opus 4.6": { provider: "claude", model: "claude-opus-4-6" },
  "Claude Haiku 4.5": {
    provider: "claude",
    model: "claude-haiku-4-5-20251001",
  },
  "MiniMax M2.7": { provider: "minimax", model: "MiniMax-M2.7" },
  "OpenAI GPT-4o": { provider: "openai", model: "gpt-4o" },
  "OpenAI o3": { provider: "openai", model: "o3" },
};

const defaultAgentForm = {
  agent_id: "",
  name: "",
  role: "AI Employee",
  personality: "You are a helpful AI employee.",
  llm_provider: "claude",
  llm_model: "claude-sonnet-4-6",
  llm_temperature: 0.7,
  llm_api_key: "",
  sandbox_enabled: true,
  platform_type: "",
  telegram_token: "",
  discord_token: "",
  lark_app_id: "",
  lark_app_secret: "",
};

export default function AgentsPage() {
  const { user, loading: authLoading } = useAuth();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [agentForm, setAgentForm] = useState(defaultAgentForm);
  const [agentMsg, setAgentMsg] = useState("");
  const [loadError, setLoadError] = useState("");
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [testChatId, setTestChatId] = useState("");
  const [testMsg, setTestMsg] = useState("");
  const [testLoading, setTestLoading] = useState(false);

  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!authLoading) {
      setLoadError("");
      listAgents()
        .then((data) => setAgents(data.agents))
        .catch((err) => setLoadError(err.message || "Failed to load agents"))
        .finally(() => setLoading(false));
    }
  }, [authLoading, reloadKey]);

  function reload() {
    setReloadKey((k) => k + 1);
  }

  function handleNewAgent() {
    setEditingAgent(null);
    setAgentForm(defaultAgentForm);
    setAgentMsg("");
    setShowForm(true);
  }

  function handleEditAgent(agent: AgentInfo) {
    setEditingAgent(agent.agent_id);
    setTestChatId("");
    setTestMsg("");
    setTestLoading(false);
    setAgentForm({
      agent_id: agent.agent_id,
      name: agent.name,
      role: agent.role,
      personality: agent.personality,
      llm_provider: agent.llm_provider,
      llm_model: agent.llm_model,
      llm_temperature: agent.llm_temperature,
      llm_api_key: "",
      sandbox_enabled: agent.sandbox_enabled,
      platform_type: agent.platform_type || "",
      telegram_token: "",
      discord_token: "",
      lark_app_id: "",
      lark_app_secret: "",
    });
    setAgentMsg("");
    setShowForm(true);
  }

  async function handleSubmitAgent(e: React.FormEvent) {
    e.preventDefault();
    setAgentMsg("");
    if (!editingAgent && !agentForm.agent_id.trim()) {
      setAgentMsg("Agent ID is required.");
      return;
    }
    if (!agentForm.name.trim()) {
      setAgentMsg("Name is required.");
      return;
    }
    try {
      if (editingAgent) {
        const { agent_id: _id, llm_api_key, telegram_token, discord_token, lark_app_id, lark_app_secret, ...updates } = agentForm;
        void _id;
        const payload: Record<string, unknown> = { ...updates };
        if (llm_api_key) payload.llm_api_key = llm_api_key;
        if (telegram_token) payload.telegram_token = telegram_token;
        if (discord_token) payload.discord_token = discord_token;
        if (lark_app_id) payload.lark_app_id = lark_app_id;
        if (lark_app_secret) payload.lark_app_secret = lark_app_secret;
        await updateAgent(editingAgent, payload);
        setAgentMsg("Agent updated. Restart to apply runtime changes.");
      } else {
        await createAgent(agentForm);
        setAgentMsg("Agent created successfully.");
      }
      setShowForm(false);
      setEditingAgent(null);
      reload();
    } catch (err) {
      setAgentMsg(err instanceof Error ? err.message : "Failed to save agent");
    }
  }

  async function handleDeleteAgent(agentId: string) {
    setAgentMsg("");
    try {
      await deleteAgent(agentId);
      setAgentMsg(`Agent '${agentId}' deactivated.`);
      reload();
    } catch (err) {
      setAgentMsg(
        err instanceof Error ? err.message : "Failed to delete agent",
      );
    }
  }

  function handleLLMPreset(presetName: string) {
    const preset = LLM_PRESETS[presetName];
    if (preset) {
      setAgentForm((f) => ({
        ...f,
        llm_provider: preset.provider,
        llm_model: preset.model,
      }));
    }
  }

  if (authLoading || loading) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  if (loadError) {
    return (
      <div className="text-destructive text-sm p-4">
        Failed to load agents: {loadError}
      </div>
    );
  }

  const activeAgents = agents.filter((a) => a.is_active);
  const inactiveAgents = agents.filter((a) => !a.is_active);

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Agents</h2>
        {isAdmin && (
          <Button onClick={handleNewAgent}>Create Agent</Button>
        )}
      </div>

      {agentMsg && (
        <p className="text-sm text-muted-foreground">{agentMsg}</p>
      )}

      {/* Create / Edit form (admin only) */}
      {showForm && isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>
              {editingAgent ? `Edit Agent: ${editingAgent}` : "New Agent"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmitAgent} className="space-y-4">
              {!editingAgent && (
                <div className="space-y-2">
                  <Label htmlFor="agent-id">Agent ID</Label>
                  <Input
                    id="agent-id"
                    placeholder="e.g. rin, helper-bot"
                    value={agentForm.agent_id}
                    onChange={(e) =>
                      setAgentForm((f) => ({
                        ...f,
                        agent_id: e.target.value,
                      }))
                    }
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    Unique identifier, cannot be changed later.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="agent-name">Name</Label>
                  <Input
                    id="agent-name"
                    placeholder="Rin"
                    value={agentForm.name}
                    onChange={(e) =>
                      setAgentForm((f) => ({ ...f, name: e.target.value }))
                    }
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="agent-role">Role</Label>
                  <Input
                    id="agent-role"
                    placeholder="AI Employee"
                    value={agentForm.role}
                    onChange={(e) =>
                      setAgentForm((f) => ({ ...f, role: e.target.value }))
                    }
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="agent-personality">Personality</Label>
                <Textarea
                  id="agent-personality"
                  placeholder="You are a helpful AI employee..."
                  value={agentForm.personality}
                  onChange={(e) =>
                    setAgentForm((f) => ({
                      ...f,
                      personality: e.target.value,
                    }))
                  }
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label>LLM Model</Label>
                <div className="flex flex-wrap gap-2">
                  {Object.keys(LLM_PRESETS).map((name) => {
                    const preset = LLM_PRESETS[name];
                    const isSelected =
                      agentForm.llm_provider === preset.provider &&
                      agentForm.llm_model === preset.model;
                    return (
                      <button
                        key={name}
                        type="button"
                        onClick={() => handleLLMPreset(name)}
                        className={`px-3 py-1 rounded-md text-sm border transition-colors ${
                          isSelected
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background border-border hover:bg-muted"
                        }`}
                      >
                        {name}
                      </button>
                    );
                  })}
                </div>
                <div className="grid grid-cols-2 gap-4 mt-2">
                  <div className="space-y-1">
                    <Label htmlFor="llm-provider" className="text-xs">
                      Provider
                    </Label>
                    <Input
                      id="llm-provider"
                      value={agentForm.llm_provider}
                      onChange={(e) =>
                        setAgentForm((f) => ({
                          ...f,
                          llm_provider: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="llm-model" className="text-xs">
                      Model
                    </Label>
                    <Input
                      id="llm-model"
                      value={agentForm.llm_model}
                      onChange={(e) =>
                        setAgentForm((f) => ({
                          ...f,
                          llm_model: e.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="llm-api-key">API Key</Label>
                <Input
                  id="llm-api-key"
                  type="password"
                  placeholder={editingAgent ? "(leave blank to keep current key)" : "Enter API key..."}
                  value={agentForm.llm_api_key}
                  onChange={(e) =>
                    setAgentForm((f) => ({
                      ...f,
                      llm_api_key: e.target.value,
                    }))
                  }
                />
                <p className="text-xs text-muted-foreground">
                  LLM API key for this agent. Falls back to system default if empty.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="llm-temp">Temperature</Label>
                  <Input
                    id="llm-temp"
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={agentForm.llm_temperature}
                    onChange={(e) =>
                      setAgentForm((f) => ({
                        ...f,
                        llm_temperature: parseFloat(e.target.value) || 0,
                      }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Sandbox</Label>
                  <div className="flex items-center gap-2 h-8">
                    <input
                      type="checkbox"
                      id="sandbox"
                      checked={agentForm.sandbox_enabled}
                      onChange={(e) =>
                        setAgentForm((f) => ({
                          ...f,
                          sandbox_enabled: e.target.checked,
                        }))
                      }
                      className="size-4 rounded border-input"
                    />
                    <Label htmlFor="sandbox" className="font-normal">
                      Enable E2B sandbox
                    </Label>
                  </div>
                </div>
              </div>

              {/* Platform Connections */}
              <div className="space-y-4 border-t pt-4">
                <Label className="text-base font-semibold">Platform Connections</Label>
                <p className="text-xs text-muted-foreground">
                  Connect this agent to multiple platforms. Leave credentials blank to skip a platform.
                </p>

                {/* Telegram */}
                <details className="rounded-md border" open={
                  editingAgent
                    ? agents.find((a) => a.agent_id === editingAgent)?.telegram_token === "***"
                    : false
                }>
                  <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                    Telegram
                    {editingAgent && agents.find((a) => a.agent_id === editingAgent)?.telegram_token === "***" && (
                      <Badge variant="outline" className="text-xs">Connected</Badge>
                    )}
                  </summary>
                  <div className="px-3 pb-3 space-y-3">
                    <div className="space-y-2">
                      <Label htmlFor="telegram-token">Bot Token</Label>
                      <Input
                        id="telegram-token"
                        type="password"
                        placeholder={editingAgent ? "(leave blank to keep current token)" : "Enter Telegram bot token..."}
                        value={agentForm.telegram_token}
                        onChange={(e) =>
                          setAgentForm((f) => ({
                            ...f,
                            telegram_token: e.target.value,
                          }))
                        }
                      />
                      <p className="text-xs text-muted-foreground">
                        Get a bot token from{" "}
                        <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="underline">
                          @BotFather
                        </a>.
                      </p>
                    </div>

                    {editingAgent && agents.find((a) => a.agent_id === editingAgent)?.telegram_token === "***" && (
                      <div className="space-y-2 rounded-md border p-3 bg-muted/30">
                        <Label className="text-sm font-medium">Test Connection</Label>
                        <div className="grid grid-cols-2 gap-2">
                          <Input
                            placeholder="Chat ID (e.g. 123456789)"
                            value={testChatId}
                            onChange={(e) => setTestChatId(e.target.value)}
                          />
                          <Button
                            type="button"
                            variant="outline"
                            disabled={!testChatId.trim() || testLoading}
                            onClick={async () => {
                              setTestLoading(true);
                              setTestMsg("");
                              try {
                                const result = await testTelegramConnection(editingAgent, testChatId.trim());
                                setTestMsg(`Sent via @${result.bot_username}`);
                              } catch (err) {
                                setTestMsg(err instanceof Error ? err.message : "Test failed");
                              } finally {
                                setTestLoading(false);
                              }
                            }}
                          >
                            {testLoading ? "Sending..." : "Send Test Message"}
                          </Button>
                        </div>
                        {testMsg && (
                          <p className={`text-xs ${testMsg.startsWith("Sent") ? "text-green-600" : "text-destructive"}`}>
                            {testMsg}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          Get your chat ID by messaging{" "}
                          <a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer" className="underline">
                            @userinfobot
                          </a>.
                        </p>
                      </div>
                    )}
                  </div>
                </details>

                {/* Discord */}
                <details className="rounded-md border" open={
                  editingAgent
                    ? agents.find((a) => a.agent_id === editingAgent)?.discord_token === "***"
                    : false
                }>
                  <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                    Discord
                    {editingAgent && agents.find((a) => a.agent_id === editingAgent)?.discord_token === "***" && (
                      <Badge variant="outline" className="text-xs">Connected</Badge>
                    )}
                  </summary>
                  <div className="px-3 pb-3 space-y-2">
                    <Label htmlFor="discord-token">Bot Token</Label>
                    <Input
                      id="discord-token"
                      type="password"
                      placeholder={editingAgent ? "(leave blank to keep current token)" : "Enter Discord bot token..."}
                      value={agentForm.discord_token}
                      onChange={(e) =>
                        setAgentForm((f) => ({
                          ...f,
                          discord_token: e.target.value,
                        }))
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      Get a bot token from the{" "}
                      <a href="https://discord.com/developers/applications" target="_blank" rel="noopener noreferrer" className="underline">
                        Discord Developer Portal
                      </a>.
                    </p>
                  </div>
                </details>

                {/* Lark */}
                <details className="rounded-md border" open={
                  editingAgent
                    ? agents.find((a) => a.agent_id === editingAgent)?.lark_app_id === "***"
                    : false
                }>
                  <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                    Lark
                    {editingAgent && agents.find((a) => a.agent_id === editingAgent)?.lark_app_id === "***" && (
                      <Badge variant="outline" className="text-xs">Connected</Badge>
                    )}
                  </summary>
                  <div className="px-3 pb-3 space-y-3">
                    <div className="space-y-2">
                      <Label htmlFor="lark-app-id">App ID</Label>
                      <Input
                        id="lark-app-id"
                        type="password"
                        placeholder={editingAgent ? "(leave blank to keep current)" : "cli_xxxxxxxx"}
                        value={agentForm.lark_app_id}
                        onChange={(e) =>
                          setAgentForm((f) => ({
                            ...f,
                            lark_app_id: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="lark-app-secret">App Secret</Label>
                      <Input
                        id="lark-app-secret"
                        type="password"
                        placeholder={editingAgent ? "(leave blank to keep current)" : "Enter App Secret..."}
                        value={agentForm.lark_app_secret}
                        onChange={(e) =>
                          setAgentForm((f) => ({
                            ...f,
                            lark_app_secret: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Get credentials from{" "}
                      <a href="https://open.larksuite.com" target="_blank" rel="noopener noreferrer" className="underline">
                        Lark Developer Console
                      </a>{" "}
                      → Credentials &amp; Basic Info.
                    </p>
                  </div>
                </details>
              </div>

              <div className="flex gap-2 pt-2">
                <Button type="submit">
                  {editingAgent ? "Update Agent" : "Create Agent"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setShowForm(false);
                    setEditingAgent(null);
                    setTestChatId("");
                    setTestMsg("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Active agents */}
      {activeAgents.length === 0 && !showForm && (
        <p className="text-muted-foreground">
          No active agents.{" "}
          {isAdmin && "Click \"Create Agent\" to add one."}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {activeAgents.map((agent) => (
          <Card key={agent.agent_id} className="flex flex-col">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-lg">{agent.name}</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    {agent.agent_id}
                  </p>
                </div>
                <Badge variant="outline">Active</Badge>
              </div>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col gap-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{agent.role}</Badge>
                <Badge variant="secondary">
                  {agent.llm_provider}:{agent.llm_model}
                </Badge>
                {agent.telegram_token === "***" && (
                  <Badge variant="outline">Telegram</Badge>
                )}
                {agent.discord_token === "***" && (
                  <Badge variant="outline">Discord</Badge>
                )}
                {agent.lark_app_id === "***" && (
                  <Badge variant="outline">Lark</Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2 flex-1">
                {agent.personality}
              </p>
              <div className="flex gap-2 pt-2">
                <Link href={`/agents/${agent.agent_id}/chat`} className="flex-1">
                  <Button variant="outline" className="w-full">Chat</Button>
                </Link>
                <Link href={`/agents/${agent.agent_id}/memories`}>
                  <Button variant="outline" size="sm">Memories</Button>
                </Link>
                <Link href={`/agents/${agent.agent_id}/skills`}>
                  <Button variant="outline" size="sm">Skills</Button>
                </Link>
                {isAdmin && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEditAgent(agent)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteAgent(agent.agent_id)}
                    >
                      Deactivate
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Inactive agents (collapsed) */}
      {inactiveAgents.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">
            Inactive ({inactiveAgents.length})
          </h3>
          {inactiveAgents.map((agent) => (
            <div
              key={agent.agent_id}
              className="border rounded-lg p-3 flex items-center justify-between opacity-60"
            >
              <div>
                <p className="font-medium text-sm">
                  {agent.name}{" "}
                  <span className="text-muted-foreground font-normal">
                    ({agent.agent_id})
                  </span>
                </p>
                <Badge variant="destructive" className="mt-1">
                  Inactive
                </Badge>
              </div>
              {isAdmin && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleEditAgent(agent)}
                >
                  Edit
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
