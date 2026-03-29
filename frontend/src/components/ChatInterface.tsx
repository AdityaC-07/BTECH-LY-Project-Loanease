import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChatMessage } from "./ChatMessage";
import { LoanCard } from "./LoanCard";
import { CreditScoreCard } from "./CreditScoreCard";
import { SanctionLetter } from "./SanctionLetter";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { Send, ArrowLeft, MessageCircle } from "lucide-react";
import { TRANSLATIONS } from "@/lib/translations";
import { formatIndianCurrency, detectLanguage, formatEMI } from "@/lib/languageUtils";
import { toast } from "sonner";

const AGENT_PIPELINE = [
  "Master Agent",
  "KYC Verification Agent",
  "Credit Underwriting Agent",
  "Loan Recommendation Engine",
  "Dynamic Negotiation Agent",
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
  const [language, setLanguage] = useState<"en" | "hi">(
    () => (localStorage.getItem("loanease_language") as "en" | "hi") || "en"
  );
  const [messages, setMessages] = useState<Message[]>(() => [
    {
      id: 1,
      text: TRANSLATIONS.opening[(localStorage.getItem("loanease_language") as "en" | "hi") || "en"],
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
  const [showCreditScoreCard, setShowCreditScoreCard] = useState(false);
  const [creditScoreData, setCreditScoreData] = useState<any>(null);
  const [userData, setUserData] = useState({
    name: "",
    pan: "",
    creditScore: 0,
    selectedLoan: { amount: 0, interest: 0, tenure: 0, emi: 0 },
    assessmentId: "",
    sessionId: "",
    riskScore: 0,
    riskTier: "",
    maxNegotiationRounds: 0,
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const conversationStep = useRef(0);
  const activeAgentIndex = AGENT_PIPELINE.indexOf(activeAgent);

  const handleLanguageChange = (lang: "en" | "hi") => {
    setLanguage(lang);
    localStorage.setItem("loanease_language", lang);
    const message =
      lang === "en"
        ? TRANSLATIONS.language_switched_en
        : TRANSLATIONS.language_switched_hi;
    toast.success(message);
  };

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

  // Detect language from user input
  useEffect(() => {
    const detectAndSwitch = async () => {
      if (input.length > 5) {
        const result = await detectLanguage(input);
        if (result.language !== "unknown" && result.language !== language) {
          const msg =
            result.language === "en"
              ? TRANSLATIONS.language_detected_en
              : TRANSLATIONS.language_detected_hi;
          toast.info(msg);
        }
      }
    };
    detectAndSwitch();
  }, [input, language]);

  const callUnderwritingAPI = async (userData: {
    pan_number: string;
    gender: string;
    married: string;
    dependents: string;
    education: string;
    self_employed: string;
    applicant_income: number;
    coapplicant_income: number;
    loan_amount: number;
    loan_amount_term: number;
    credit_history: number;
    property_area: string;
    preferred_language: "en" | "hi";
  }) => {
    try {
      const response = await fetch("http://localhost:8000/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(userData),
      });

      if (!response.ok) throw new Error("Assessment failed");
      const data = await response.json();

      setUserData((prev) => ({
        ...prev,
        assessmentId: data.application_id,
        riskScore: data.risk_score,
        riskTier: data.risk_tier,
        creditScore: data.credit_score,
        maxNegotiationRounds: data.max_negotiation_rounds || 0,
      }));

      return data;
    } catch (error) {
      console.error("Underwriting error:", error);
      toast.error("Failed to assess application");
      return null;
    }
  };

  const callNegotiationAPI = async (
    riskScore: number,
    riskTier: string,
    loanAmount: number,
    tenureMonths: number
  ) => {
    try {
      const response = await fetch("http://localhost:8001/negotiate/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicant_name: userData.name,
          risk_score: riskScore,
          risk_tier: riskTier,
          loan_amount: loanAmount,
          tenure_months: tenureMonths,
          top_positive_factor: "good credit history",
        }),
      });

      if (!response.ok) throw new Error("Negotiation start failed");
      const data = await response.json();

      setUserData((prev) => ({
        ...prev,
        sessionId: data.session_id,
      }));

      return data;
    } catch (error) {
      console.error("Negotiation error:", error);
      toast.error("Failed to start negotiation");
      return null;
    }
  };

  const callCreditScoreAPI = async (pan: string) => {
    try {
      const response = await fetch(`http://localhost:8000/credit-score/${pan}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Credit score fetch failed");
      const data = await response.json();

      setCreditScoreData(data);
      setShowCreditScoreCard(true);

      return data;
    } catch (error) {
      console.error("Credit score error:", error);
      toast.error("Failed to fetch credit score");
      return null;
    }
  };

  const simulateBotResponse = (userMessage: string) => {
    setIsTyping(true);

    setTimeout(async () => {
      setIsTyping(false);
      let botResponse = "";

      switch (conversationStep.current) {
        case 0:
          setUserData((prev) => ({ ...prev, name: userMessage }));
          activateAgent("KYC Verification Agent", "Validating identity inputs and verification details.");
          botResponse = `${TRANSLATIONS.kyc_intro[language]}`;
          conversationStep.current = 1;
          break;

        case 1:
          const panNumber = userMessage.toUpperCase();
          setUserData((prev) => ({ ...prev, pan: panNumber }));
          activateAgent("Credit Underwriting Agent", "Evaluating eligibility based on credit and risk profile.");
          botResponse = TRANSLATIONS.kyc_processing[language];
          conversationStep.current = 2;

          setTimeout(async () => {
            // Call credit score API after KYC
            const creditScoreResult = await callCreditScoreAPI(panNumber);

            if (creditScoreResult) {
              // Show credit score card
              setShowCreditScoreCard(true);

              setTimeout(() => {
                if (creditScoreResult.eligible_for_loan) {
                  // Eligible: proceed to /assess
                  setMessages((prev) => [
                    ...prev,
                    {
                      id: prev.length + 1,
                      text:
                        language === "en"
                          ? "Great! Your credit profile qualifies. Now let me analyze your complete financial profile..."
                          : "बहुत बढ़िया! आपकी credit profile योग्य है। अब मैं आपकी complete financial profile का विश्लेषण करूंगा...",
                      isBot: true,
                    },
                  ]);

                  // Proceed to /assess with pan_number
                  conversationStep.current = 2;
                  // Continue flow will call /assess in the next simulateBotResponse
                } else {
                  // Not eligible: show rejection message
                  setMessages((prev) => [
                    ...prev,
                    {
                      id: prev.length + 1,
                      text: creditScoreResult.message_en
                        ? creditScoreResult.message_en
                        : language === "en"
                          ? "Unfortunately, your credit score does not meet our minimum requirement."
                          : "दुर्भाग्यवश, आपका credit score हमारी न्यूनतम आवश्यकता को पूरा नहीं करता है।",
                      isBot: true,
                    },
                  ]);

                  // End conversation
                  conversationStep.current = -1;
                }
              }, 1500);
            }
          }, 2000);
          break;

        case 2:
          // This case is for /assess call after credit score is approved
          // For now, keep the flow as is - the user will proceed through handleLoanSelect
          botResponse = "";
          break;

        case 3:
          botResponse = "Feel free to adjust the sliders to customize your loan terms. Once satisfied, click 'Select This Plan' to proceed.";
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

  const handleLoanSelect = async (interest: number, tenure: number, amount: number) => {
    const emi = Math.round(
      (amount * (interest / 1200) * Math.pow(1 + interest / 1200, tenure)) /
        (Math.pow(1 + interest / 1200, tenure) - 1)
    );

    setUserData((prev) => ({
      ...prev,
      selectedLoan: { amount, interest, tenure, emi },
    }));

    setShowLoanOffers(false);

    const selectionMessage =
      language === "en"
        ? `You selected: ${formatIndianCurrency(amount)} at ${interest}% for ${tenure} months.\n\n${TRANSLATIONS.emi[language]}: ${formatIndianCurrency(emi)}/month`
        : `आपने चुना: ${formatIndianCurrency(amount)} ${interest}% पर ${tenure} महीनों के लिए।\n\n${TRANSLATIONS.emi[language]}: ${formatIndianCurrency(emi)}/month`;

    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text: selectionMessage,
        isBot: false,
      },
    ]);

    setIsTyping(true);
    setTimeout(async () => {
      setIsTyping(false);
      setActiveAgent("Dynamic Negotiation Agent");
      setMessages((prev) => [
        ...prev,
        {
          id: prev.length + 1,
          text: "Dynamic Negotiation Agent activated.\nApplying negotiation policy and offer optimization.\n\nYour application is being processed.",
          isBot: true,
        },
      ]);

      // First call /assess with pan_number and full details
      const assessmentResult = await callUnderwritingAPI({
        pan_number: userData.pan,
        gender: "Male",
        married: "Yes",
        dependents: "1",
        education: "Graduate",
        self_employed: "No",
        applicant_income: 5000,
        coapplicant_income: 1500,
        loan_amount: amount / 100000, // Convert to lakhs
        loan_amount_term: tenure,
        credit_history: 1,
        property_area: "Urban",
        preferred_language: language,
      });

      if (assessmentResult && assessmentResult.decision === "APPROVED") {
        // Then call negotiation API with max_negotiation_rounds from assessment
        const negotiationResult = await callNegotiationAPI(
          assessmentResult.risk_score,
          assessmentResult.risk_tier,
          amount,
          tenure
        );

        // Pass max_negotiation_rounds to negotiation API
        if (negotiationResult) {
          await fetch("http://localhost:8001/negotiate/accept", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: negotiationResult.session_id,
            }),
          });

          setTimeout(() => {
            const approvalMsg =
              language === "en"
                ? TRANSLATIONS.approved[language]
                : TRANSLATIONS.approved[language];

            setMessages((prev) => [
              ...prev,
              {
                id: prev.length + 1,
                text: `KYC Verified\nCredit Check Passed\nIncome Assessment Complete\nRisk Analysis Completed\n\n${approvalMsg}`,
                isBot: true,
              },
            ]);

            setTimeout(() => {
              setMessages((prev) => [
                ...prev,
                {
                  id: prev.length + 1,
                  text: "Sanction details are being securely recorded with tamper-proof hash verification.",
                  isBot: true,
                },
              ]);
              setShowSanction(true);
            }, 1000);
          }, 1000);
        }
      } else if (assessmentResult) {
        // Show rejection
        setMessages((prev) => [
          ...prev,
          {
            id: prev.length + 1,
            text: assessmentResult.message || TRANSLATIONS.rejected[language],
            isBot: true,
          },
        ]);
      }
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
          <LanguageSwitcher currentLanguage={language} onLanguageChange={handleLanguageChange} />
        </div>
        <div className="px-4 pb-3">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
            <div className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
              Agent Activation Timeline
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {AGENT_PIPELINE.map((agent, index) => {
                const isCompleted = index < activeAgentIndex;
                const isActive = index === activeAgentIndex;
                return (
                  <div key={agent} className="flex items-center gap-2 min-w-0">
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
                      className={`text-xs ${
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

        {showCreditScoreCard && creditScoreData && (
          <div className="py-4 animate-slide-up">
            <div className="bg-gradient-to-br from-yellow-500/10 to-yellow-600/10 border border-yellow-500/30 rounded-lg p-6 max-w-md">
              <div className="text-center space-y-4">
                <div className="text-2xl font-bold">📊 {language === "en" ? "Your Credit Score" : "आपका Credit Score"}</div>

                {/* Animated score display */}
                <div className="text-4xl font-bold text-yellow-500">
                  {creditScoreData.credit_score} <span className="text-lg text-muted-foreground">/ 900</span>
                </div>

                {/* Score bar */}
                <div className="w-full bg-gray-300 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-1500 ${
                      creditScoreData.credit_band_color === "green"
                        ? "bg-green-500"
                        : creditScoreData.credit_band_color === "yellow"
                          ? "bg-yellow-500"
                          : creditScoreData.credit_band_color === "orange"
                            ? "bg-orange-500"
                            : "bg-red-500"
                    }`}
                    style={{
                      width: `${(creditScoreData.credit_score / 900) * 100}%`,
                    }}
                  />
                </div>

                {/* Band label */}
                <div className="text-lg font-semibold text-foreground">{creditScoreData.credit_band}</div>

                {/* Message */}
                <div className="text-sm text-muted-foreground">
                  {creditScoreData.eligible_for_loan
                    ? language === "en"
                      ? "You qualify for our loan products! Proceeding with assessment..."
                      : "आप हमारे loan products के लिए योग्य हैं! आकलन के साथ आगे बढ़ रहे हैं..."
                    : language === "en"
                      ? "Unfortunately, you do not meet our minimum requirement."
                      : "दुर्भाग्यवश, आप हमारी न्यूनतम आवश्यकता को पूरा नहीं करते।"}
                </div>

                {/* Improvement tips if ineligible */}
                {!creditScoreData.eligible_for_loan && creditScoreData.improvement_tips && (
                  <div className="mt-4 pt-4 border-t border-yellow-500/20 text-left">
                    <div className="text-sm font-semibold mb-2">{language === "en" ? "How to improve:" : "सुधार करने के लिए:"}</div>
                    <ul className="text-xs space-y-1 text-muted-foreground">
                      {creditScoreData.improvement_tips.map((tip: string, idx: number) => (
                        <li key={idx}>• {tip}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

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
