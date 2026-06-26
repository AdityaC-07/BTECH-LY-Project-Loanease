import { useState } from 'react';
import { Check, Clock, X, Loader2, ChevronDown, ChevronUp } from 'lucide-react';

export type AgentType = 'master' | 'kyc' | 'credit' | 'negotiation' | 'blockchain';
export type AgentStatus = 'idle' | 'waiting' | 'processing' | 'completed' | 'failed';

interface AgentEvent {
  timestamp: string;
  action: string;
}

interface AgentCardConfig {
  id: AgentType;
  name: string;
  status: AgentStatus;
  color: string;
  lastAction?: string;
  events: AgentEvent[];
}

interface AgentSidebarProps {
  agents: AgentCardConfig[];
  isResponding?: boolean;
}

const AGENT_COLORS = {
  master: '#F5C518',
  kyc: '#51CF66',
  credit: '#4C6EF5',
  negotiation: '#FF922B',
  blockchain: '#A78BFA'
};

const getStatusIcon = (status: AgentStatus) => {
  switch (status) {
    case 'completed':
      return <Check className="w-4 h-4" />;
    case 'processing':
      return <Loader2 className="w-4 h-4 animate-spin" />;
    case 'failed':
      return <X className="w-4 h-4" />;
    case 'waiting':
      return <Clock className="w-4 h-4" />;
    case 'idle':
    default:
      return <Clock className="w-4 h-4 opacity-50" />;
  }
};

const getStatusColor = (status: AgentStatus) => {
  switch (status) {
    case 'completed':
      return '#51CF66';
    case 'processing':
      return '#4C6EF5';
    case 'failed':
      return '#FF6B6B';
    case 'waiting':
      return '#FFD700';
    case 'idle':
    default:
      return '#666';
  }
};

const formatTimestamp = (timestamp?: string): string => {
  if (!timestamp) return 'Now';
  
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'Now';
  if (diffMins < 60) return `${diffMins} min${diffMins > 1 ? 's' : ''} ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return `${Math.floor(diffMins / 1440)}d ago`;
};

function AgentCard({ agent }: { agent: AgentCardConfig }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const visibleEvents = isExpanded ? agent.events : agent.events.slice(0, 3);
  const hasMoreEvents = agent.events.length > 3;

  return (
    <div 
      className="w-full mb-3 p-3 rounded"
      style={{
        backgroundColor: '#2A2A2A',
        borderLeft: `6px solid ${agent.color}`,
        borderRadius: '6px'
      }}
    >
      {/* Agent Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div 
            className="flex items-center justify-center"
            style={{ color: getStatusColor(agent.status) }}
          >
            {getStatusIcon(agent.status)}
          </div>
          <span 
            className="font-bold"
            style={{ 
              color: agent.color,
              fontSize: '16px',
              fontFamily: 'DM Sans, sans-serif'
            }}
          >
            {agent.name}
          </span>
        </div>
        <span 
          className="text-xs uppercase"
          style={{ 
            color: '#AAA',
            fontFamily: 'DM Sans, sans-serif'
          }}
        >
          {agent.status}
        </span>
      </div>

      {/* Last Action */}
      {agent.lastAction && (
        <div 
          className="text-xs mb-2"
          style={{ 
            color: '#666',
            fontFamily: 'DM Sans, sans-serif'
          }}
        >
          {formatTimestamp(agent.lastAction)}
        </div>
      )}

      {/* Event Log */}
      {agent.events.length > 0 && (
        <div className="space-y-1">
          {visibleEvents.map((event, idx) => (
            <div 
              key={idx}
              className="text-xs p-1 rounded"
              style={{ 
                backgroundColor: '#1A1A1A',
                fontFamily: 'monospace',
                color: '#999'
              }}
            >
              <span style={{ color: '#666' }}>{formatTimestamp(event.timestamp)}</span>
              <span className="ml-2">{event.action}</span>
            </div>
          ))}
          
          {hasMoreEvents && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-xs mt-1 flex items-center gap-1"
              style={{ 
                color: '#F5C518',
                fontFamily: 'DM Sans, sans-serif'
              }}
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="w-3 h-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="w-3 h-3" />
                  Show {agent.events.length - 3} more events
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentSidebar({ agents, isResponding = false }: AgentSidebarProps) {
  return (
    <div 
      className="w-full h-full overflow-y-auto p-4"
      style={{ 
        backgroundColor: '#1A1A1A',
        borderLeft: '1px solid #F5C518'
      }}
    >
      <h3 
        className="text-sm font-bold mb-4 uppercase"
        style={{ 
          color: '#F5C518',
          fontFamily: 'DM Sans, sans-serif'
        }}
      >
        Agent Orchestration
      </h3>

      {/* Typing Indicator */}
      {isResponding && (
        <div 
          className="mb-4 p-3 rounded flex items-center gap-2"
          style={{ 
            backgroundColor: '#2A2A2A',
            borderLeft: '4px solid #F5C518'
          }}
        >
          <Loader2 className="w-4 h-4 animate-spin" style={{ color: '#4C6EF5' }} />
          <span 
            className="text-sm"
            style={{ 
              color: '#FFF',
              fontFamily: 'DM Sans, sans-serif'
            }}
          >
            Master Agent is responding...
          </span>
        </div>
      )}

      {/* Agent Cards */}
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
