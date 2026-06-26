import { useState, useEffect, useRef } from "react";
import { Paperclip, Mic, Send, Check, CheckCheck } from "lucide-react";
import { ENDPOINTS } from "../config";
import SequentialEligibilityForm from "./SequentialEligibilityForm";

interface Message {
  id: string;
  content: string;
  type: 'user' | 'assistant';
  timestamp: Date;
  status?: 'sent' | 'delivered' | 'read';
  attachment?: {
    name: string;
    type: string;
  };
}

// Simplified Message Component
const SimpleMessage = ({ message }: { message: Message }) => {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-IN', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    });
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'sent':
        return <Check className="w-4 h-4" />;
      case 'delivered':
        return <CheckCheck className="w-4 h-4" />;
      case 'read':
        return <CheckCheck className="w-4 h-4 text-blue-400" />;
      default:
        return null;
    }
  };

  const isUser = message.type === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? 'order-2' : 'order-1'}`}>
        {/* Message Bubble */}
        <div
          className="relative px-4 py-3 rounded-lg"
          style={{
            backgroundColor: isUser ? '#F5C518' : '#2A2A2A',
            color: isUser ? '#000000' : '#FFFFFF',
            borderLeft: isUser ? 'none' : '4px solid #F5C518',
            borderRadius: '8px',
            fontFamily: 'DM Sans, sans-serif',
            fontSize: '14px'
          }}
        >
          {/* Attachment */}
          {message.attachment && (
            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/20">
              <div className="w-8 h-8 bg-white/20 rounded flex items-center justify-center">
                <Paperclip className="w-4 h-4 text-white" />
              </div>
              <span className="text-sm">{message.attachment.name}</span>
            </div>
          )}
          
          {/* Message Content */}
          <p className="whitespace-pre-wrap break-words leading-relaxed">
            {message.content}
          </p>
        </div>
        
        {/* Timestamp and Status */}
        <div className={`flex items-center gap-1 mt-1 text-xs text-[#8696a0] ${isUser ? 'justify-end' : 'justify-start'}`}>
          <span>{formatTime(message.timestamp)}</span>
          {isUser && getStatusIcon(message.status)}
        </div>
      </div>
    </div>
  );
};

// Simplified Input Component
const SimpleInput = ({ onSendMessage, disabled }: { onSendMessage: (message: string, file?: File) => void, disabled?: boolean }) => {
  const [message, setMessage] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (message.trim() && !disabled) {
      onSendMessage(message.trim());
      setMessage("");
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && !disabled) {
      onSendMessage("", file);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleMicClick = () => {
    if (disabled) return;
    
    if (isRecording) {
      setIsRecording(false);
      onSendMessage("Voice message (simulated)");
    } else {
      setIsRecording(true);
    }
  };

  return (
    <>
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          className="text-[#8696a0] hover:text-white p-2 rounded-full transition-colors"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={20} />
        </button>

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept="image/*,.pdf,.doc,.docx"
          onChange={handleFileSelect}
          disabled={disabled}
        />

        <div className="flex-1 relative">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type a message"
            className="w-full bg-[#2a3942] text-white placeholder-[#8696a0] rounded-full px-4 py-2 pr-12 focus:outline-none focus:ring-1 focus:ring-[#00a884] disabled:opacity-50"
            disabled={disabled}
          />
        </div>

        <button
          type={message.trim() ? "submit" : "button"}
          onClick={!message.trim() ? handleMicClick : undefined}
          className={`
            p-2 rounded-full transition-all
            ${message.trim() 
              ? 'bg-[#00a884] text-white hover:bg-[#008069]' 
              : isRecording 
                ? 'bg-red-500 text-white animate-pulse' 
                : 'text-[#8696a0] hover:text-white'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
          `}
          disabled={disabled}
        >
          {message.trim() ? (
            <Send size={20} />
          ) : (
            <Mic size={20} />
          )}
        </button>
      </form>

      {isRecording && (
        <div className="absolute bottom-full left-4 right-4 mb-2 bg-red-500 text-white px-3 py-1 rounded-full text-xs flex items-center gap-2">
          <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
          Recording... Tap to stop
        </div>
      )}
    </>
  );
};

export const WhatsAppChat = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      content: 'Welcome to LoanEase. I am your Loan Assistant, here to guide you through a streamlined personal loan application. Please provide the following information to proceed:\n\nFirst, what is your full legal name as it appears on your identity documents?',
      type: 'assistant',
      timestamp: new Date(),
      status: 'read'
    }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const [sessionId] = useState(() => `WA-${Date.now()}`);
  const [showSequentialForm, setShowSequentialForm] = useState(true);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const toAsciiDigits = (value: string) =>
    value.replace(/[०-९]/g, (digit) => ({
      "०": "0",
      "१": "1",
      "२": "2",
      "३": "3",
      "४": "4",
      "५": "5",
      "६": "6",
      "७": "7",
      "८": "8",
      "९": "9",
    }[digit] ?? digit));

  const normalizePan = (value: string) => toAsciiDigits(value).replace(/\s+/g, "").toUpperCase();

  const isValidPan = (value: string) => /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(value);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const handleProceedToKYC = (event: CustomEvent) => {
      const { formData, eligibilityResult } = event.detail;
      
      // Hide the form and show chat
      setShowSequentialForm(false);
      
      // Add a message with the eligibility results
      const eligibilityMessage: Message = {
        id: (Date.now()).toString(),
        content: `Based on the information provided, here is your quick eligibility preview:\n\nELIGIBILITY ASSESSMENT\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nApplicant Name: ${formData.name}\nMonthly Gross Income: ₹${formData.monthly_income?.toLocaleString('en-IN')}\nDesired Loan Amount: ₹${formData.loan_amount?.toLocaleString('en-IN')}\nProposed Tenure: 60 months\nEstimated EMI: ₹${eligibilityResult.estimated_emi.toLocaleString('en-IN')}\nEMI to Income Ratio: ${(eligibilityResult.dti_ratio * 100).toFixed(1)}%\nEligibility Status: ${eligibilityResult.eligibility_status}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nThis is a preliminary assessment based on income alone. Your final eligibility depends on credit verification, identity authentication, and document validation.\n\nWould you like to proceed to KYC (Know Your Customer) verification?`,
        type: 'assistant',
        timestamp: new Date(),
        status: 'delivered'
      };
      
      setMessages(prev => [...prev, eligibilityMessage]);
    };

    window.addEventListener('proceedToKYC', handleProceedToKYC as EventListener);
    
    return () => {
      window.removeEventListener('proceedToKYC', handleProceedToKYC as EventListener);
    };
  }, []);

  const handleSendMessage = async (content: string, attachment?: File) => {
    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      content,
      type: 'user',
      timestamp: new Date(),
      status: 'sent',
      ...(attachment && {
        attachment: {
          name: attachment.name,
          type: attachment.type
        }
      })
    };

    setMessages(prev => [...prev, userMessage]);

    // Show typing indicator
    setIsTyping(true);

    try {
      if (attachment) {
        const formData = new FormData();
        formData.append("document", attachment);
        formData.append("session_id", sessionId);
        formData.append("language", "en");

        const panResponse = await fetch(ENDPOINTS.kyc_pan, {
          method: "POST",
          body: formData,
        });

        if (panResponse.ok) {
          const panData = await panResponse.json();
          const extractedPanCandidate = normalizePan(panData?.extracted_fields?.pan_number || "");
          const extractedPan = isValidPan(extractedPanCandidate)
            ? extractedPanCandidate
            : (panData?.extracted_fields?.pan_number || "");

          if (extractedPan) {
            const extractedName = panData?.extracted_fields?.name || "";
            const extractedDob = panData?.extracted_fields?.date_of_birth || "";
            const ocrMessage: Message = {
              id: (Date.now() + 2).toString(),
              content: `PAN OCR detected:\nPAN: ${extractedPan}${extractedName ? `\nName: ${extractedName}` : ""}${extractedDob ? `\nDOB: ${extractedDob}` : ""}`,
              type: 'assistant',
              timestamp: new Date(),
              status: 'delivered'
            };
            setMessages(prev => [...prev, ocrMessage]);
          }
        }
      }

      // Send to backend with channel parameter
      const formData = new FormData();
      formData.append('message', content);
      formData.append('session_id', sessionId);
      formData.append('channel', 'whatsapp');
      
      if (attachment) {
        formData.append('file', attachment);
      }

      const response = await fetch(`http://localhost:8000/chat`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      // Add assistant response
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: data.content || data.message || 'Sorry, I could not process that.',
        type: 'assistant',
        timestamp: new Date(),
        status: 'delivered'
      };

      setMessages(prev => [...prev, assistantMessage]);
      
      // Update user message status to delivered then read
      setTimeout(() => {
        setMessages(prev => prev.map(msg => 
          msg.id === userMessage.id ? { ...msg, status: 'delivered' } : msg
        ));
      }, 500);

      setTimeout(() => {
        setMessages(prev => prev.map(msg => 
          msg.id === userMessage.id ? { ...msg, status: 'read' } : msg
        ));
      }, 1000);

    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add error message
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: 'Sorry, I had trouble processing that. Please try again.',
        type: 'assistant',
        timestamp: new Date(),
        status: 'delivered'
      };
      
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Sequential Form Container */}
      {showSequentialForm && (
        <div className="flex-1 overflow-y-auto px-4 py-4 flex items-center justify-center">
          <SequentialEligibilityForm />
        </div>
      )}

      {/* Messages Container */}
      {!showSequentialForm && (
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
          {messages.map((message) => (
            <SimpleMessage
              key={message.id}
              message={message}
            />
          ))}
          
          {/* Typing Indicator */}
          {isTyping && (
            <div className="flex items-start gap-2">
              <div className="bg-[#1f2c34] rounded-2xl rounded-tl-none px-4 py-2 max-w-[70%]">
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 bg-[#8696a0] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-[#8696a0] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-[#8696a0] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input Area */}
      {!showSequentialForm && (
        <div className="border-t border-[#2a3942] px-4 py-2">
          <SimpleInput
            onSendMessage={handleSendMessage}
            disabled={isTyping}
          />
        </div>
      )}
    </div>
  );
};
