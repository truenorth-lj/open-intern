"use client";

import { useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getMemories, deleteMemory, getMemoryStats } from "@/lib/api";
import type { MemoryEntry, MemoryStats } from "@/lib/types";

export default function MemoriesPage() {
  const [scope, setScope] = useState("all");
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [page, setPage] = useState(0);
  const limit = 20;

  useEffect(() => {
    getMemoryStats().then(setStats).catch((err) => console.error("Failed to load memory stats:", err));
  }, []);

  useEffect(() => {
    const s = scope === "all" ? undefined : scope;
    getMemories(s, limit, page * limit)
      .then((data) => {
        setMemories(data.items);
        setTotal(data.total);
      })
      .catch((err) => console.error("Failed to load memories:", err));
  }, [scope, page]);

  async function handleDelete(id: string) {
    await deleteMemory(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
    setTotal((prev) => prev - 1);
    if (stats) {
      getMemoryStats().then(setStats).catch((err) => console.error("Failed to refresh memory stats:", err));
    }
  }

  const scopeColor = (s: string) => {
    if (s === "shared") return "default";
    if (s === "channel") return "secondary";
    return "outline";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Memories</h2>
        {stats && (
          <div className="flex gap-2 text-sm text-muted-foreground">
            <span>{stats.total} total</span>
            <span>|</span>
            <span>{stats.shared} shared</span>
            <span>{stats.channel} channel</span>
            <span>{stats.personal} personal</span>
          </div>
        )}
      </div>

      <Tabs value={scope} onValueChange={(v) => { setScope(v); setPage(0); }}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="shared">Shared</TabsTrigger>
          <TabsTrigger value="channel">Channel</TabsTrigger>
          <TabsTrigger value="personal">Personal</TabsTrigger>
        </TabsList>

        <TabsContent value={scope} className="mt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50%]">Content</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Date</TableHead>
                <TableHead className="w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {memories.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                    No memories found.
                  </TableCell>
                </TableRow>
              )}
              {memories.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="max-w-md">
                    <p className="text-sm truncate">{m.content}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant={scopeColor(m.scope)}>{m.scope}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.source}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {m.created_at ? new Date(m.created_at).toLocaleDateString() : ""}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleDelete(m.id)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {total > limit && (
            <div className="flex justify-center gap-2 mt-4">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="text-sm text-muted-foreground self-center">
                Page {page + 1} of {Math.ceil(total / limit)}
              </span>
              <Button variant="outline" size="sm" disabled={(page + 1) * limit >= total} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
