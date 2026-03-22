"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { getSystemSettings, upsertSystemSetting } from "@/lib/api";

export default function SettingsPage() {
  const [defaultApiKey, setDefaultApiKey] = useState("");
  const [hasExistingKey, setHasExistingKey] = useState(false);
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSystemSettings()
      .then((data) => {
        const keySetting = data.settings.find(
          (s) => s.key === "default_llm_api_key",
        );
        if (keySetting && keySetting.value === "***") {
          setHasExistingKey(true);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  async function handleSave() {
    if (!defaultApiKey.trim()) {
      setMsg("Please enter an API key.");
      return;
    }
    try {
      await upsertSystemSetting(
        "default_llm_api_key",
        defaultApiKey,
        true,
        "Default LLM API key used when an agent has no key configured",
      );
      setMsg("Saved! Restart agents to apply.");
      setHasExistingKey(true);
      setDefaultApiKey("");
      setTimeout(() => setMsg(""), 5000);
    } catch {
      setMsg("Failed to save.");
    }
  }

  if (loading) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-2xl font-bold">Settings</h2>

      <Card>
        <CardHeader>
          <CardTitle>System Default API Key</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This key is used as a fallback when an agent does not have its own
            API key configured. It works for all LLM providers (Anthropic,
            MiniMax, OpenAI).
          </p>
          {hasExistingKey && (
            <Badge variant="outline">A default key is already configured</Badge>
          )}
          <div className="space-y-2">
            <Label htmlFor="default-key">API Key</Label>
            <Input
              id="default-key"
              type="password"
              placeholder={
                hasExistingKey
                  ? "(leave blank to keep current key)"
                  : "Enter your LLM API key..."
              }
              value={defaultApiKey}
              onChange={(e) => setDefaultApiKey(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleSave}>Save Default Key</Button>
            {msg && <Badge variant="secondary">{msg}</Badge>}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
