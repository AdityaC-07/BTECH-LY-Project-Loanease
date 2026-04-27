import { useMemo, useState, useEffect } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Loader2, CheckCircle2, Bot, X, PanelLeftClose, PanelLeftOpen } from "lucide-react";
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
  const [isDemoMode, setIsDemoMode] = useState(false);
  const doneSet = useMemo(() => new Set(trace.map((item) => item.agent)), [trace]);
  
  // Detect demo mode from URL param
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setIsDemoMode(params.get("demo") === "true");
  }, []);

  const activeAgent = useMemo(() => {
    const next = AGENT_ORDER.find((agent) => !doneSet.has(agent));
    return pipelineStatus === "SANCTIONED" || pipelineStatus === "FAILED" ? null : next ?? null;
  }, [doneSet, pipelineStatus]);

  const hasActiveAgent = activeAgent !== null;

  // Collapsed sidebar - just show toggle button
  if (collapsed) {
    return (
      <div className="agent-sidebar collapsed flex-shrink-0 flex flex-col items-center py-4 bg-card border-l border-border">
        <button 
          className="p-2 rounded-lg hover:bg-muted transition-colors mb-4"
          onClick={() => setCollapsed(false)}
          title="Expand Agent Activity"
        >
          <PanelLeftOpen className="w-5 h-5 text-muted-foreground" />
        </button>
        
        <div className="flex flex-col gap-2 items-center">
          {AGENT_ORDER.slice(0, 4).map((agent) => {
            const item = trace.find((t) => t.agent === agent);
            const isDone = Boolean(item);
            const isActive = activeAgent === agent;
            
            return (
              <div 
                key={agent} 
                className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center transition-all",
                  isDone ? "bg-green-500/20 text-green-500" : 
                  isActive ? "bg-yellow-400/20 text-yellow-400 animate-pulse" : 
                  "bg-muted/50 text-muted-foreground"
                )}
                title={LABELS[agent]}
              >
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : isActive ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <span className="text-xs font-bold">{AGENT_ORDER.indexOf(agent) + 1}</span>
                )}
              </div>
            );
          })}
        </div>
        
        {hasActiveAgent && (
          <div className="mt-auto">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
          </div>
        )}
      </div>
    );
  }

  // Expanded sidebar
  return (
    <div className="agent-sidebar flex-shrink-0 flex flex-col bg-card border-l border-border overflow-hidden">
      <div className="sidebar-content flex-1 flex flex-col overflow-hidden">
        {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-title">
          <span>🤖</span>
          <span>Agent Activity</span>
        </div>
        {isDemoMode && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-yellow-400/20 text-yellow-400 font-semibold border border-yellow-400/30 animate-pulse-soft">
            ⚡ Demo
          </span>
        )}
        <button 
          className="p-1.5 hover:bg-muted rounded-md transition-colors"
          onClick={() => setCollapsed(true)}
          title="Collapse sidebar"
        >
          <PanelLeftClose className="w-4 h-4 text-muted-foreground" />
        </button>
      </div>

      {/* Agent List */}
      <div className="flex-1 p-0 overflow-y-auto scrollbar-hide">
        {AGENT_ORDER.map((agent) => {
          const item = trace.find((t) => t.agent === agent);
          const isDone = Boolean(item);
          const isActive = activeAgent === agent;
          
          return (
            <div 
              key={agent} 
              className={cn(
                "agent-item",
                isDone ? "completed" : 
                isActive ? "active" : 
                "waiting"
              )}
            >
              <div className="flex items-center gap-2">
                {isDone ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                ) : isActive ? (
                  <Loader2 className="h-4 w-4 animate-spin text-yellow-400 shrink-0" />
                ) : (
                  <div className="h-4 w-4 rounded-full border-2 border-muted-foreground shrink-0 flex items-center justify-center">
                    <span className="text-[8px]">{AGENT_ORDER.indexOf(agent) + 1}</span>
                  </div>
                )}
                
                <div className="min-w-0 flex-1">
                  <div className={cn(
                    "truncate text-sm font-semibold",
                    isActive && "text-yellow-400"
                  )}>
                    {LABELS[agent]}
                  </div>
                </div>
              </div>

              <div className="pl-0">
                {isDone && item && (
                  <div className="text-xs text-muted-foreground break-words leading-tight">
                    {item.action || "Completed successfully"}
                    <div className="mt-1 text-[10px] opacity-70 font-mono">
                      {(item.duration_ms / 1000).toFixed(1)}s
                    </div>
                  </div>
                )}
                
                {isActive && (
                  <div className="text-xs text-muted-foreground break-words leading-tight">
                    <div className="w-full bg-muted rounded-full h-1.5 mt-1 mb-1.5 overflow-hidden">
                      <div className="bg-yellow-400 h-full w-2/3 animate-pulse" />
                    </div>
                    Processing...
                  </div>
                )}

                {!isDone && !isActive && (
                  <div className="text-xs text-muted-foreground">Waiting</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Footer Status */}
      {hasActiveAgent && (
        <div className="p-2 border-t border-border/50 bg-muted/10 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            <span className="text-[10px] font-medium text-muted-foreground">Groq LLaMA 70B</span>
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">📡 :8000</span>
        </div>
      )}
      </div>
    </div>
  );
};
