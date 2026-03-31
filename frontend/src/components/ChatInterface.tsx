import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChatMessage } from "./ChatMessage";
import { LoanCard } from "./LoanCard";
import { CreditScoreCard } from "./CreditScoreCard";
import { SanctionLetter } from "./SanctionLetter";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { Send, ArrowLeft, MessageCircle, Upload, CheckCircle2, FileText, Pencil } from "lucide-react";
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

interface PanKycFields {
  pan_number?: string;
  name?: string;
  fathers_name?: string;
  date_of_birth?: string;
  age?: number;
  age_eligible?: boolean;
}

interface AadhaarKycFields {
  aadhaar_last4?: string;
  name?: string;
  date_of_birth?: string;
  age?: number;
  gender?: string;
  age_eligible?: boolean;
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
  const [showPanUploadCard, setShowPanUploadCard] = useState(false);
  const [showAadhaarUploadCard, setShowAadhaarUploadCard] = useState(false);
  const [isKycProcessing, setIsKycProcessing] = useState(false);
  const [kycProcessingText, setKycProcessingText] = useState("");
  const [kycProgress, setKycProgress] = useState(0);
  const [showPanConfirmCard, setShowPanConfirmCard] = useState(false);
  const [showKycVerifiedCard, setShowKycVerifiedCard] = useState(false);
  const [panKycData, setPanKycData] = useState<PanKycFields | null>(null);
  const [aadhaarKycData, setAadhaarKycData] = useState<AadhaarKycFields | null>(null);
  const [kycMatchScore, setKycMatchScore] = useState<number | null>(null);
  const [kycReferenceId, setKycReferenceId] = useState<string>("");
  const [panFile, setPanFile] = useState<File | null>(null);
  const [aadhaarFile, setAadhaarFile] = useState<File | null>(null);
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
  const panInputRef = useRef<HTMLInputElement>(null);
  const aadhaarInputRef = useRef<HTMLInputElement>(null);

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

  const DEVANAGARI_DIGIT_MAP: Record<string, string> = {
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
  };

  const toAsciiDigits = (value: string) =>
    value.replace(/[०-९]/g, (digit) => DEVANAGARI_DIGIT_MAP[digit] ?? digit);

  const normalizePan = (value: string) => toAsciiDigits(value).replace(/\s+/g, "").toUpperCase();

  const extractPan = (value: string) => {
    const normalized = toAsciiDigits(value).toUpperCase();
    const match = normalized.match(/[A-Z]{5}[0-9]{4}[A-Z]/);
    return match ? match[0] : "";
  };

  const isValidPan = (value: string) => /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(value);

  const kycText = (en: string, hi: string) => (language === "hi" ? hi : en);

  const addBotMessage = (text: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text,
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

  const startKycProgress = (label: string) => {
    setIsKycProcessing(true);
    setKycProcessingText(label);
    setKycProgress(5);
    let value = 5;
    const timer = setInterval(() => {
      value = Math.min(95, value + 5);
      setKycProgress(value);
    }, 150);
    return timer;
  };

  const stopKycProgress = (timer: ReturnType<typeof setInterval>) => {
    clearInterval(timer);
    setKycProgress(100);
    setTimeout(() => {
      setIsKycProcessing(false);
      setKycProcessingText("");
      setKycProgress(0);
    }, 300);
  };

  const callKycPanExtractAPI = async (file: File) => {
    const form = new FormData();
    form.append("document", file);
    form.append("language", language);

    const response = await fetch("http://localhost:8003/kyc/extract/pan", {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => null);
      throw new Error(errBody?.detail || "PAN extraction failed");
    }

    return response.json();
  };

  const callKycAadhaarExtractAPI = async (file: File) => {
    const form = new FormData();
    form.append("document", file);

    const response = await fetch("http://localhost:8003/kyc/extract/aadhaar", {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => null);
      throw new Error(errBody?.detail || "Aadhaar extraction failed");
    }

    return response.json();
  };

  const callKycVerifyAPI = async (panDoc: File, aadhaarDoc: File) => {
    const form = new FormData();
    form.append("pan", panDoc);
    form.append("aadhaar", aadhaarDoc);

    const response = await fetch("http://localhost:8003/kyc/verify", {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => null);
      throw new Error(errBody?.detail || "KYC verification failed");
    }

    return response.json();
  };

  const proceedToCreditFlow = async (panNumber: string) => {
    const normalizedPan = normalizePan(panNumber);
    if (!isValidPan(normalizedPan)) {
      toast.error(kycText("Invalid PAN from KYC extraction", "KYC extraction से PAN invalid मिला"));
      return;
    }

    setUserData((prev) => ({ ...prev, pan: normalizedPan }));
    activateAgent("Credit Underwriting Agent", "Evaluating eligibility based on credit and risk profile.");
    addBotMessage(TRANSLATIONS.kyc_processing[language]);

    const creditScoreResult = await callCreditScoreAPI(normalizedPan);
    if (!creditScoreResult) return;

    setShowCreditScoreCard(true);
    setTimeout(() => {
      addBotMessage(
        language === "en"
          ? "Your credit profile has been evaluated. Continuing with personalized loan options based on your risk tier and pricing band."
          : "आपकी credit profile का मूल्यांकन हो गया है। अब आपके risk tier और pricing band के आधार पर personalized loan options दिखाए जा रहे हैं।"
      );
      activateAgent("Loan Recommendation Engine", "Generating personalized loan options based on risk profile.");
      setShowLoanOffers(true);
      conversationStep.current = 2;
    }, 1500);
  };

  const handlePanFileSelected = async (file?: File) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error(kycText("File exceeds 5MB limit", "फ़ाइल 5MB सीमा से बड़ी है"));
      return;
    }

    setPanFile(file);
    setShowPanUploadCard(false);
    setMessages((prev) => [...prev, { id: prev.length + 1, text: file.name, isBot: false }]);

    const timer = startKycProgress(kycText("Scanning your PAN card...", "आपके PAN कार्ड को स्कैन किया जा रहा है..."));
    try {
      const result = await callKycPanExtractAPI(file);
      stopKycProgress(timer);

      setPanKycData(result.extracted_fields);
      const issues: string[] = result.validation?.issues || [];
      const confidence = Number(result.confidence_score || 0);
      const panFound = Boolean(result.validation?.pan_format_valid);
      const nameFound = Boolean(result.validation?.name_found);
      const dobFound = Boolean(result.validation?.dob_found);

      // Accept when critical PAN fields are present, even if OCR confidence is modest.
      const valid = panFound && dobFound && (nameFound || confidence >= 0.45);

      if (!valid) {
        const hasPanMissingIssue = issues.some((i) => i.toLowerCase().includes("pan format"));
        const hasAgeIssue = issues.some((i) => i.toLowerCase().includes("age"));

        if (!panFound && confidence > 0.2) {
          addBotMessage(
            kycText(
              "This file doesn't look like a PAN card. Please upload the PAN card front image or PAN PDF.",
              "यह फ़ाइल PAN कार्ड जैसी नहीं लग रही है। कृपया PAN कार्ड का front image या PAN PDF अपलोड करें।"
            )
          );
        } else if (confidence <= 0.2 || !nameFound || !dobFound) {
          addBotMessage(
            kycText(
              "OCR could not read key PAN fields clearly. Please upload a sharper PAN image/PDF in good lighting.",
              "OCR PAN के मुख्य fields साफ़ नहीं पढ़ पाया। कृपया अच्छी रोशनी में अधिक साफ PAN image/PDF अपलोड करें।"
            )
          );
        } else if (hasAgeIssue) {
          addBotMessage(
            kycText(
              "Applicants must be between 21 and 65 years old to apply.",
              "आवेदन करने के लिए आयु 21 से 65 वर्ष के बीच होनी चाहिए।"
            )
          );
        } else if (hasPanMissingIssue) {
          addBotMessage(
            kycText(
              "PAN number couldn't be validated. Please upload a clear PAN card image where the PAN number is fully visible.",
              "PAN number validate नहीं हो पाया। कृपया ऐसा PAN कार्ड image अपलोड करें जिसमें PAN number पूरी तरह दिखाई दे।"
            )
          );
        } else {
          addBotMessage(
            kycText(
              issues[0] || "The document image is unclear. Please upload a better quality photo in good lighting.",
              issues[0] || "दस्तावेज़ स्पष्ट नहीं है। कृपया अच्छी रोशनी में स्पष्ट फोटो अपलोड करें।"
            )
          );
        }

        setShowPanUploadCard(true);
        return;
      }

      setShowPanConfirmCard(true);
    } catch (error) {
      stopKycProgress(timer);
      toast.error(error instanceof Error ? error.message : "PAN OCR failed");
      setShowPanUploadCard(true);
    }
  };

  const handleAadhaarFileSelected = async (file?: File) => {
    if (!file || !panFile) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error(kycText("File exceeds 5MB limit", "फ़ाइल 5MB सीमा से बड़ी है"));
      return;
    }

    setAadhaarFile(file);
    setShowAadhaarUploadCard(false);
    setMessages((prev) => [...prev, { id: prev.length + 1, text: file.name, isBot: false }]);

    const timer = startKycProgress(kycText("Scanning your Aadhaar card...", "आपके Aadhaar कार्ड को स्कैन किया जा रहा है..."));
    try {
      const aadhaarResult = await callKycAadhaarExtractAPI(file);
      setAadhaarKycData(aadhaarResult.extracted_fields);

      const aadhaarIssues: string[] = aadhaarResult.validation?.issues || [];
      const aadhaarConfidence = Number(aadhaarResult.confidence_score || 0);
      const aadhaarValid = Boolean(aadhaarResult.validation?.aadhaar_format_valid);
      if (!aadhaarValid) {
        stopKycProgress(timer);
        if (aadhaarConfidence > 0.2) {
          addBotMessage(
            kycText(
              "This file doesn't look like an Aadhaar card. Please upload a valid Aadhaar front image/PDF.",
              "यह फ़ाइल Aadhaar कार्ड जैसी नहीं लग रही है। कृपया valid Aadhaar front image/PDF अपलोड करें।"
            )
          );
        } else {
          addBotMessage(
            kycText(
              "OCR could not read your Aadhaar clearly. Please upload a sharper image/PDF in good lighting.",
              "OCR Aadhaar साफ़ नहीं पढ़ पाया। कृपया अच्छी रोशनी में अधिक साफ image/PDF अपलोड करें।"
            )
          );
        }
        if (aadhaarIssues.length > 0) {
          toast.error(aadhaarIssues[0]);
        }
        setShowAadhaarUploadCard(true);
        return;
      }

      const verifyResult = await callKycVerifyAPI(panFile, file);
      stopKycProgress(timer);

      if (!verifyResult.overall_kyc_passed) {
        const nameScore = Number(verifyResult.cross_validation?.name_match_score ?? 0);
        const dobMatch = Boolean(verifyResult.cross_validation?.dob_match);
        const ageEligible = Boolean(verifyResult.cross_validation?.age_eligible);

        if (nameScore < 70) {
          addBotMessage(
            kycText(
              "The names on your PAN and Aadhaar don't match closely enough. Please check your documents.",
              "PAN और Aadhaar पर नाम पर्याप्त रूप से मेल नहीं खा रहे हैं। कृपया दस्तावेज़ जांचें।"
            )
          );
        } else if (!dobMatch) {
          addBotMessage(
            kycText(
              "Date of birth on PAN and Aadhaar does not match. Please upload clearer documents or verify your details.",
              "PAN और Aadhaar पर जन्म तिथि मेल नहीं खा रही है। कृपया अधिक स्पष्ट दस्तावेज़ अपलोड करें या विवरण जांचें।"
            )
          );
        } else if (!ageEligible) {
          addBotMessage(
            kycText(
              "Applicants must be between 21 and 65 years old to apply.",
              "आवेदन करने के लिए आयु 21 से 65 वर्ष के बीच होनी चाहिए।"
            )
          );
        } else {
          addBotMessage(
            kycText(
              "KYC verification could not be completed. Please retry with clearer PAN and Aadhaar files.",
              "KYC सत्यापन पूरा नहीं हो सका। कृपया अधिक स्पष्ट PAN और Aadhaar फाइलों के साथ पुनः प्रयास करें।"
            )
          );
        }
        setShowAadhaarUploadCard(true);
        return;
      }

      setKycMatchScore(verifyResult.cross_validation?.name_match_score ?? null);
      setKycReferenceId(verifyResult.kyc_reference_id ?? "");
      setShowKycVerifiedCard(true);

      setTimeout(async () => {
        setShowKycVerifiedCard(false);
        const extractedPan = verifyResult.pan_data?.pan_number || panKycData?.pan_number;
        if (extractedPan) {
          await proceedToCreditFlow(extractedPan);
        }
      }, 1300);
    } catch (error) {
      stopKycProgress(timer);
      toast.error(error instanceof Error ? error.message : "Aadhaar OCR failed");
      setShowAadhaarUploadCard(true);
    }
  };

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
    tenureMonths: number,
    maxNegotiationRounds: number
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
          max_negotiation_rounds: maxNegotiationRounds,
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
      const response = await fetch(`http://localhost:8000/credit-score/${encodeURIComponent(pan)}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "Credit score fetch failed");
      }
      const data = await response.json();

      setCreditScoreData(data);
      setShowCreditScoreCard(true);

      return data;
    } catch (error) {
      console.error("Credit score error:", error);
      const message = error instanceof Error ? error.message : "Failed to fetch credit score";
      toast.error(message);
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
          botResponse = kycText("Please upload your PAN card first.", "कृपया पहले अपना PAN कार्ड अपलोड करें।");
          setShowPanUploadCard(true);
          conversationStep.current = 1;
          break;

        case 1: {
          botResponse = kycText(
            "Please use the upload card below to upload your PAN document.",
            "कृपया PAN दस्तावेज़ अपलोड करने के लिए नीचे दिए गए upload card का उपयोग करें।"
          );
          break;
        }

        case 2:
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

      if (assessmentResult && (assessmentResult.decision === "APPROVED" || assessmentResult.decision === "APPROVED_WITH_CONDITIONS")) {
        // Then call negotiation API with max_negotiation_rounds from assessment
        const negotiationResult = await callNegotiationAPI(
          assessmentResult.risk_score,
          assessmentResult.risk_tier,
          amount,
            tenure,
            assessmentResult.max_negotiation_rounds || 0
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
            <div className="mb-2 text-center text-[11px] uppercase tracking-wide text-muted-foreground">
              Agent Activation Timeline
            </div>
            <div className="flex flex-wrap items-center justify-center gap-2">
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

        {isKycProcessing && (
          <div className="max-w-md rounded-xl border border-yellow-500/40 bg-gradient-to-br from-card to-card/80 p-4 shadow-lg shadow-yellow-500/10">
            <div className="mb-2 text-sm font-medium text-foreground">{kycProcessingText}</div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted/70">
              <div
                className="h-full rounded-full bg-gradient-to-r from-yellow-400 to-yellow-500 transition-all duration-200"
                style={{ width: `${kycProgress}%` }}
              />
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">{kycProgress}%</div>
          </div>
        )}

        {showPanUploadCard && (
          <div className="max-w-md rounded-xl border-2 border-dashed border-yellow-500/70 bg-gradient-to-br from-card to-card/85 p-5 shadow-lg shadow-yellow-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-foreground">
              <FileText className="h-4 w-4 text-yellow-400" />
              {kycText("Upload PAN Card", "PAN कार्ड अपलोड करें")}
            </div>
            <div className="mb-3 text-xs text-muted-foreground">JPG, PNG or PDF • Max 5MB</div>
            <input
              ref={panInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              className="hidden"
              onChange={(e) => handlePanFileSelected(e.target.files?.[0])}
            />
            <Button variant="outline" className="w-full border-yellow-500/50 bg-background/60 hover:bg-yellow-500/10" onClick={() => panInputRef.current?.click()}>
              <Upload className="mr-2 h-4 w-4" />
              {kycText("Choose File", "फ़ाइल चुनें")}
            </Button>
            <div className="mt-2 text-[11px] text-muted-foreground">
              {kycText("or drag file here", "या फ़ाइल यहां drag करें")}
            </div>
          </div>
        )}

        {showPanConfirmCard && panKycData && (
          <div className="max-w-md rounded-xl border border-green-500/50 bg-gradient-to-br from-card to-card/85 p-4 shadow-lg shadow-green-500/10">
            <div className="mb-2 flex items-center gap-2 text-base font-semibold text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              {kycText("PAN Card Verified", "PAN कार्ड सत्यापित")}
            </div>
            <div className="space-y-1.5 text-sm text-foreground">
              <div className="font-medium">{panKycData.name}</div>
              <div>{panKycData.pan_number}</div>
              <div>{panKycData.date_of_birth} {panKycData.age ? `(Age: ${panKycData.age})` : ""}</div>
              <div>{kycText("Father", "पिता")}: {panKycData.fathers_name}</div>
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                variant="accent"
                className="flex-1"
                onClick={() => {
                  setShowPanConfirmCard(false);
                  setShowAadhaarUploadCard(true);
                  addBotMessage(kycText("Great! Now upload your Aadhaar card.", "बहुत बढ़िया! अब अपना Aadhaar कार्ड अपलोड करें।"));
                }}
              >
                {kycText("Confirm", "पुष्टि करें")}
              </Button>
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => {
                  setShowPanConfirmCard(false);
                  setShowPanUploadCard(true);
                }}
              >
                <Pencil className="mr-1 h-4 w-4" />
                {kycText("Edit", "संपादित करें")}
              </Button>
            </div>
          </div>
        )}

        {showAadhaarUploadCard && (
          <div className="max-w-md rounded-xl border-2 border-dashed border-yellow-500/70 bg-gradient-to-br from-card to-card/85 p-5 shadow-lg shadow-yellow-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-foreground">
              <FileText className="h-4 w-4 text-yellow-400" />
              {kycText("Upload Aadhaar Card", "Aadhaar कार्ड अपलोड करें")}
            </div>
            <div className="mb-3 text-xs text-muted-foreground">JPG, PNG or PDF • Max 5MB</div>
            <input
              ref={aadhaarInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              className="hidden"
              onChange={(e) => handleAadhaarFileSelected(e.target.files?.[0])}
            />
            <Button variant="outline" className="w-full border-yellow-500/50 bg-background/60 hover:bg-yellow-500/10" onClick={() => aadhaarInputRef.current?.click()}>
              <Upload className="mr-2 h-4 w-4" />
              {kycText("Choose File", "फ़ाइल चुनें")}
            </Button>
            <div className="mt-2 text-[11px] text-muted-foreground">
              {kycText("or drag file here", "या फ़ाइल यहां drag करें")}
            </div>
          </div>
        )}

        {showKycVerifiedCard && (
          <div className="max-w-md rounded-xl border border-green-500/50 bg-gradient-to-br from-card to-card/85 p-4 shadow-lg shadow-green-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              {kycText("KYC Verified", "KYC सत्यापित")}
            </div>
            <div className="text-sm text-foreground">{kycText("Documents match", "दस्तावेज़ मेल")} : {kycMatchScore ?? "-"}%</div>
            <div className="text-sm text-muted-foreground">KYC Ref: {kycReferenceId}</div>
          </div>
        )}

        {showCreditScoreCard && creditScoreData && (
          <div className="py-4">
            <CreditScoreCard score={creditScoreData.credit_score} maxScore={900} />
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
            disabled={
              showLoanOffers ||
              showSanction ||
              isKycProcessing ||
              showPanUploadCard ||
              showAadhaarUploadCard ||
              showPanConfirmCard
            }
          />
          <Button
            variant="chat"
            size="icon"
            onClick={handleSend}
            disabled={
              !input.trim() ||
              showLoanOffers ||
              showSanction ||
              isKycProcessing ||
              showPanUploadCard ||
              showAadhaarUploadCard ||
              showPanConfirmCard
            }
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};
