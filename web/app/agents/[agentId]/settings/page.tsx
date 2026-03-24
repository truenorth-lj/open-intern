"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  getAgentDetail,
  updateAgent,
  reloadAgent,
  testTelegramConnection,
  createApiKey,
  listApiKeys,
  revokeApiKey,
  backupSandbox,
  listSandboxBackups,
  restoreSandbox,
  type AgentInfo,
  type ApiKeyInfo,
  type BackupEntry,
} from "@/lib/api";
import { useDesktopStream } from "@/lib/use-desktop-stream";

const LLM_PRESETS: Record<string, { provider: string; model: string }> = {
  "Claude Sonnet 4.6": { provider: "claude", model: "claude-sonnet-4-6" },
  "Claude Opus 4.6": { provider: "claude", model: "claude-opus-4-6" },
  "Claude Haiku 4.5": { provider: "claude", model: "claude-haiku-4-5-20251001" },
  "MiniMax M2.7": { provider: "minimax", model: "MiniMax-M2.7" },
  "OpenAI GPT-4o": { provider: "openai", model: "gpt-4o" },
  "OpenAI o3": { provider: "openai", model: "o3" },
};

export default function AgentSettingsPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const { user, loading: authLoading } = useAuth();
  const [agent, setAgent] = useState<AgentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  // Form state
  const [form, setForm] = useState({
    name: "",
    role: "",
    personality: "",
    llm_provider: "",
    llm_model: "",
    llm_temperature: 0.7,
    llm_api_key: "",
    sandbox_mode: "base",
    ssh_host: "",
    ssh_port: 22,
    ssh_user: "user",
    ssh_key: "",
    platform_type: "",
    telegram_token: "",
    discord_token: "",
    lark_app_id: "",
    lark_app_secret: "",
  });

  // Telegram test
  const [testChatId, setTestChatId] = useState("");
  const [testMsg, setTestMsg] = useState("");
  const [testLoading, setTestLoading] = useState(false);

  // Desktop stream
  const stream = useDesktopStream(agentId);

  // API keys
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);
  const [apiKeyName, setApiKeyName] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [apiKeyMsg, setApiKeyMsg] = useState("");

  // Sandbox backups
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupMsg, setBackupMsg] = useState("");

  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (authLoading) return;
    loadAgent();
    loadApiKeys();
    loadBackups();
    stream.loadStatus();
  }, [authLoading, agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadAgent() {
    try {
      const data = await getAgentDetail(agentId);
      setAgent(data);
      setForm({
        name: data.name,
        role: data.role,
        personality: data.personality,
        llm_provider: data.llm_provider,
        llm_model: data.llm_model,
        llm_temperature: data.llm_temperature,
        llm_api_key: "",
        sandbox_mode: data.sandbox_mode || "base",
        ssh_host: data.ssh_host || "",
        ssh_port: data.ssh_port || 22,
        ssh_user: data.ssh_user || "user",
        ssh_key: "",
        platform_type: data.platform_type || "",
        telegram_token: "",
        discord_token: "",
        lark_app_id: "",
        lark_app_secret: "",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agent");
    } finally {
      setLoading(false);
    }
  }

  async function loadApiKeys() {
    try {
      const data = await listApiKeys(agentId);
      setApiKeys(data.api_keys);
    } catch {
      // ignore — may not have access
    }
  }

  async function loadBackups() {
    try {
      const data = await listSandboxBackups(agentId);
      setBackups(data.backups);
    } catch {
      // ignore
    }
  }

  async function handleBackup() {
    setBackupLoading(true);
    setBackupMsg("");
    try {
      await backupSandbox(agentId);
      setBackupMsg("Backup created.");
      loadBackups();
    } catch (err) {
      setBackupMsg(err instanceof Error ? err.message : "Backup failed");
    } finally {
      setBackupLoading(false);
    }
  }

  async function handleRestore() {
    setBackupLoading(true);
    setBackupMsg("");
    try {
      await restoreSandbox(agentId);
      setBackupMsg("Restore complete.");
      loadBackups();
    } catch (err) {
      setBackupMsg(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setBackupLoading(false);
    }
  }

  async function handleSave() {
    setMsg("");
    const { llm_api_key, telegram_token, discord_token, lark_app_id, lark_app_secret, ssh_key, ...rest } = form;
    const payload: Record<string, unknown> = { ...rest };
    if (llm_api_key) payload.llm_api_key = llm_api_key;
    if (telegram_token) payload.telegram_token = telegram_token;
    if (discord_token) payload.discord_token = discord_token;
    if (lark_app_id) payload.lark_app_id = lark_app_id;
    if (lark_app_secret) payload.lark_app_secret = lark_app_secret;
    if (ssh_key) payload.ssh_key = ssh_key;

    try {
      await updateAgent(agentId, payload);
      setMsg("Agent updated successfully.");
      loadAgent();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to update agent");
    }
  }

  async function handleReload() {
    try {
      await reloadAgent(agentId);
      setMsg("Agent runtime reloaded.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to reload");
    }
  }

  function handleLLMPreset(presetName: string) {
    const preset = LLM_PRESETS[presetName];
    if (preset) {
      setForm((f) => ({ ...f, llm_provider: preset.provider, llm_model: preset.model }));
    }
  }

  async function handleCreateApiKey() {
    setApiKeyMsg("");
    setNewApiKey("");
    try {
      const result = await createApiKey(agentId, apiKeyName);
      setNewApiKey(result.key);
      setApiKeyName("");
      loadApiKeys();
    } catch (err) {
      setApiKeyMsg(err instanceof Error ? err.message : "Failed to create API key");
    }
  }

  async function handleRevokeApiKey(keyId: string) {
    try {
      await revokeApiKey(agentId, keyId);
      loadApiKeys();
    } catch (err) {
      setApiKeyMsg(err instanceof Error ? err.message : "Failed to revoke API key");
    }
  }

  if (authLoading || loading) {
    return <p className="text-muted-foreground p-4">Loading...</p>;
  }

  if (error) {
    return <div className="text-destructive text-sm p-4">{error}</div>;
  }

  if (!agent) {
    return <div className="text-destructive text-sm p-4">Agent not found</div>;
  }

  const showDesktop = agent.sandbox_mode === "desktop" || form.sandbox_mode === "desktop";

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Link href="/agents" className="text-muted-foreground hover:text-foreground text-sm">
              Agents
            </Link>
            <span className="text-muted-foreground">/</span>
            <h2 className="text-2xl font-bold">{agent.name}</h2>
            <Badge variant={agent.is_active ? "outline" : "destructive"}>
              {agent.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{agentId}</p>
        </div>
        <div className="flex gap-2">
          <Link href={`/agents/${agentId}/chat`}>
            <Button variant="outline">Chat</Button>
          </Link>
          {isAdmin && (
            <Button variant="outline" onClick={handleReload}>
              Reload Runtime
            </Button>
          )}
        </div>
      </div>

      {msg && <p className="text-sm text-muted-foreground">{msg}</p>}

      {/* Non-admin: read-only info */}
      {!isAdmin ? (
        <Card>
          <CardHeader>
            <CardTitle>Agent Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p><span className="text-muted-foreground">Role:</span> {agent.role}</p>
            <p><span className="text-muted-foreground">Model:</span> {agent.llm_provider}:{agent.llm_model}</p>
            <p><span className="text-muted-foreground">Personality:</span> {agent.personality}</p>
          </CardContent>
        </Card>
      ) : (
        /* Admin: tabbed settings */
        <Tabs defaultValue="general">
          <TabsList>
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="model">Model</TabsTrigger>
            <TabsTrigger value="platforms">Platforms</TabsTrigger>
            {showDesktop && <TabsTrigger value="desktop">Desktop</TabsTrigger>}
          </TabsList>

          {/* ── General Tab ── */}
          <TabsContent value="general">
            <Card>
              <CardHeader>
                <CardTitle>General</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="agent-name">Name</Label>
                      <Input
                        id="agent-name"
                        value={form.name}
                        onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="agent-role">Role</Label>
                      <Input
                        id="agent-role"
                        value={form.role}
                        onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="agent-personality">Personality</Label>
                    <Textarea
                      id="agent-personality"
                      value={form.personality}
                      onChange={(e) => setForm((f) => ({ ...f, personality: e.target.value }))}
                      rows={3}
                    />
                  </div>

                  <Button type="button" onClick={handleSave}>Save Changes</Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Model Tab ── */}
          <TabsContent value="model">
            <Card>
              <CardHeader>
                <CardTitle>LLM Model</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Quick Select</Label>
                    <div className="flex flex-wrap gap-2">
                      {Object.keys(LLM_PRESETS).map((name) => {
                        const preset = LLM_PRESETS[name];
                        const isSelected =
                          form.llm_provider === preset.provider && form.llm_model === preset.model;
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
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <Label htmlFor="llm-provider">Provider</Label>
                      <Input
                        id="llm-provider"
                        value={form.llm_provider}
                        onChange={(e) => setForm((f) => ({ ...f, llm_provider: e.target.value }))}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="llm-model">Model</Label>
                      <Input
                        id="llm-model"
                        value={form.llm_model}
                        onChange={(e) => setForm((f) => ({ ...f, llm_model: e.target.value }))}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="llm-api-key">API Key</Label>
                    <Input
                      id="llm-api-key"
                      type="password"
                      placeholder="(leave blank to keep current key)"
                      value={form.llm_api_key}
                      onChange={(e) => setForm((f) => ({ ...f, llm_api_key: e.target.value }))}
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
                        value={form.llm_temperature}
                        onChange={(e) =>
                          setForm((f) => ({ ...f, llm_temperature: parseFloat(e.target.value) || 0 }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="sandbox-mode">Sandbox</Label>
                      <select
                        id="sandbox-mode"
                        value={form.sandbox_mode}
                        onChange={(e) => setForm((f) => ({ ...f, sandbox_mode: e.target.value }))}
                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors"
                      >
                        <option value="none">None (local shell)</option>
                        <option value="base">Base (CLI sandbox)</option>
                        <option value="desktop">Desktop (GUI + browser)</option>
                        <option value="ssh">SSH (remote machine)</option>
                      </select>
                    </div>
                  </div>

                  {form.sandbox_mode === "ssh" && (
                    <div className="rounded-md border p-4 space-y-4">
                      <h4 className="text-sm font-medium">SSH Connection</h4>
                      <p className="text-xs text-muted-foreground">
                        Connect to a remote machine (Mac Mini, Raspberry Pi, cloud VM, etc.) via SSH.
                      </p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="space-y-2 md:col-span-2">
                          <Label htmlFor="ssh-host">Host</Label>
                          <Input
                            id="ssh-host"
                            placeholder="192.168.1.100 or hostname"
                            value={form.ssh_host}
                            onChange={(e) => setForm((f) => ({ ...f, ssh_host: e.target.value }))}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="ssh-port">Port</Label>
                          <Input
                            id="ssh-port"
                            type="number"
                            value={form.ssh_port}
                            onChange={(e) =>
                              setForm((f) => ({ ...f, ssh_port: parseInt(e.target.value) || 22 }))
                            }
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="ssh-user">Username</Label>
                        <Input
                          id="ssh-user"
                          placeholder="user"
                          value={form.ssh_user}
                          onChange={(e) => setForm((f) => ({ ...f, ssh_user: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="ssh-key">Private Key (PEM)</Label>
                        <Textarea
                          id="ssh-key"
                          rows={4}
                          placeholder={agent?.ssh_key === "***" ? "(encrypted — leave blank to keep)" : "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"}
                          value={form.ssh_key}
                          onChange={(e) => setForm((f) => ({ ...f, ssh_key: e.target.value }))}
                          className="font-mono text-xs"
                        />
                        <p className="text-xs text-muted-foreground">
                          Paste your SSH private key. Leave blank to rely on ssh-agent.
                          The key is encrypted at rest.
                        </p>
                      </div>
                    </div>
                  )}

                  <Button type="button" onClick={handleSave}>Save Changes</Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Platforms Tab ── */}
          <TabsContent value="platforms">
            <Card>
              <CardHeader>
                <CardTitle>Platform Connections</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Connect this agent to multiple platforms. Leave credentials blank to skip.
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                  {/* Telegram */}
                  <details className="rounded-md border" open={agent.telegram_token === "***"}>
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                      Telegram
                      {agent.telegram_token === "***" && (
                        <Badge variant="outline" className="text-xs">Connected</Badge>
                      )}
                    </summary>
                    <div className="px-3 pb-3 space-y-3">
                      <div className="space-y-2">
                        <Label htmlFor="telegram-token">Bot Token</Label>
                        <Input
                          id="telegram-token"
                          type="password"
                          placeholder="(leave blank to keep current token)"
                          value={form.telegram_token}
                          onChange={(e) => setForm((f) => ({ ...f, telegram_token: e.target.value }))}
                        />
                      </div>
                      {agent.telegram_token === "***" && (
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
                                  const result = await testTelegramConnection(agentId, testChatId.trim());
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
                        </div>
                      )}
                    </div>
                  </details>

                  {/* Discord */}
                  <details className="rounded-md border" open={agent.discord_token === "***"}>
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                      Discord
                      {agent.discord_token === "***" && (
                        <Badge variant="outline" className="text-xs">Connected</Badge>
                      )}
                    </summary>
                    <div className="px-3 pb-3 space-y-2">
                      <Label htmlFor="discord-token">Bot Token</Label>
                      <Input
                        id="discord-token"
                        type="password"
                        placeholder="(leave blank to keep current token)"
                        value={form.discord_token}
                        onChange={(e) => setForm((f) => ({ ...f, discord_token: e.target.value }))}
                      />
                    </div>
                  </details>

                  {/* Lark */}
                  <details className="rounded-md border" open={agent.lark_app_id === "***"}>
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2">
                      Lark
                      {agent.lark_app_id === "***" && (
                        <Badge variant="outline" className="text-xs">Connected</Badge>
                      )}
                    </summary>
                    <div className="px-3 pb-3 space-y-3">
                      <div className="space-y-2">
                        <Label htmlFor="lark-app-id">App ID</Label>
                        <Input
                          id="lark-app-id"
                          type="password"
                          placeholder="(leave blank to keep current)"
                          value={form.lark_app_id}
                          onChange={(e) => setForm((f) => ({ ...f, lark_app_id: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="lark-app-secret">App Secret</Label>
                        <Input
                          id="lark-app-secret"
                          type="password"
                          placeholder="(leave blank to keep current)"
                          value={form.lark_app_secret}
                          onChange={(e) => setForm((f) => ({ ...f, lark_app_secret: e.target.value }))}
                        />
                      </div>
                    </div>
                  </details>

                  <Button type="button" onClick={handleSave}>Save Changes</Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Desktop Tab (conditional) ── */}
          {showDesktop && (
            <TabsContent value="desktop">
              <Card>
                <CardHeader>
                  <CardTitle>Desktop Stream</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    View the agent&apos;s desktop environment with browser in real-time via noVNC.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {stream.error && (
                    <p className="text-sm text-destructive">{stream.error}</p>
                  )}

                  {stream.streamUrl ? (
                    <>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-green-600 border-green-600">
                          Streaming
                        </Badge>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => window.open(stream.streamUrl!, "_blank")}
                        >
                          Open in New Tab
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={stream.pause}
                          disabled={stream.loading}
                        >
                          {stream.loading ? "Pausing..." : "Pause (keep data)"}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={stream.stop}
                          disabled={stream.loading}
                        >
                          Stop &amp; Destroy
                        </Button>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Pause preserves sandbox state (files, installed packages). Stop destroys everything.
                      </p>
                      <div className="rounded-md border overflow-hidden bg-black">
                        <iframe
                          src={stream.streamUrl}
                          className="w-full border-0"
                          style={{ height: "600px" }}
                          allow="clipboard-read; clipboard-write"
                          title="Desktop Stream"
                        />
                      </div>
                    </>
                  ) : stream.sandboxStatus === "paused" ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-yellow-600 border-yellow-600">
                          Paused
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                          Sandbox is paused. Files and state are preserved.
                        </span>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          onClick={stream.resume}
                          disabled={stream.loading}
                        >
                          {stream.loading ? "Resuming..." : "Resume Desktop"}
                        </Button>
                        <Button
                          variant="outline"
                          onClick={stream.stop}
                          disabled={stream.loading}
                        >
                          Destroy Sandbox
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button
                      onClick={stream.start}
                      disabled={stream.loading}
                    >
                      {stream.loading ? "Starting Desktop..." : "Launch Desktop"}
                    </Button>
                  )}

                  {/* Backups */}
                  <div className="border-t pt-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-base font-semibold">Backups</Label>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleBackup}
                        disabled={backupLoading || !stream.streamUrl}
                      >
                        {backupLoading ? "Backing up..." : "Backup Now"}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Backups save all files and installed packages to Cloudflare R2.
                      Automatically created when pausing.
                    </p>
                    {backupMsg && (
                      <p className={`text-xs ${backupMsg.includes("failed") ? "text-destructive" : "text-green-600"}`}>
                        {backupMsg}
                      </p>
                    )}
                    {backups.length > 0 ? (
                      <div className="space-y-1">
                        {backups.slice(0, 5).map((b) => (
                          <div
                            key={b.key}
                            className="flex items-center justify-between text-xs rounded border px-3 py-2"
                          >
                            <div>
                              <span className="font-mono">
                                {new Date(b.timestamp).toLocaleString()}
                              </span>
                              <span className="text-muted-foreground ml-2">
                                {(b.size_bytes / 1024 / 1024).toFixed(1)} MB
                              </span>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleRestore}
                              disabled={backupLoading}
                            >
                              Restore
                            </Button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No backups yet.</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      )}

      {/* API Keys — visible to all users */}
      <Card>
        <CardHeader>
          <CardTitle>API Keys</CardTitle>
          <p className="text-sm text-muted-foreground">
            Use API keys to access this agent programmatically. Send requests with the{" "}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">X-Agent-API-Key</code> header.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {isAdmin && (
            <div className="flex gap-2">
              <Input
                placeholder="Key name (optional)"
                value={apiKeyName}
                onChange={(e) => setApiKeyName(e.target.value)}
                className="max-w-xs"
              />
              <Button type="button" variant="outline" onClick={handleCreateApiKey}>
                Create API Key
              </Button>
            </div>
          )}

          {newApiKey && (
            <div className="rounded-md border border-green-500/50 bg-green-500/10 p-3 space-y-2">
              <p className="text-sm font-medium text-green-700 dark:text-green-400">
                API key created. Copy it now — it won&apos;t be shown again.
              </p>
              <code className="block text-xs bg-muted p-2 rounded break-all select-all">
                {newApiKey}
              </code>
            </div>
          )}

          {apiKeyMsg && <p className="text-sm text-destructive">{apiKeyMsg}</p>}

          {apiKeys.length > 0 ? (
            <div className="space-y-2">
              {apiKeys.map((k) => (
                <div
                  key={k.id}
                  className={`flex items-center justify-between rounded-md border p-3 ${
                    !k.is_active ? "opacity-50" : ""
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <code className="text-sm">{k.key_prefix}...</code>
                      {k.name && <span className="text-sm text-muted-foreground">{k.name}</span>}
                      <Badge variant={k.is_active ? "outline" : "destructive"} className="text-xs">
                        {k.is_active ? "Active" : "Revoked"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Created {k.created_at ? new Date(k.created_at).toLocaleDateString() : "—"}
                      {k.last_used_at && ` · Last used ${new Date(k.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  {k.is_active && isAdmin && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRevokeApiKey(k.id)}
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No API keys yet.</p>
          )}

          {/* Usage example */}
          <details className="rounded-md border">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
              Usage Example
            </summary>
            <div className="px-3 pb-3">
              <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">{`curl -X POST ${typeof window !== "undefined" ? window.location.origin : "http://localhost:8000"}/api/dashboard/chat \\
  -H "X-Agent-API-Key: oi_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{"message": "Hello", "agent_id": "${agentId}"}'`}</pre>
            </div>
          </details>
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex gap-2">
        <Link href={`/agents/${agentId}/memories`}>
          <Button variant="outline" size="sm">Memories</Button>
        </Link>
        <Link href={`/agents/${agentId}/skills`}>
          <Button variant="outline" size="sm">Skills</Button>
        </Link>
        <Link href={`/agents/${agentId}/scheduled-jobs`}>
          <Button variant="outline" size="sm">Scheduled Jobs</Button>
        </Link>
      </div>
    </div>
  );
}
