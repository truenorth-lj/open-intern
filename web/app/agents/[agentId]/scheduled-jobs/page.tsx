"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import {
  listScheduledJobs,
  deleteScheduledJob,
  pauseScheduledJob,
  resumeScheduledJob,
  triggerScheduledJob,
  type ScheduledJob,
} from "@/lib/api";

function formatSchedule(job: ScheduledJob): string {
  if (job.schedule_type === "interval") {
    const secs = parseInt(job.schedule_expr, 10);
    if (isNaN(secs)) return job.schedule_expr;
    if (secs < 60) return `Every ${secs}s`;
    if (secs < 3600) return `Every ${Math.round(secs / 60)}m`;
    if (secs < 86400) return `Every ${Math.round(secs / 3600)}h`;
    return `Every ${Math.round(secs / 86400)}d`;
  }
  if (job.schedule_type === "cron") return `Cron: ${job.schedule_expr}`;
  if (job.schedule_type === "once") {
    try {
      return `Once: ${new Date(job.schedule_expr).toLocaleString()}`;
    } catch {
      return job.schedule_expr;
    }
  }
  return job.schedule_expr;
}

function formatTime(iso: string | null): string {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ScheduledJobsPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMsg, setActionMsg] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  async function loadJobs() {
    try {
      setError("");
      const data = await listScheduledJobs(agentId);
      setJobs(data.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadJobs();
  }, [agentId]);

  async function handleAction(
    jobId: string,
    action: () => Promise<void>,
    successMsg: string,
  ) {
    try {
      setPendingAction(jobId);
      setActionMsg("");
      setError("");
      await action();
      setActionMsg(successMsg);
      setConfirmDeleteId(null);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setPendingAction(null);
    }
  }

  if (loading) {
    return <div className="text-muted-foreground p-8">Loading scheduled jobs...</div>;
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Scheduled Jobs</h2>
          <p className="text-muted-foreground text-sm mt-1">
            Cron jobs and interval tasks for this agent
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadJobs}>
            Refresh
          </Button>
          <Link href={`/agents/${agentId}/settings`}>
            <Button variant="outline" size="sm">Settings</Button>
          </Link>
        </div>
      </div>

      {error && (
        <div className="text-destructive text-sm bg-destructive/10 rounded p-3">
          {error}
        </div>
      )}
      {actionMsg && (
        <div className="text-green-600 text-sm bg-green-500/10 rounded p-3">
          {actionMsg}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Jobs ({jobs.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <p className="text-muted-foreground text-center py-10">
              No scheduled jobs yet. Jobs created via chat will appear here.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>Prompt</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Run</TableHead>
                  <TableHead>Next Run</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-medium max-w-[150px] truncate">
                      {job.name}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {formatSchedule(job)}
                    </TableCell>
                    <TableCell
                      className="max-w-[200px] truncate text-sm"
                      title={job.prompt}
                    >
                      {job.prompt}
                    </TableCell>
                    <TableCell>
                      {job.enabled ? (
                        <Badge variant="outline" className="text-green-600 border-green-600">
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Paused</Badge>
                      )}
                      {job.last_run_status === "error" && (
                        <Badge variant="destructive" className="ml-1" title={job.last_run_error || ""}>
                          Error
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {formatTime(job.last_run_at)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {formatTime(job.next_run_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex gap-1 justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={pendingAction !== null}
                          onClick={() =>
                            handleAction(
                              job.id,
                              () => triggerScheduledJob(job.id),
                              `Triggered "${job.name}"`,
                            )
                          }
                        >
                          {pendingAction === job.id ? "..." : "Run"}
                        </Button>
                        {job.enabled ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={pendingAction !== null}
                            onClick={() =>
                              handleAction(
                                job.id,
                                () => pauseScheduledJob(job.id),
                                `Paused "${job.name}"`,
                              )
                            }
                          >
                            Pause
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={pendingAction !== null}
                            onClick={() =>
                              handleAction(
                                job.id,
                                () => resumeScheduledJob(job.id),
                                `Resumed "${job.name}"`,
                              )
                            }
                          >
                            Resume
                          </Button>
                        )}
                        {confirmDeleteId === job.id ? (
                          <div className="flex gap-1">
                            <Button
                              variant="destructive"
                              size="sm"
                              disabled={pendingAction !== null}
                              onClick={() =>
                                handleAction(
                                  job.id,
                                  () => deleteScheduledJob(job.id),
                                  `Deleted "${job.name}"`,
                                )
                              }
                            >
                              Confirm
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setConfirmDeleteId(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={pendingAction !== null}
                            onClick={() => setConfirmDeleteId(job.id)}
                          >
                            Delete
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Job details expandable section */}
      {jobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Job Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {jobs.map((job) => (
              <details key={job.id} className="border rounded p-3">
                <summary className="cursor-pointer font-medium text-sm">
                  {job.name}
                  <span className="text-muted-foreground ml-2 font-normal">
                    ({job.id.slice(0, 8)}...)
                  </span>
                </summary>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    {job.schedule_type}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Expression:</span>{" "}
                    <code className="bg-muted px-1 rounded">{job.schedule_expr}</code>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Timezone:</span>{" "}
                    {job.timezone}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Isolated:</span>{" "}
                    {job.isolated ? "Yes" : "No"}
                  </div>
                  {job.delivery_platform && (
                    <>
                      <div>
                        <span className="text-muted-foreground">Delivery:</span>{" "}
                        {job.delivery_platform}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Chat ID:</span>{" "}
                        <code className="bg-muted px-1 rounded">{job.delivery_chat_id}</code>
                      </div>
                    </>
                  )}
                  <div className="col-span-2">
                    <span className="text-muted-foreground">Prompt:</span>
                    <pre className="mt-1 bg-muted p-2 rounded text-xs whitespace-pre-wrap">
                      {job.prompt}
                    </pre>
                  </div>
                  {job.last_run_error && (
                    <div className="col-span-2">
                      <span className="text-destructive">Last error:</span>
                      <pre className="mt-1 bg-destructive/10 p-2 rounded text-xs whitespace-pre-wrap">
                        {job.last_run_error}
                      </pre>
                    </div>
                  )}
                  <div>
                    <span className="text-muted-foreground">Created:</span>{" "}
                    {formatTime(job.created_at)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Updated:</span>{" "}
                    {formatTime(job.updated_at)}
                  </div>
                </div>
              </details>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
