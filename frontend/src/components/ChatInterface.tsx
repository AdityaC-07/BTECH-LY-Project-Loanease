import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChatMessage } from "./ChatMessage";
import { LoanCard } from "./LoanCard";
import { CreditScoreCard } from "./CreditScoreCard";
import { SanctionLetter } from "./SanctionLetter";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { Send, ArrowLeft, MessageCircle } from "lucide-react";

const AGENT_PIPELINE = [
  "Master Agent",
  "KYC Verification Agent",
  "Credit Underwriting Agent",
  "Loan Recommendation Engine",
  "Dynamic Negotiation Agent",
  "Blockchain Ledger",
];

interface Message {
  id: number;
  text: string;
  isBot: boolean;
}

interface ChatInterfaceProps {
  onClose: () => void;
}

export const ChatInterface = ({ onClose }: ChatInterfaceProps) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Hello. I am your Personal Loan Assistant. I will help you identify the most suitable loan offer and guide you through the journey.\n\nPlease share your full name as per your PAN card.",
      isBot: true,
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [showCreditScore, setShowCreditScore] = useState(false);
  const [showLoanOffers, setShowLoanOffers] = useState(false);
  const [showSanction, setShowSanction] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [activeAgent, setActiveAgent] = useState("Master Agent");
  const [userData, setUserData] = useState({
    name: "",
    pan: "",
    creditScore: 0,
    selectedLoan: { amount: 0, interest: 0, tenure: 0, emi: 0 },
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const conversationStep = useRef(0);
  const activeAgentIndex = AGENT_PIPELINE.indexOf(activeAgent);

  const activateAgent = (agentName: string, note: string) => {
    setActiveAgent(agentName);
    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text: `${agentName} activated.\n${note}`,
        isBot: true,
      },
    ]);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, showCreditScore, showLoanOffers, showSanction, showAnalytics]);

  const simulateBotResponse = (userMessage: string) => {
    setIsTyping(true);

    setTimeout(() => {
      setIsTyping(false);
      let botResponse = "";

      switch (conversationStep.current) {
        case 0:
          setUserData((prev) => ({ ...prev, name: userMessage }));
          activateAgent("KYC Verification Agent", "Validating identity inputs and verification details.");
          botResponse = `Thank you, ${userMessage}.\n\nFor KYC verification, please enter your PAN number.`;
          conversationStep.current = 1;
          break;
        case 1:
          setUserData((prev) => ({ ...prev, pan: userMessage.toUpperCase() }));
          activateAgent("Credit Underwriting Agent", "Evaluating eligibility based on credit and risk profile.");
          botResponse = "Your details are captured. I will now verify your profile and fetch your credit score.\n\nPlease wait while we process the bureau check.";
          conversationStep.current = 2;

          setTimeout(() => {
            const creditScore = Math.floor(Math.random() * (850 - 680) + 680);
            setUserData((prev) => ({ ...prev, creditScore }));
            setShowCreditScore(true);

            setTimeout(() => {
              if (creditScore >= 700) {
                setActiveAgent("Loan Recommendation Engine");
                setMessages((prev) => [
                  ...prev,
                  {
                    id: prev.length + 1,
                    text: "Loan Recommendation Engine activated.\nBuilding personalized loan options.\n\nBased on your credit profile, you are eligible for the following offers:",
                    isBot: true,
                  },
                ]);
                setShowLoanOffers(true);
                conversationStep.current = 3;
              } else {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: prev.length + 1,
                    text: "Your current credit score does not meet our minimum eligibility criteria (700+). We recommend improving your score and reapplying after some time.\n\nWould you like improvement tips?",
                    isBot: true,
                  },
                ]);
              }
            }, 1500);
          }, 2000);
          break;
        case 3:
          botResponse = "I see you're interested! Feel free to adjust the sliders to customize your loan terms. Once you're satisfied, click 'Select This Plan' to proceed.";
          break;
        default:
          botResponse = "Thank you for your message. Is there anything else I can help you with?";
      }

      if (botResponse) {
        setMessages((prev) => [
          ...prev,
          { id: prev.length + 1, text: botResponse, isBot: true },
        ]);
      }
    }, 1500);
  };

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage = input.trim();
    setMessages((prev) => [
      ...prev,
      { id: prev.length + 1, text: userMessage, isBot: false },
    ]);
    setInput("");
    simulateBotResponse(userMessage);
  };

  const handleLoanSelect = (interest: number, tenure: number, amount: number) => {
    const emi = Math.round(
      (amount * (interest / 1200) * Math.pow(1 + interest / 1200, tenure)) /
      (Math.pow(1 + interest / 1200, tenure) - 1)
    );

    setUserData((prev) => ({
      ...prev,
      selectedLoan: { amount, interest, tenure, emi },
    }));

    setShowLoanOffers(false);

    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text: `You selected: ₹${amount.toLocaleString('en-IN')} at ${interest}% for ${tenure} months.\n\nEMI: ₹${emi.toLocaleString('en-IN')}/month`,
        isBot: false,
      },
    ]);

    setIsTyping(true);
    setTimeout(() => {
      setIsTyping(false);
      setActiveAgent("Dynamic Negotiation Agent");
      setMessages((prev) => [
        ...prev,
        {
          id: prev.length + 1,
          text: "Dynamic Negotiation Agent activated.\nApplying negotiation policy and offer optimization.\n\nYour application is being processed.\n\nKYC Verified\nCredit Check Passed\nIncome Assessment Complete\nRisk Analysis Completed\n\nYour loan has been approved.",
          isBot: true,
        },
      ]);

      setTimeout(() => {
        setActiveAgent("Blockchain Ledger");
        setMessages((prev) => [
          ...prev,
          {
            id: prev.length + 1,
            text: "Blockchain Ledger activated.\nYour sanction details are being securely recorded with tamper-proof hash verification.",
            isBot: true,
          },
        ]);
        setShowSanction(true);
      }, 1000);
    }, 2500);
  };

  return (
    <div className="fixed inset-0 bg-background z-50 flex flex-col">
      {/* Header */}
      <div className="bg-card border-b border-border">
        <div className="flex items-center justify-between px-4 py-3">
          <Button variant="ghost" size="icon" onClick={onClose}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
              <MessageCircle className="w-4 h-4 text-primary-foreground" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Loan Assistant</h2>
              <p className="text-xs text-accent">Online • {activeAgent}</p>
            </div>
          </div>
          <div className="w-10" />
        </div>
        <div className="px-4 pb-3">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
            <div className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
              Agent Activation Timeline
            </div>
            <div className="flex items-center gap-2 overflow-x-auto">
              {AGENT_PIPELINE.map((agent, index) => {
                const isCompleted = index < activeAgentIndex;
                const isActive = index === activeAgentIndex;
                return (
                  <div key={agent} className="flex items-center gap-2">
                    <div
                      className={`h-7 min-w-7 rounded-full border text-[11px] flex items-center justify-center px-2 ${
                        isActive
                          ? "bg-yellow-400 text-black border-yellow-400"
                          : isCompleted
                            ? "bg-green-600 text-white border-green-600"
                            : "bg-background text-muted-foreground border-border"
                      }`}
                    >
                      {index + 1}
                    </div>
                    <div
                      className={`whitespace-nowrap text-xs ${
                        isActive
                          ? "text-yellow-300"
                          : isCompleted
                            ? "text-green-400"
                            : "text-muted-foreground"
                      }`}
                    >
                      {agent}
                    </div>
                    {index < AGENT_PIPELINE.length - 1 && (
                      <div
                        className={`h-[2px] w-8 ${
                          index < activeAgentIndex
                            ? "bg-green-500"
                            : "bg-border"
                        }`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message.text}
            isBot={message.isBot}
          />
        ))}

        {isTyping && <ChatMessage message="" isBot isTyping />}

        {showCreditScore && (
          <div className="py-4">
            <CreditScoreCard score={userData.creditScore} />
          </div>
        )}

        {showLoanOffers && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-4">
            <LoanCard
              amount={200000}
              minInterest={10.5}
              maxInterest={14}
              minTenure={12}
              maxTenure={60}
              onSelect={(interest, tenure) => handleLoanSelect(interest, tenure, 200000)}
            />
            <LoanCard
              amount={500000}
              minInterest={10}
              maxInterest={13.5}
              minTenure={12}
              maxTenure={72}
              isRecommended
              onSelect={(interest, tenure) => handleLoanSelect(interest, tenure, 500000)}
            />
            <LoanCard
              amount={1000000}
              minInterest={9.5}
              maxInterest={12.5}
              minTenure={12}
              maxTenure={84}
              onSelect={(interest, tenure) => handleLoanSelect(interest, tenure, 1000000)}
            />
          </div>
        )}

        {showSanction && (
          <div className="py-4">
            <SanctionLetter
              customerName={userData.name}
              loanAmount={userData.selectedLoan.amount}
              interestRate={userData.selectedLoan.interest}
              tenure={userData.selectedLoan.tenure}
              emi={userData.selectedLoan.emi}
              sanctionDate={new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
              referenceId={`LOAN${Date.now().toString().slice(-8)}`}
              blockchainHash={`0x${Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join('')}`}
              onViewAnalytics={() => setShowAnalytics(true)}
            />
          </div>
        )}

        {showAnalytics && (
          <div className="py-8 bg-background/50 rounded-xl border border-border/50 animate-slide-up">
            <AnalyticsDashboard
              customerName={userData.name}
              initialAmount={userData.selectedLoan.amount}
              initialInterest={userData.selectedLoan.interest}
              initialTenure={userData.selectedLoan.tenure}
            />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border bg-card">
        <div className="flex gap-2 max-w-4xl mx-auto">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            onKeyPress={(e) => e.key === "Enter" && handleSend()}
            className="flex-1"
            disabled={showLoanOffers || showSanction}
          />
          <Button
            variant="chat"
            size="icon"
            onClick={handleSend}
            disabled={!input.trim() || showLoanOffers || showSanction}
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};
