import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChatMessage } from "./ChatMessage";
import { StepIndicator } from "./StepIndicator";
import { LoanCard } from "./LoanCard";
import { CreditScoreCard } from "./CreditScoreCard";
import { SanctionLetter } from "./SanctionLetter";
import { Send, ArrowLeft, MessageCircle } from "lucide-react";

const STEPS = [
  { id: "welcome", label: "Welcome" },
  { id: "kyc", label: "KYC" },
  { id: "credit", label: "Credit Score" },
  { id: "offers", label: "Loan Offers" },
  { id: "negotiation", label: "Negotiation" },
  { id: "sanction", label: "Sanction" },
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
      text: "Hello! I'm your Personal Loan Assistant. I'll help you find the perfect loan tailored to your needs. Let's get started!\n\nMay I have your full name as per your PAN card?",
      isBot: true,
    },
  ]);
  const [input, setInput] = useState("");
  const [currentStep, setCurrentStep] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const [showCreditScore, setShowCreditScore] = useState(false);
  const [showLoanOffers, setShowLoanOffers] = useState(false);
  const [showSanction, setShowSanction] = useState(false);
  const [userData, setUserData] = useState({
    name: "",
    pan: "",
    creditScore: 0,
    selectedLoan: { amount: 0, interest: 0, tenure: 0, emi: 0 },
  });
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const conversationStep = useRef(0);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, showCreditScore, showLoanOffers, showSanction]);

  const simulateBotResponse = (userMessage: string) => {
    setIsTyping(true);
    
    setTimeout(() => {
      setIsTyping(false);
      let botResponse = "";
      
      switch (conversationStep.current) {
        case 0:
          setUserData((prev) => ({ ...prev, name: userMessage }));
          botResponse = `Nice to meet you, ${userMessage}! 🙂\n\nFor KYC verification, please enter your PAN number:`;
          conversationStep.current = 1;
          setCurrentStep(1);
          break;
        case 1:
          setUserData((prev) => ({ ...prev, pan: userMessage.toUpperCase() }));
          botResponse = "Perfect! Let me verify your details and fetch your credit score...\n\n⏳ Please wait while I connect to the bureau...";
          conversationStep.current = 2;
          setCurrentStep(2);
          
          setTimeout(() => {
            const creditScore = Math.floor(Math.random() * (850 - 680) + 680);
            setUserData((prev) => ({ ...prev, creditScore }));
            setShowCreditScore(true);
            
            setTimeout(() => {
              if (creditScore >= 700) {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: prev.length + 1,
                    text: "Great news! Based on your credit profile, you're eligible for our premium loan offers. Here are personalized options for you:",
                    isBot: true,
                  },
                ]);
                setShowLoanOffers(true);
                setCurrentStep(3);
                conversationStep.current = 3;
              } else {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: prev.length + 1,
                    text: "I'm sorry, but your current credit score doesn't meet our minimum eligibility criteria (700+). I recommend improving your credit score and applying again in a few months.\n\nWould you like tips on improving your credit score?",
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
    setCurrentStep(4);
    
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
      setMessages((prev) => [
        ...prev,
        {
          id: prev.length + 1,
          text: "Excellent choice! I'm now processing your application...\n\n✅ KYC Verified\n✅ Credit Check Passed\n✅ Income Assessment Complete\n✅ Risk Analysis Done\n\n🎉 Congratulations! Your loan has been approved!",
          isBot: true,
        },
      ]);
      
      setCurrentStep(5);
      setTimeout(() => {
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
              <p className="text-xs text-accent">Online</p>
            </div>
          </div>
          <div className="w-10" />
        </div>
        <StepIndicator steps={STEPS} currentStep={currentStep} />
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
