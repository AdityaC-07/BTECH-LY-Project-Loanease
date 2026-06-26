import React, { useEffect, useState } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { API_BASE_URL } from '../config';

export type PipelineStage = 'KYC' | 'CREDIT_ASSESSMENT' | 'LOAN_OFFER' | 'NEGOTIATION' | 'BLOCKCHAIN_SANCTION';

export interface StageStatusData {
  state: string;
  completed: boolean;
  current_stage?: boolean;
  timestamp_completed?: string;
  timestamp_started?: string;
  error?: string;
}

export type PipelineStateMap = Record<string, StageStatusData>;

interface PipelineTrackerProps {
  sessionId?: string;
  onStatusUpdate?: (status: { stage: PipelineStage; data: StageStatusData }) => void;
  // Fallback props to maintain backward compatibility if sessionId is not ready
  stages?: any[];
  currentStage?: string;
}

const STAGE_CONFIG = [
  { id: 'KYC' as PipelineStage, label: 'KYC', abbr: 'KYC' },
  { id: 'CREDIT_ASSESSMENT' as PipelineStage, label: 'CREDIT CHECK', abbr: 'CREDIT' },
  { id: 'LOAN_OFFER' as PipelineStage, label: 'OFFER', abbr: 'OFFER' },
  { id: 'NEGOTIATION' as PipelineStage, label: 'NEGOTIATION', abbr: 'NEG.' },
  { id: 'BLOCKCHAIN_SANCTION' as PipelineStage, label: 'SANCTION', abbr: 'SANCT.' },
];

export default function PipelineTracker({ sessionId, onStatusUpdate, stages }: PipelineTrackerProps) {
  const [pipelineState, setPipelineState] = useState<PipelineStateMap | null>(null);
  const [hoveredStage, setHoveredStage] = useState<PipelineStage | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    // 1. Fetch initial state on mount or refresh
    fetch(`${API_BASE_URL}/kyc/status/${sessionId}`)
      .then(res => {
        if (!res.ok) throw new Error('Status fetch failed');
        return res.json();
      })
      .then(data => {
        if (data && data.pipeline_stages) {
          setPipelineState(data.pipeline_stages);
        }
      })
      .catch(err => console.error("Failed to fetch initial pipeline status:", err));

    // 2. Subscribe to WebSocket for real-time updates
    const wsUrl = API_BASE_URL.replace(/^http/, 'ws') + `/events/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data && data.pipeline_stages) {
          setPipelineState(data.pipeline_stages);
          
          // Notify parent of updates, especially errors
          if (onStatusUpdate) {
            Object.entries(data.pipeline_stages).forEach(([stage, stageData]: [string, any]) => {
              if (stageData.error || (stageData.state && stageData.state.includes('FAILED'))) {
                onStatusUpdate({ stage: stage as PipelineStage, data: stageData });
              }
            });
          }
        }
      } catch (err) {
        console.error("Failed to parse websocket message", err);
      }
    };

    return () => {
      ws.close();
    };
  }, [sessionId, onStatusUpdate]);

  const getStageUIState = (stageId: PipelineStage) => {
    // Priority 1: WebSocket / API State
    if (pipelineState && pipelineState[stageId]) {
      const stageData = pipelineState[stageId];
      if (stageData.error || (stageData.state && stageData.state.includes('FAILED'))) return 'FAILED';
      if (stageData.completed) return 'COMPLETED';
      if (stageData.current_stage && !stageData.completed) return 'ACTIVE';
      return 'PENDING';
    }
    
    // Priority 2: Fallback to old props structure if used
    if (stages && !pipelineState) {
      const propStage = stages.find(s => {
        if (stageId === 'KYC') return s.id === 'kyc';
        if (stageId === 'CREDIT_ASSESSMENT') return s.id === 'credit';
        if (stageId === 'LOAN_OFFER') return s.id === 'offer';
        if (stageId === 'NEGOTIATION') return s.id === 'negotiation';
        if (stageId === 'BLOCKCHAIN_SANCTION') return s.id === 'sanction';
        return false;
      });
      if (propStage) {
        if (propStage.status === 'completed') return 'COMPLETED';
        if (propStage.status === 'in_progress') return 'ACTIVE';
        if (propStage.status === 'failed') return 'FAILED';
      }
    }
    
    return 'PENDING';
  };

  const getStyleForState = (state: string) => {
    switch (state) {
      case 'COMPLETED':
        return { bg: '#51CF66', border: '#2E8B57', color: '#FFFFFF' };
      case 'ACTIVE':
        return { bg: '#F5C518', border: '#FFD700', color: '#000000' };
      case 'FAILED':
        return { bg: '#FF6B6B', border: '#C92A2A', color: '#FFFFFF' };
      case 'PENDING':
      default:
        return { bg: '#444444', border: '#666666', color: '#FFFFFF' };
    }
  };

  const renderIcon = (state: string, index: number) => {
    switch (state) {
      case 'COMPLETED':
        return (
          <Check 
            className="w-5 h-5 transition-transform duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]" 
            style={{ animation: 'scaleIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards' }} 
          />
        );
      case 'ACTIVE':
        return <Loader2 className="w-5 h-5 animate-[spin_2s_linear_infinite]" />;
      case 'FAILED':
        return <X className="w-5 h-5" />;
      case 'PENDING':
      default:
        return <span className="font-bold text-sm">{index + 1}</span>;
    }
  };

  // Build ARIA labels
  const completedCount = STAGE_CONFIG.filter(s => getStageUIState(s.id) === 'COMPLETED').length;
  const ariaLabel = `Loan processing: ${completedCount} of 5 stages complete`;

  return (
    <>
      <style>
        {`
          @keyframes scaleIn {
            from { transform: scale(0.5); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
          }
        `}
      </style>
      <div 
        className="w-full flex justify-center items-center overflow-x-auto overflow-y-visible"
        style={{ backgroundColor: 'transparent', minHeight: '80px', margin: '12px 0', padding: '8px 16px' }}
        role="progressbar"
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={5}
        aria-valuenow={completedCount}
      >
        {/* Screen reader live region */}
        <div aria-live="polite" className="sr-only">
          {STAGE_CONFIG.map(s => {
            const state = getStageUIState(s.id);
            const stateText = state === 'COMPLETED' ? 'complete' : state === 'ACTIVE' ? 'in progress' : state === 'FAILED' ? 'failed' : 'pending';
            return `${s.label} verification: ${stateText}. `;
          }).join('')}
        </div>

        <ol className="flex items-center justify-between w-full max-w-5xl mx-auto px-2 min-w-[max-content] md:min-w-0">
          {STAGE_CONFIG.map((stage, index) => {
            const uiState = getStageUIState(stage.id);
            const styles = getStyleForState(uiState);
            const isLast = index === STAGE_CONFIG.length - 1;
            
            return (
              <li key={stage.id} className="flex items-center relative flex-1 last:flex-none group">
                {/* Stage Container */}
                <div 
                  className="flex flex-col items-center relative z-10 shrink-0 cursor-pointer"
                  onMouseEnter={() => setHoveredStage(stage.id)}
                  onMouseLeave={() => setHoveredStage(null)}
                >
                  {/* Circle Indicator */}
                  <div
                    className="w-8 h-8 md:w-9 md:h-9 lg:w-10 lg:h-10 rounded-full flex items-center justify-center transition-colors duration-300 ease-in-out"
                    style={{
                      backgroundColor: styles.bg,
                      border: `3px solid ${styles.border}`,
                      color: styles.color,
                    }}
                    tabIndex={0}
                  >
                    {renderIcon(uiState, index)}
                  </div>
                  
                  {/* Stage Label */}
                  <span 
                    className="absolute top-full mt-2 text-[10px] md:text-xs font-bold whitespace-nowrap tracking-wide"
                    style={{ 
                      color: uiState === 'PENDING' ? '#888' : '#FFF',
                      fontFamily: 'DM Sans, sans-serif'
                    }}
                  >
                    <span className="hidden md:inline">{stage.label}</span>
                    <span className="inline md:hidden">{stage.abbr}</span>
                  </span>

                  {/* Tooltip on Hover */}
                  {hoveredStage === stage.id && pipelineState && pipelineState[stage.id] && (
                    <div className="absolute bottom-full mb-3 left-1/2 transform -translate-x-1/2 bg-gray-900 border border-gray-700 text-white text-xs rounded-lg p-3 shadow-xl z-50 w-56 pointer-events-none transition-opacity duration-200">
                      <div className="font-bold mb-1 text-sm">{stage.label}</div>
                      <div className="text-gray-300 mb-1">State: <span className="text-white font-medium">{pipelineState[stage.id].state || uiState}</span></div>
                      {pipelineState[stage.id].timestamp_completed && (
                        <div className="text-gray-400 text-[10px] mb-1">
                          Completed: {new Date(pipelineState[stage.id].timestamp_completed!).toLocaleTimeString()}
                        </div>
                      )}
                      {pipelineState[stage.id].timestamp_started && !pipelineState[stage.id].completed && (
                        <div className="text-gray-400 text-[10px] mb-1">
                          Started: {new Date(pipelineState[stage.id].timestamp_started!).toLocaleTimeString()}
                        </div>
                      )}
                      {pipelineState[stage.id].error && (
                        <div className="text-red-400 mt-1 font-medium bg-red-900/30 p-1.5 rounded">
                          Error: {pipelineState[stage.id].error}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                
                {/* Connecting Line */}
                {!isLast && (
                  <div className="flex-1 h-[3px] mx-2 md:mx-4 lg:mx-8 shrink">
                    <div 
                      className="h-full w-full transition-colors duration-500 ease-in-out origin-left rounded-full"
                      style={{
                        background: uiState === 'COMPLETED' ? '#51CF66' : uiState === 'ACTIVE' ? '#F5C518' : '#444444',
                      }}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </>
  );
}
