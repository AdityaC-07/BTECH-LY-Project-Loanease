import { useState, useEffect } from "react";
import { X, Clock, CheckCircle2, XCircle, Loader2, FileDown, Shield } from "lucide-react";
import { Button } from "./ui/button";
import { API_BASE_URL } from "@/config";
import { cn } from "@/lib/utils";

interface AuditEvent {
  timestamp: string;
  event: string;
  agent: string;
  status: string;
  details: string;
}

interface AuditTrailModalProps {
  sessionId: string;
  onClose: () => void;
}

const statusIcon = (status: string) => {
  switch (status.toUpperCase()) {
    case "SUCCESS":
      return <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" aria-hidden="true" />;
    case "FAILED":
    case "ERROR":
      return <XCircle className="w-4 h-4 text-red-400 shrink-0" aria-hidden="true" />;
    default:
      return <Clock className="w-4 h-4 text-muted-foreground shrink-0" aria-hidden="true" />;
  }
};

const formatTimestamp = (ts: string) => {
  try {
    return new Date(ts).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
};

export const AuditTrailModal = ({ sessionId, onClose }: AuditTrailModalProps) => {
  const [events, setEvents]   = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    const fetchAudit = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/kyc/audit/${sessionId}`, {
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setEvents(data.events ?? []);
      } catch (e) {
        setError("Could not load audit trail. The session may not exist or the server is unavailable.");
      } finally {
        setLoading(false);
      }
    };
    fetchAudit();
  }, [sessionId]);

  const downloadAudit = () => {
    const lines = events.map((e) =>
      `[${formatTimestamp(e.timestamp)}] ${e.agent} — ${e.event} (${e.status})\n  ${e.details}`
    );
    const blob = new Blob(
      [`LoanEase Audit Trail\nSession: ${sessionId}\n\n`, lines.join("\n\n")],
      { type: "text/plain" }
    );
    const url = URL.createObjectURL(blob);
    const a   = document.createElement("a");
    a.href     = url;
    a.download = `audit_${sessionId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Loan processing audit trail"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-accent" aria-hidden="true" />
            <h2 className="text-base font-semibold">Audit Trail</h2>
            <span className="text-xs text-muted-foreground font-mono">{sessionId}</span>
          </div>
          <div className="flex items-center gap-2">
            {events.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={downloadAudit}
                aria-label="Download audit trail as text file"
                className="text-xs"
              >
                <FileDown className="w-4 h-4 mr-1" aria-hidden="true" />
                Download
              </Button>
            )}
            <button
              onClick={onClose}
              aria-label="Close audit trail"
              className="rounded-full p-1 hover:bg-secondary/60 transition-colors"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-0">
          {loading && (
            <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
              Loading audit events…
            </div>
          )}

          {!loading && error && (
            <p className="text-center text-sm text-destructive py-12">{error}</p>
          )}

          {!loading && !error && events.length === 0 && (
            <p className="text-center text-sm text-muted-foreground py-12">
              No events recorded for this session yet.
            </p>
          )}

          {!loading && !error && events.length > 0 && (
            <ol aria-label="Audit events timeline">
              {events.map((ev, i) => (
                <li
                  key={i}
                  className={cn(
                    "relative flex gap-3 pb-5",
                    i < events.length - 1 &&
                      "before:absolute before:left-[7px] before:top-5 before:h-[calc(100%-8px)] before:w-px before:bg-border/50"
                  )}
                >
                  <div className="mt-0.5">{statusIcon(ev.status)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span className="font-medium text-sm text-foreground">{ev.event}</span>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {ev.agent}
                      </span>
                    </div>
                    {ev.details && (
                      <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                        {ev.details}
                      </p>
                    )}
                    <time
                      dateTime={ev.timestamp}
                      className="text-[10px] text-muted-foreground/70 mt-1 block"
                    >
                      {formatTimestamp(ev.timestamp)}
                    </time>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
};
