import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Circle, Loader2, CheckCircle2, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface AgentTraceItem {
  step: number;
  agent: string;
  action: string;
  reasoning: string;
  duration_ms: number;
  timestamp: string;
}

interface AgentActivityPanelProps {
  trace: AgentTraceItem[];
  pipelineStatus: string;
}

const AGENT_ORDER = [
  "MasterOrchestratorAgent",
  "KYCVerificationAgent",
  "CreditUnderwritingAgent",
  "Negotiation Agent",
  "BlockchainAuditAgent",
];

const LABELS: Record<string, string> = {
  MasterOrchestratorAgent: "Master Agent",
  KYCVerificationAgent: "KYC Agent",
  CreditUnderwritingAgent: "Credit Agent",
  "Negotiation Agent": "Negotiation Agent",
  BlockchainAuditAgent: "Blockchain Agent",
};

export const AgentActivityPanel = ({ trace, pipelineStatus }: AgentActivityPanelProps) => {
  const [collapsed, setCollapsed] = useState(false);
  const doneSet = useMemo(() => new Set(trace.map((item) => item.agent)), [trace]);
  const activeAgent = useMemo(() => {
    const next = AGENT_ORDER.find((agent) => !doneSet.has(agent));
    return pipelineStatus === "SANCTIONED" ? null : next ?? null;
  }, [doneSet, pipelineStatus]);

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold">🤖 Agent Activity</div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </Button>
      </div>

      {!collapsed && (
        <div className="space-y-2">
          {AGENT_ORDER.map((agent) => {
            const item = trace.find((t) => t.agent === agent);
            const isDone = Boolean(item);
            const isActive = activeAgent === agent;
            const statusIcon = isDone ? (
              <CheckCircle2 className="h-4 w-4 text-green-500" />
            ) : isActive ? (
              <Loader2 className="h-4 w-4 animate-spin text-yellow-400" />
            ) : (
              <Circle className="h-4 w-4 text-muted-foreground" />
            );
            const statusText = isDone
              ? `${item?.action ?? "Completed"}${item?.duration_ms ? ` (${(item.duration_ms / 1000).toFixed(1)}s)` : ""}`
              : isActive
                ? "Processing..."
                : "Waiting";
            return (
              <div key={agent} className="flex items-center gap-2 rounded-md border border-border/70 p-2">
                <Bot className="h-4 w-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium">{LABELS[agent]}</div>
                  <div
                    className={cn(
                      "truncate text-[11px]",
                      isDone ? "text-green-500" : isActive ? "text-yellow-400" : "text-muted-foreground"
                    )}
                  >
                    {statusText}
                  </div>
                </div>
                {statusIcon}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
