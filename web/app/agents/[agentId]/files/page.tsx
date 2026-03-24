"use client";

import { useEffect, useState, use, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listFiles, readFile, writeFile, createDirectory } from "@/lib/api";
import type { SandboxFileInfo } from "@/lib/api";

function formatSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function pathSegments(path: string): { name: string; path: string }[] {
  const parts = path.split("/").filter(Boolean);
  const segments: { name: string; path: string }[] = [{ name: "/", path: "/" }];
  let current = "";
  for (const part of parts) {
    current += "/" + part;
    segments.push({ name: part, path: current });
  }
  return segments;
}

export default function AgentFilesPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const [currentPath, setCurrentPath] = useState("/home/user");
  const [items, setItems] = useState<SandboxFileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // File viewer/editor state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [fileLoading, setFileLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  // New file/folder dialog
  const [showNewInput, setShowNewInput] = useState<"file" | "folder" | null>(null);
  const [newName, setNewName] = useState("");

  const loadDir = useCallback(
    async (path: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await listFiles(agentId, path);
        // Sort: directories first, then alphabetical
        const sorted = [...data.items].sort((a, b) => {
          if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
          return a.path.localeCompare(b.path);
        });
        setItems(sorted);
        setCurrentPath(path);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load directory");
      } finally {
        setLoading(false);
      }
    },
    [agentId],
  );

  useEffect(() => {
    loadDir(currentPath);
  }, [agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleOpen(item: SandboxFileInfo) {
    if (item.is_dir) {
      setSelectedFile(null);
      setEditing(false);
      loadDir(item.path);
      return;
    }
    // Open file
    setFileLoading(true);
    setSelectedFile(item.path);
    setEditing(false);
    try {
      const data = await readFile(agentId, item.path);
      setFileContent(data.content);
      setEditContent(data.content);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to read file";
      // Backend returns "is a directory" when is_dir was wrong — navigate instead
      if (msg.toLowerCase().includes("is a directory")) {
        setSelectedFile(null);
        loadDir(item.path);
        return;
      }
      setFileContent(`Error: ${msg}`);
    } finally {
      setFileLoading(false);
    }
  }

  function handleGoUp() {
    const parent = currentPath.replace(/\/[^/]+\/?$/, "") || "/";
    setSelectedFile(null);
    setEditing(false);
    loadDir(parent);
  }

  async function handleSave() {
    if (!selectedFile) return;
    setSaving(true);
    try {
      await writeFile(agentId, selectedFile, editContent);
      setFileContent(editContent);
      setEditing(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    const fullPath = `${currentPath.replace(/\/$/, "")}/${newName.trim()}`;
    try {
      if (showNewInput === "folder") {
        await createDirectory(agentId, fullPath);
      } else {
        await writeFile(agentId, fullPath, "");
      }
      setShowNewInput(null);
      setNewName("");
      loadDir(currentPath);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to create");
    }
  }

  const breadcrumbs = pathSegments(currentPath);
  const fileName = selectedFile ? selectedFile.split("/").pop() : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Files</h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { setShowNewInput("file"); setNewName(""); }}>
            + File
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setShowNewInput("folder"); setNewName(""); }}>
            + Folder
          </Button>
          <Button variant="outline" size="sm" onClick={() => loadDir(currentPath)}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-sm text-muted-foreground flex-wrap">
        {breadcrumbs.map((seg, i) => (
          <span key={seg.path} className="flex items-center gap-1">
            {i > 0 && <span>/</span>}
            <button
              className="hover:text-foreground hover:underline transition-colors"
              onClick={() => { setSelectedFile(null); setEditing(false); loadDir(seg.path); }}
            >
              {seg.name}
            </button>
          </span>
        ))}
        {fileName && (
          <>
            <span>/</span>
            <span className="text-foreground font-medium">{fileName}</span>
          </>
        )}
      </div>

      {/* New file/folder inline input */}
      {showNewInput && (
        <div className="flex items-center gap-2 p-3 border rounded-lg bg-muted/30">
          <span className="text-sm text-muted-foreground">
            New {showNewInput}:
          </span>
          <input
            autoFocus
            className="flex-1 bg-transparent border-b border-border text-sm outline-none px-1 py-0.5"
            placeholder={showNewInput === "folder" ? "folder-name" : "filename.txt"}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") setShowNewInput(null);
            }}
          />
          <Button size="sm" onClick={handleCreate}>Create</Button>
          <Button size="sm" variant="ghost" onClick={() => setShowNewInput(null)}>Cancel</Button>
        </div>
      )}

      {error && (
        <div className="p-3 border border-destructive/50 bg-destructive/10 rounded-lg text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex gap-4 min-h-[500px]">
        {/* File listing */}
        <div className={selectedFile ? "w-1/3 shrink-0" : "w-full"}>
          <div className="border rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead className="w-[100px] text-right">Size</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {currentPath !== "/" && (
                  <TableRow
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={handleGoUp}
                  >
                    <TableCell className="text-sm font-medium text-muted-foreground">..</TableCell>
                    <TableCell />
                  </TableRow>
                )}
                {loading && (
                  <TableRow>
                    <TableCell colSpan={2} className="text-center text-muted-foreground py-10">
                      Loading...
                    </TableCell>
                  </TableRow>
                )}
                {!loading && items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} className="text-center text-muted-foreground py-10">
                      Empty directory
                    </TableCell>
                  </TableRow>
                )}
                {!loading &&
                  items.map((item) => {
                    const name = item.path.split("/").pop() || item.path;
                    const isSelected = selectedFile === item.path;
                    return (
                      <TableRow
                        key={item.path}
                        className={`cursor-pointer hover:bg-muted/50 ${isSelected ? "bg-muted" : ""}`}
                        onClick={() => handleOpen(item)}
                      >
                        <TableCell className="text-sm">
                          <span className="flex items-center gap-2">
                            <span className="text-muted-foreground text-xs w-4">
                              {item.is_dir ? "📁" : "📄"}
                            </span>
                            <span className={`font-medium ${item.is_dir ? "" : "text-foreground"}`}>
                              {name}
                            </span>
                            {item.is_dir && (
                              <Badge variant="secondary" className="text-[10px] px-1 py-0">
                                dir
                              </Badge>
                            )}
                          </span>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground text-right">
                          {item.is_dir ? "—" : formatSize(item.size)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* File viewer/editor */}
        {selectedFile && (
          <div className="flex-1 border rounded-lg flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
              <span className="text-sm font-medium truncate">{selectedFile}</span>
              <div className="flex gap-2 shrink-0">
                {editing ? (
                  <>
                    <Button size="sm" onClick={handleSave} disabled={saving}>
                      {saving ? "Saving..." : "Save"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => { setEditing(false); setEditContent(fileContent); }}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                    Edit
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => { setSelectedFile(null); setEditing(false); }}
                >
                  Close
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              {fileLoading ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : editing ? (
                <textarea
                  className="w-full h-full p-4 font-mono text-sm bg-transparent resize-none outline-none min-h-[400px]"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  spellCheck={false}
                />
              ) : (
                <pre className="p-4 font-mono text-sm whitespace-pre-wrap break-words">
                  {fileContent}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
