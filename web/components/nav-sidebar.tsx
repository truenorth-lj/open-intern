"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Status", icon: "●" },
  { href: "/chat", label: "Chat", icon: "💬" },
  { href: "/memories", label: "Memories", icon: "🧠" },
  { href: "/skills", label: "Skills", icon: "🛠" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

export function NavSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 border-r bg-muted/30 flex flex-col p-4 gap-1">
      <div className="mb-6 px-2">
        <h1 className="text-lg font-bold">open_intern</h1>
        <p className="text-xs text-muted-foreground">AI Employee Dashboard</p>
      </div>
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            pathname === item.href
              ? "bg-secondary text-secondary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <span>{item.icon}</span>
          {item.label}
        </Link>
      ))}
    </aside>
  );
}
