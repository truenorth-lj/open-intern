import { AgentChatSidebar } from "@/components/agent-chat-sidebar";

export default function AgentChatLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ agentId: string }>;
}) {
  return (
    <div className="flex h-full -m-6">
      <AgentChatSidebar paramsPromise={params} />
      <div className="flex-1 flex flex-col p-4">{children}</div>
    </div>
  );
}
