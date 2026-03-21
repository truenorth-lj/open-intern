"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";

const navItems = [
  { href: "/", label: "Status", icon: "●" },
  { href: "/chat", label: "Chat", icon: "💬" },
  { href: "/memories", label: "Memories", icon: "🧠" },
  { href: "/skills", label: "Skills", icon: "🛠" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

const adminItems = [
  { href: "/admin", label: "Admin", icon: "🔧" },
];

interface NavSidebarProps {
  userRole?: "admin" | "user" | null;
}

export function NavSidebar({ userRole }: NavSidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const isAdmin = userRole === "admin" || user?.role === "admin";
  const items = isAdmin ? [...navItems, ...adminItems] : navItems;

  return (
    <aside className="w-56 border-r bg-muted/30 flex flex-col p-4 gap-1">
      <div className="mb-6 px-2">
        <h1 className="text-lg font-bold">open_intern</h1>
        <p className="text-xs text-muted-foreground">AI Employee Dashboard</p>
      </div>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
              ? "bg-secondary text-secondary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <span>{item.icon}</span>
          {item.label}
        </Link>
      ))}
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
