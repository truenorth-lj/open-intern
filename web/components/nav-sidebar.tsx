"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

const globalItems = [
  { href: "/agents", label: "Agents", icon: "+" },
  { href: "/usage", label: "Usage", icon: "U" },
  { href: "/settings", label: "Settings", icon: "S" },
];

const adminItems = [
  { href: "/admin", label: "Admin", icon: "A" },
];

const agentSubItems = [
  { suffix: "/chat", label: "Chat" },
  { suffix: "/memories", label: "Memories" },
  { suffix: "/skills", label: "Skills" },
];

interface NavSidebarProps {
  userRole?: "admin" | "user" | null;
}

export function NavSidebar({ userRole }: NavSidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const isAdmin = userRole === "admin" || user?.role === "admin";
  const items = isAdmin ? [...globalItems, ...adminItems] : globalItems;

  // Detect if we're inside an agent scope: /agents/[agentId]/...
  const agentMatch = pathname.match(/^\/agents\/([^/]+)\//);
  const activeAgentId = agentMatch ? agentMatch[1] : null;
  const agentBase = activeAgentId ? `/agents/${activeAgentId}` : null;

  return (
    <aside className="w-56 border-r bg-muted/30 flex flex-col p-4 gap-1">
      <div className="mb-6 px-2">
        <h1 className="text-lg font-bold">open_intern</h1>
        <p className="text-xs text-muted-foreground">AI Employee Dashboard</p>
      </div>

      {/* Global nav */}
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            pathname === item.href ||
              (item.href === "/agents" && pathname.startsWith("/agents"))
              ? "bg-secondary text-secondary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {item.label}
        </Link>
      ))}

      {/* Agent sub-nav (shown when inside an agent) */}
      {activeAgentId && agentBase && (
        <div className="mt-4 border-t pt-3 space-y-1">
          <Link
            href="/agents"
            className="text-xs text-muted-foreground hover:text-foreground px-3 transition-colors"
          >
            &larr; All Agents
          </Link>
          <p className="px-3 text-xs font-semibold text-foreground truncate mt-2">
            {activeAgentId}
          </p>
          {agentSubItems.map((sub) => {
            const href = `${agentBase}${sub.suffix}`;
            const isActive = pathname.startsWith(href);
            return (
              <Link
                key={sub.suffix}
                href={href}
                className={cn(
                  "block rounded-lg px-3 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-secondary text-secondary-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {sub.label}
              </Link>
            );
          })}
        </div>
      )}

      <div className="mt-auto pt-4 border-t">
        {user && (
          <div className="px-3 py-2">
            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
            <p className="text-xs text-muted-foreground capitalize">{user.role}</p>
          </div>
        )}
        <button
          onClick={logout}
          className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
