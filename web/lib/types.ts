export interface IdentityConfig {
  name: string;
  role: string;
  personality: string;
  avatar_url: string;
}

export interface LLMConfig {
  provider: string;
  model: string;
  api_key: string;
  temperature: number;
  max_tokens_per_action: number;
  daily_cost_budget_usd: number;
}

export interface MemoryEntry {
  id: string;
  content: string;
  scope: "shared" | "channel" | "personal";
  scope_id: string;
  source: string;
  importance: number;
  created_at: string;
}

export interface MemoryStats {
  shared: number;
  channel: number;
  personal: number;
  total: number;
}

export interface AgentStatus {
  name: string;
  role: string;
  platform: string;
  llm_provider: string;
  llm_model: string;
  memory_stats: MemoryStats;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Skill {
  name: string;
  description: string;
  files: { path: string; modified_at: string }[];
  modified_at: string;
  allowed_tools?: string;
  category?: string;
  version?: string;
  content?: string;
}

export interface AuthUser {
  user_id: string;
  email: string;
  role: "admin" | "user";
}
