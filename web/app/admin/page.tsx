"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  type AgentInfo,
} from "@/lib/api";

interface User {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  agent_ids: string[];
}

const BASE = "/api/dashboard";

const LLM_PRESETS: Record<string, { provider: string; model: string }> = {
  "Claude Sonnet 4.6": { provider: "claude", model: "claude-sonnet-4-6" },
  "Claude Opus 4.6": { provider: "claude", model: "claude-opus-4-6" },
  "Claude Haiku 4.5": { provider: "claude", model: "claude-haiku-4-5-20251001" },
  "MiniMax M2.7": { provider: "minimax", model: "MiniMax-M2.7" },
  "OpenAI GPT-4o": { provider: "openai", model: "gpt-4o" },
  "OpenAI o3": { provider: "openai", model: "o3" },
};

async function apiFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, init);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return res;
}

const defaultAgentForm = {
  agent_id: "",
  name: "",
  role: "AI Employee",
  personality: "You are a helpful AI employee.",
  llm_provider: "claude",
  llm_model: "claude-sonnet-4-6",
  llm_temperature: 0.7,
  sandbox_enabled: true,
};

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [users, setUsers] = useState<User[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  // Create user form
  const [newEmail, setNewEmail] = useState("");
  const [createdPassword, setCreatedPassword] = useState("");
  const [createMsg, setCreateMsg] = useState("");

  // Reset password state
  const [resetPasswords, setResetPasswords] = useState<Record<string, string>>(
    {},
  );

  // Agent assignment state
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);

  // Agent CRUD state
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [agentForm, setAgentForm] = useState(defaultAgentForm);
  const [agentMsg, setAgentMsg] = useState("");
  const [editingAgent, setEditingAgent] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!authLoading && user?.role !== "admin") {
      router.push("/");
      return;
    }
    if (!authLoading && user?.role === "admin") {
      Promise.all([apiFetch("/auth/users"), listAgents()])
        .then(([usersRes, agentsData]) => {
          if (usersRes.ok) {
            usersRes.json().then((data) => setUsers(data.users));
          }
          setAgents(agentsData.agents);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [authLoading, user, router, reloadKey]);

  function reload() {
    setReloadKey((k) => k + 1);
  }

  // --- User handlers ---

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    setCreateMsg("");
    setCreatedPassword("");

    const res = await apiFetch("/auth/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: newEmail }),
    });

    if (res.ok) {
      const data = await res.json();
      setCreatedPassword(data.password);
      setCreateMsg(
        `User created! Password shown below (copy it now, it won't be shown again).`,
      );
      setNewEmail("");
      reload();
    } else {
      const data = await res.json().catch(() => ({}));
      setCreateMsg(data.detail || "Failed to create user");
    }
  }

  async function handleResetPassword(userId: string) {
    const res = await apiFetch(`/auth/users/${userId}/reset-password`, {
      method: "POST",
    });
    if (res.ok) {
      const data = await res.json();
      setResetPasswords((prev) => ({ ...prev, [userId]: data.password }));
    }
  }

  async function handleToggleActive(userId: string, currentlyActive: boolean) {
    await apiFetch(`/auth/users/${userId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    reload();
  }

  async function handleEditAgents(userId: string, currentAgentIds: string[]) {
    setEditingUser(userId);
    setSelectedAgents(currentAgentIds);
  }

  async function handleSaveAgents() {
    if (!editingUser) return;
    await apiFetch(`/auth/users/${editingUser}/agents`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_ids: selectedAgents }),
    });
    setEditingUser(null);
    reload();
  }

  function toggleAgent(agentId: string) {
    setSelectedAgents((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId],
    );
  }

  // --- Agent handlers ---

  function handleNewAgent() {
    setEditingAgent(null);
    setAgentForm(defaultAgentForm);
    setAgentMsg("");
    setShowAgentForm(true);
  }

  function handleEditAgent(agent: AgentInfo) {
    setEditingAgent(agent.agent_id);
    setAgentForm({
      agent_id: agent.agent_id,
      name: agent.name,
      role: agent.role,
      personality: agent.personality,
      llm_provider: agent.llm_provider,
      llm_model: agent.llm_model,
      llm_temperature: agent.llm_temperature,
      sandbox_enabled: agent.sandbox_enabled,
    });
    setAgentMsg("");
    setShowAgentForm(true);
  }

  async function handleSubmitAgent(e: React.FormEvent) {
    e.preventDefault();
    setAgentMsg("");
    try {
      if (editingAgent) {
        const { agent_id: _agentId, ...updates } = agentForm;
        void _agentId;
        await updateAgent(editingAgent, updates);
        setAgentMsg("Agent updated. Restart to apply runtime changes.");
      } else {
        await createAgent(agentForm);
        setAgentMsg("Agent created successfully.");
      }
      setShowAgentForm(false);
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

  if (user?.role !== "admin") {
    return null;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-2xl font-bold">Admin Settings</h2>

      {/* ── Agents Section ── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Agents ({agents.length})</CardTitle>
          <Button size="sm" onClick={handleNewAgent}>
            Create Agent
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {agentMsg && (
            <p className="text-sm text-muted-foreground">{agentMsg}</p>
          )}

          {/* Agent form (create / edit) */}
          {showAgentForm && (
            <form
              onSubmit={handleSubmitAgent}
              className="border rounded-lg p-4 space-y-4 bg-muted/30"
            >
              <p className="font-medium">
                {editingAgent ? `Edit Agent: ${editingAgent}` : "New Agent"}
              </p>

              {!editingAgent && (
                <div className="space-y-2">
                  <Label htmlFor="agent-id">Agent ID</Label>
                  <Input
                    id="agent-id"
                    placeholder="e.g. rin, helper-bot"
                    value={agentForm.agent_id}
                    onChange={(e) =>
                      setAgentForm((f) => ({ ...f, agent_id: e.target.value }))
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

              <div className="flex gap-2 pt-2">
                <Button type="submit">
                  {editingAgent ? "Update Agent" : "Create Agent"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setShowAgentForm(false);
                    setEditingAgent(null);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {/* Agent list */}
          {agents.length === 0 && !showAgentForm && (
            <p className="text-sm text-muted-foreground">
              No agents created yet. Click &quot;Create Agent&quot; to add one.
            </p>
          )}
          {agents.map((agent) => (
            <div
              key={agent.agent_id}
              className="border rounded-lg p-4 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">
                    {agent.name}{" "}
                    <span className="text-muted-foreground font-normal">
                      ({agent.agent_id})
                    </span>
                  </p>
                  <div className="flex gap-2 mt-1">
                    <Badge variant="secondary">{agent.role}</Badge>
                    <Badge variant={agent.is_active ? "outline" : "destructive"}>
                      {agent.is_active ? "Active" : "Inactive"}
                    </Badge>
                    <Badge variant="secondary">
                      {agent.llm_provider}:{agent.llm_model}
                    </Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleEditAgent(agent)}
                  >
                    Edit
                  </Button>
                  {agent.is_active && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteAgent(agent.agent_id)}
                    >
                      Deactivate
                    </Button>
                  )}
                </div>
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2">
                {agent.personality}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Separator />

      {/* ── Create User ── */}
      <Card>
        <CardHeader>
          <CardTitle>Create User</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreateUser} className="space-y-4">
            <div className="flex gap-3 items-end">
              <div className="flex-1 space-y-2">
                <Label htmlFor="new-email">Email</Label>
                <Input
                  id="new-email"
                  type="email"
                  placeholder="user@company.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  required
                />
              </div>
              <Button type="submit">Create User</Button>
            </div>
            {createMsg && (
              <p className="text-sm text-muted-foreground">{createMsg}</p>
            )}
            {createdPassword && (
              <div className="bg-muted p-3 rounded-md">
                <p className="text-sm font-medium">Generated Password:</p>
                <code className="text-sm font-mono select-all">
                  {createdPassword}
                </code>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      <Separator />

      {/* ── User List ── */}
      <Card>
        <CardHeader>
          <CardTitle>Users ({users.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {users.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No users created yet.
            </p>
          )}
          {users.map((u) => (
            <div
              key={u.user_id}
              className="border rounded-lg p-4 space-y-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{u.email}</p>
                  <div className="flex gap-2 mt-1">
                    <Badge variant="secondary">{u.role}</Badge>
                    <Badge
                      variant={u.is_active ? "outline" : "destructive"}
                    >
                      {u.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleResetPassword(u.user_id)}
                  >
                    Reset Password
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      handleToggleActive(u.user_id, u.is_active)
                    }
                  >
                    {u.is_active ? "Deactivate" : "Activate"}
                  </Button>
                </div>
              </div>

              {/* Show reset password */}
              {resetPasswords[u.user_id] && (
                <div className="bg-muted p-3 rounded-md">
                  <p className="text-sm font-medium">New Password:</p>
                  <code className="text-sm font-mono select-all">
                    {resetPasswords[u.user_id]}
                  </code>
                </div>
              )}

              {/* Agent access */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-muted-foreground">
                    Agent Access:{" "}
                    {u.agent_ids.length === 0
                      ? "None"
                      : u.agent_ids.join(", ")}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      handleEditAgents(u.user_id, u.agent_ids)
                    }
                  >
                    Edit
                  </Button>
                </div>

                {editingUser === u.user_id && (
                  <div className="bg-muted/50 p-3 rounded-md space-y-2">
                    <p className="text-sm font-medium">Select agents:</p>
                    <div className="flex flex-wrap gap-2">
                      {agents
                        .filter((a) => a.is_active)
                        .map((agent) => (
                          <button
                            key={agent.agent_id}
                            onClick={() => toggleAgent(agent.agent_id)}
                            className={`px-3 py-1 rounded-md text-sm border transition-colors ${
                              selectedAgents.includes(agent.agent_id)
                                ? "bg-primary text-primary-foreground border-primary"
                                : "bg-background border-border hover:bg-muted"
                            }`}
                          >
                            {agent.name} ({agent.agent_id})
                          </button>
                        ))}
                    </div>
                    <div className="flex gap-2 pt-2">
                      <Button size="sm" onClick={handleSaveAgents}>
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditingUser(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
