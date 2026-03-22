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
import { apiFetch, listAgents, type AgentInfo } from "@/lib/api";

interface User {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  agent_ids: string[];
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [users, setUsers] = useState<User[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const [newEmail, setNewEmail] = useState("");
  const [createdPassword, setCreatedPassword] = useState("");
  const [createMsg, setCreateMsg] = useState("");
  const [resetPasswords, setResetPasswords] = useState<Record<string, string>>(
    {},
  );
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
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
        "User created! Password shown below (copy it now, it won't be shown again).",
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

  if (authLoading || loading) {
    return <p className="text-muted-foreground">Loading...</p>;
  }
  if (user?.role !== "admin") return null;

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-2xl font-bold">Admin Settings</h2>

      {/* Create User */}
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

      {/* User List */}
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
            <div key={u.user_id} className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{u.email}</p>
                  <div className="flex gap-2 mt-1">
                    <Badge variant="secondary">{u.role}</Badge>
                    <Badge variant={u.is_active ? "outline" : "destructive"}>
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
                    onClick={() => handleToggleActive(u.user_id, u.is_active)}
                  >
                    {u.is_active ? "Deactivate" : "Activate"}
                  </Button>
                </div>
              </div>

              {resetPasswords[u.user_id] && (
                <div className="bg-muted p-3 rounded-md">
                  <p className="text-sm font-medium">New Password:</p>
                  <code className="text-sm font-mono select-all">
                    {resetPasswords[u.user_id]}
                  </code>
                </div>
              )}

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
                    onClick={() => {
                      setEditingUser(u.user_id);
                      setSelectedAgents(u.agent_ids);
                    }}
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
