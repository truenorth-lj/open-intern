"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { getSkills } from "@/lib/api";
import type { Skill } from "@/lib/types";

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    getSkills()
      .then((data) => setSkills(data.skills))
      .catch((err) => console.error("Failed to load skills:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        Loading skills...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Skills</h2>
        <span className="text-sm text-muted-foreground">
          {skills.length} skill{skills.length !== 1 ? "s" : ""} loaded
        </span>
      </div>

      {skills.length === 0 ? (
        <Card className="p-10 text-center text-muted-foreground">
          No skills found. Add skill directories under{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">skills/</code>{" "}
          and restart the agent.
        </Card>
      ) : (
        <div className="grid gap-4">
          {skills.map((skill) => (
            <Card key={skill.name} className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-lg font-semibold">{skill.name}</h3>
                    {skill.version && (
                      <Badge variant="outline">v{skill.version}</Badge>
                    )}
                    {skill.category && (
                      <Badge variant="secondary">{skill.category}</Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    {skill.description}
                  </p>

                  <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                    {skill.allowed_tools && (
                      <span>
                        Tools:{" "}
                        <code className="bg-muted px-1 py-0.5 rounded">
                          {skill.allowed_tools}
                        </code>
                      </span>
                    )}
                    <span>
                      {skill.files.length} file
                      {skill.files.length !== 1 ? "s" : ""}
                    </span>
                    {skill.modified_at && (
                      <span>
                        Updated:{" "}
                        {new Date(skill.modified_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setExpanded(expanded === skill.name ? null : skill.name)
                  }
                >
                  {expanded === skill.name ? "Collapse" : "Details"}
                </Button>
              </div>

              {expanded === skill.name && (
                <div className="mt-4 border-t pt-4 space-y-3">
                  {skill.content && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">
                        Instructions
                      </h4>
                      <pre className="text-xs bg-muted p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">
                        {skill.content}
                      </pre>
                    </div>
                  )}

                  <div>
                    <h4 className="text-sm font-medium mb-2">Files</h4>
                    <ul className="space-y-1">
                      {skill.files.map((f) => (
                        <li
                          key={f.path}
                          className="text-xs text-muted-foreground flex justify-between"
                        >
                          <code className="bg-muted px-1 py-0.5 rounded">
                            {f.path}
                          </code>
                          {f.modified_at && (
                            <span>
                              {new Date(f.modified_at).toLocaleString()}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
