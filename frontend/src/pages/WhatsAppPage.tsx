import { useEffect, useRef, useState } from "react";
import { ArrowLeft, MoreVertical, Send } from "lucide-react";
import { WhatsAppChat } from "@/components";
import PipelineTracker, { type PipelineStage, type StageStatus } from "../components/PipelineTracker";
import AgentSidebar, { type AgentType, type AgentStatus } from "../components/AgentSidebar";
import { useNavigate } from "react-router-dom";

const WhatsAppPage = () => {
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showNewMessageIndicator, setShowNewMessageIndicator] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [showAgentSidebar, setShowAgentSidebar] = useState(false);
  const [sessionId] = useState(() => `WA-${Date.now()}`);

  // Pipeline stages state
  const [pipelineStages, setPipelineStages] = useState([
    { id: 'kyc' as PipelineStage, label: 'KYC', status: 'pending' as StageStatus },
    { id: 'credit' as PipelineStage, label: 'Credit', status: 'pending' as StageStatus },
    { id: 'offer' as PipelineStage, label: 'Offer', status: 'pending' as StageStatus },
    { id: 'negotiation' as PipelineStage, label: 'Negotiation', status: 'pending' as StageStatus },
    { id: 'sanction' as PipelineStage, label: 'Sanction', status: 'pending' as StageStatus }
  ]);

  const [currentStage, setCurrentStage] = useState<PipelineStage>('kyc');

  // Agent status state
  const [agents, setAgents] = useState([
    {
      id: 'master' as AgentType,
      name: 'Master Agent',
      status: 'idle' as AgentStatus,
      color: '#F5C518',
      events: []
    },
    {
      id: 'kyc' as AgentType,
      name: 'KYC Agent',
      status: 'idle' as AgentStatus,
      color: '#51CF66',
      events: []
    },
    {
      id: 'credit' as AgentType,
      name: 'Credit Agent',
      status: 'idle' as AgentStatus,
      color: '#4C6EF5',
      events: []
    },
    {
      id: 'negotiation' as AgentType,
      name: 'Negotiation Agent',
      status: 'idle' as AgentStatus,
      color: '#FF922B',
      events: []
    },
    {
      id: 'blockchain' as AgentType,
      name: 'Blockchain Agent',
      status: 'idle' as AgentStatus,
      color: '#A78BFA',
      events: []
    }
  ]);

  const [isResponding, setIsResponding] = useState(false);

  // Agent status update functions with critical logic
  const updateAgentStatus = (agentId: AgentType, status: AgentStatus, action?: string) => {
    setAgents(prev => prev.map(agent => {
      if (agent.id === agentId) {
        const updatedAgent = { ...agent, status, lastAction: new Date().toISOString() };
        
        // Add event to log
        if (action) {
          updatedAgent.events = [
            { timestamp: new Date().toISOString(), action },
            ...agent.events
          ].slice(0, 10); // Keep only last 10 events
        }
        
        return updatedAgent;
      }
      return agent;
    }));
  };

  const updatePipelineStage = (stageId: PipelineStage, status: StageStatus) => {
    setPipelineStages(prev => prev.map(stage => {
      if (stage.id === stageId) {
        return { ...stage, status };
      }
      return stage;
    }));
    
    if (status === 'in_progress') {
      setCurrentStage(stageId);
    }
  };

  // Critical agent status logic
  const handleKYCStatusUpdate = (event: string) => {
    switch (event) {
      case 'OTP_SENT':
        updateAgentStatus('kyc', 'waiting', 'OTP sent to mobile');
        break;
      case 'OTP_VERIFIED':
        updateAgentStatus('kyc', 'completed', 'OTP verified successfully');
        updatePipelineStage('kyc', 'completed');
        updatePipelineStage('credit', 'in_progress');
        break;
      case 'OTP_FAILED':
        updateAgentStatus('kyc', 'failed', 'OTP verification failed');
        break;
      default:
        updateAgentStatus('kyc', 'processing', event);
    }
  };

  const handleCreditStatusUpdate = (event: string) => {
    switch (event) {
      case 'SCORE_CALCULATED':
        updateAgentStatus('credit', 'processing', 'Credit score calculated');
        break;
      case 'OFFER_GENERATED':
        updateAgentStatus('credit', 'completed', 'Offer generated successfully');
        updatePipelineStage('credit', 'completed');
        updatePipelineStage('offer', 'completed');
        updatePipelineStage('negotiation', 'in_progress');
        break;
      case 'CREDIT_FAILED':
        updateAgentStatus('credit', 'failed', 'Credit assessment failed');
        break;
      default:
        updateAgentStatus('credit', 'processing', event);
    }
  };

  const handleNegotiationStatusUpdate = (event: string) => {
    switch (event) {
      case 'NEGOTIATION_STARTED':
        updateAgentStatus('negotiation', 'processing', 'Negotiation started');
        break;
      case 'ROUND_COMPLETED':
        updateAgentStatus('negotiation', 'processing', 'Negotiation round completed');
        break;
      case 'ACCEPTED':
        updateAgentStatus('negotiation', 'completed', 'Negotiation accepted');
        updatePipelineStage('negotiation', 'completed');
        updatePipelineStage('sanction', 'in_progress');
        break;
      case 'REJECTED':
        updateAgentStatus('negotiation', 'failed', 'Negotiation rejected');
        break;
      default:
        updateAgentStatus('negotiation', 'processing', event);
    }
  };

  const handleBlockchainStatusUpdate = (event: string) => {
    switch (event) {
      case 'SANCTION_GENERATED':
        updateAgentStatus('blockchain', 'processing', 'Sanction letter generated');
        break;
      case 'BLOCKCHAIN_RECORDED':
        updateAgentStatus('blockchain', 'completed', 'Blockchain transaction recorded');
        updatePipelineStage('sanction', 'completed');
        break;
      case 'BLOCKCHAIN_FAILED':
        updateAgentStatus('blockchain', 'failed', 'Blockchain recording failed');
        break;
      default:
        updateAgentStatus('blockchain', 'processing', event);
    }
  };

  const handleMasterAgentStatus = (status: AgentStatus, action: string) => {
    updateAgentStatus('master', status, action);
    setIsResponding(status === 'processing');
  };

  // Detect mobile screen size
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const bottomThreshold = 50;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < bottomThreshold);
  };

  useEffect(() => {
    scrollToBottom();
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    // Auto-expand textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  };

  const handleSubmit = async () => {
    if (!inputValue.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setIsResponding(true);
    
    // Simulate sending message
    setInputValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    // Simulate response delay
    setTimeout(() => {
      setIsSubmitting(false);
      setIsResponding(false);
    }, 2000);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = textareaRef.current?.selectionStart || 0;
      const end = textareaRef.current?.selectionEnd || 0;
      const newValue = inputValue.substring(0, start) + '\t' + inputValue.substring(end);
      setInputValue(newValue);
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + 1;
        }
      }, 0);
    }
  };

  return (
    <div 
      className="w-full h-screen overflow-hidden"
      style={{ 
        display: 'grid',
        gridTemplateRows: isMobile ? '60px 80px 1fr 100px' : '60px 120px 1fr 100px',
        gridTemplateColumns: isMobile ? '1fr' : '60% 40%',
        gap: 0,
        backgroundColor: '#141414'
      }}
    >
      {/* Header */}
      <div 
        className="px-4 py-3 flex items-center justify-between"
        style={{ 
          gridRow: 1,
          gridColumn: isMobile ? 1 : '1 / 3',
          backgroundColor: '#1f2c34',
          borderBottom: '1px solid #333'
        }}
      >
        <div className="flex items-center gap-3">
          <button 
            onClick={() => navigate('/')}
            className="text-white hover:bg-white/10 p-2 rounded-full transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          
          <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ backgroundColor: '#F5C518' }}>
            <span className="text-black font-bold text-lg">₹</span>
          </div>
          
          <div className="flex-1">
            <h1 className="text-white font-semibold">LoanEase Loan Assistant</h1>
            <p className="text-[#8696a0] text-xs">Available</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {!isMobile && (
            <button 
              onClick={() => setShowAgentSidebar(!showAgentSidebar)}
              className="text-white hover:bg-white/10 p-2 rounded-full transition-colors"
            >
              <MoreVertical size={20} />
            </button>
          )}
          {isMobile && (
            <button 
              onClick={() => setShowAgentSidebar(!showAgentSidebar)}
              className="text-white hover:bg-white/10 p-2 rounded-full transition-colors"
              style={{ backgroundColor: showAgentSidebar ? '#F5C518' : 'transparent' }}
            >
              <MoreVertical size={20} />
            </button>
          )}
        </div>
      </div>

      {/* Pipeline Tracker */}
      <div style={{ gridRow: 2, gridColumn: isMobile ? 1 : '1 / 3' }}>
        <PipelineTracker 
          stages={pipelineStages} 
          currentStage={currentStage}
          sessionId={sessionId}
          onStatusUpdate={({ stage, data }) => {
            if (data.error) {
              // Show error in agent sidebar
              const agentMap: Record<string, AgentType> = {
                'KYC': 'kyc',
                'CREDIT_ASSESSMENT': 'credit',
                'NEGOTIATION': 'negotiation',
                'BLOCKCHAIN_SANCTION': 'blockchain'
              };
              const agentId = agentMap[stage];
              if (agentId) {
                updateAgentStatus(agentId, 'failed', data.error);
              }
            }
          }}
        />
      </div>

      {/* Conversation Area */}
      <div 
        ref={messagesEndRef}
        className="px-4 py-4 overflow-y-auto"
        onScroll={handleScroll}
        style={{ 
          gridRow: 3,
          gridColumn: isMobile ? 1 : 1,
          scrollBehavior: 'smooth'
        }}
      >
        <WhatsAppChat />
        
        {/* New Message Indicator */}
        {showNewMessageIndicator && !isAtBottom && (
          <div 
            className="fixed bottom-24 left-1/2 transform -translate-x-1/2 px-4 py-2 rounded-full cursor-pointer"
            style={{ 
              backgroundColor: '#F5C518',
              color: '#000000',
              fontFamily: 'DM Sans, sans-serif',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
            onClick={scrollToBottom}
          >
            New message
          </div>
        )}
      </div>

      {/* Agent Sidebar - Hidden on mobile by default */}
      {!isMobile && (
        <div style={{ gridRow: '1 / 4', gridColumn: 2 }}>
          <AgentSidebar agents={agents} isResponding={isResponding} />
        </div>
      )}

      {/* Mobile Agent Sidebar Modal */}
      {isMobile && showAgentSidebar && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.8)' }}
          onClick={() => setShowAgentSidebar(false)}
        >
          <div 
            className="w-full max-w-md max-h-[80vh] overflow-y-auto rounded-lg p-4"
            style={{ backgroundColor: '#1A1A1A' }}
            onClick={(e) => e.stopPropagation()}
          >
            <AgentSidebar agents={agents} isResponding={isResponding} />
          </div>
        </div>
      )}

      {/* Input Field */}
      <div 
        className="px-6 py-4 flex items-center gap-3"
        style={{ 
          gridRow: 4,
          gridColumn: isMobile ? 1 : 1,
          backgroundColor: 'rgba(20, 20, 20, 0.95)',
          borderTop: '1px solid #444'
        }}
      >
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type your response or ask a question..."
            className="w-full resize-none rounded"
            style={{
              backgroundColor: '#2A2A2A',
              color: '#FFFFFF',
              border: '1px solid #666',
              borderRadius: '8px',
              padding: '12px 14px',
              fontFamily: 'DM Sans, sans-serif',
              fontSize: '16px',
              minHeight: '44px',
              maxHeight: '120px',
              outline: 'none'
            }}
            onFocus={(e) => e.target.style.borderColor = '#F5C518'}
            onBlur={(e) => e.target.style.borderColor = '#666'}
          />
        </div>
        
        <button
          onClick={handleSubmit}
          disabled={!inputValue.trim() || isSubmitting}
          className="w-11 h-11 rounded flex items-center justify-center transition-all"
          style={{
            backgroundColor: '#F5C518',
            color: '#000000',
            opacity: (!inputValue.trim() || isSubmitting) ? 0.5 : 1,
            cursor: (!inputValue.trim() || isSubmitting) ? 'not-allowed' : 'pointer'
          }}
          onMouseEnter={(e) => {
            if (inputValue.trim() && !isSubmitting) {
              e.currentTarget.style.filter = 'brightness(110%)';
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.filter = 'brightness(100%)';
          }}
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default WhatsAppPage;
