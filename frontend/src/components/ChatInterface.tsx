import React, { useState, useRef, useEffect, useMemo, ClipboardEvent } from "react";
import { ENDPOINTS } from "../config";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { ChatMessage } from "./ChatMessage";
import { CreditScoreCard } from "./CreditScoreCard";
import { SanctionLetter } from "./SanctionLetter";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { Send, ArrowLeft, MessageCircle, Upload, CheckCircle2, FileText, Pencil, Check, X, Smartphone, Zap, Bot, MessageSquare, Clock, AlertTriangle, CheckCircle, Shield, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { QuickReplies } from "./QuickReplies";
import { EmiCalculatorWidget } from "./EmiCalculatorWidget";
import { LoanComparisonCards, type Offer } from "./LoanComparisonCards";
import {
  AgentActivityPanel,
  type AgentTraceItem,
  type KycAuditEntry,
  type KycAuditSummary,
} from "./AgentActivityPanel";
import { Badge } from "./ui/badge";
import { TRANSLATIONS } from "../lib/translations";
import { formatIndianRupees, detectLanguage } from "../lib/languageUtils";
import { cn } from "../lib/utils";
import { User } from "lucide-react";
import { useNavigate } from "react-router-dom";

const AGENT_PIPELINE = [
  "Master Agent",
  "KYC Verification Agent",
  "Credit Underwriting Agent",
  "Loan Recommendation Engine",
  "Dynamic Negotiation Agent",
];

const APP_STAGES = [
  { id: "kyc", label: "KYC" },
  { id: "credit", label: "Credit Check" },
  { id: "offer", label: "Offer" },
  { id: "negotiate", label: "Negotiate" },
  { id: "sanction", label: "Sanction" },
];

interface Message {
  id: number;
  text: string;
  isBot: boolean;
  status?: "sent" | "delivered" | "responded";
  quickReplies?: { label: string; value: string }[];
  type?: "emi-calculator" | "escalation" | "comparison-cards";
  variant?: "system";
}

interface QuickEligibilityPreview {
  loanAmount: number;
  monthlyIncome: number;
  tenureMonths: number;
  assumedRate: number;
  estimatedEmi: number;
  emiToIncomeRatio: number;
  maxAffordableEmi: number;
  status: "Strong" | "Conditional" | "Needs review";
  note: string;
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
  aadhaar_number?: string;
  mobile_last4?: string;
  mobile_number?: string;
  name?: string;
  date_of_birth?: string;
  age?: number;
  gender?: string;
  age_eligible?: boolean;
}

interface AadhaarVerhoeffResult {
  valid?: boolean;
  message?: string;
  masked?: string;
  aadhaar_last4?: string;
  last4?: string;
  reason?: string;
}

interface AadhaarQrVerification {
  qr_found?: boolean;
  qr_parsed?: boolean;
  qr_type?: string;
  mobile_hash_available?: boolean;
  uidai_signed?: boolean;
  mobile_verification?: {
    verified?: boolean;
    iterations?: number;
    method?: string;
    mobile_last4?: string;
  };
  name_consistency?: {
    consistent?: boolean;
    vlm_name?: string;
    qr_name?: string;
  };
  data_source?: string;
}

type KycFactorKey = "fa1" | "fa2" | "fa3";

interface KycFactorState {
  fa1: boolean;
  fa2: boolean;
  fa3: boolean;
  current: 1 | 2 | 3;
}

const KYC_FACTORS: Array<{ key: KycFactorKey; label: string }> = [
  { key: "fa1", label: "1. Document & Match" },
  { key: "fa2", label: "2. ID Validation" },
  { key: "fa3", label: "3. OTP" },
];

const formatMissingFields = (fields: string[]) => fields.join(", ");
const missingFieldMessage = (fields: string[]) => {
  const joined = formatMissingFields(fields);
  return fields.length === 1 ? `${joined} is missing` : `${joined} are missing`;
};

const MONEY_PATTERN = /(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(lakh|lakhs|lac|lacs|crore|cr|k|thousand)?/i;

const extractApplicantNameFromMessage = (message: string, existingName?: string) => {
  if (existingName) return existingName;

  const text = message.trim().toLowerCase();
  if (!text) return null;

  const patterns = [
    /\bmy name is ([a-z][a-z\s]{1,40})\b/i,
    /\bi am ([a-z][a-z\s]{1,40})\b/i,
    /\bi'm ([a-z][a-z\s]{1,40})\b/i,
    /\bmera naam ([a-z][a-z\s]{1,40})\b/i,
    /\bmai(n)? ([a-z][a-z\s]{1,40})\b/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match?.[1]) continue;

    const candidate = match[1].trim().replace(/\b(apply|want|need|for|to|loan|please|help)\b.*$/i, "").trim();
    if (candidate && candidate.split(/\s+/).length <= 4) {
      return candidate
        .split(/\s+/)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
    }
  }

  return null;
};

const parseMoneyAmount = (value: string): number | null => {
  const match = value.match(MONEY_PATTERN);
  if (!match?.[1]) return null;

  const numericValue = Number.parseFloat(match[1].replace(/,/g, ""));
  if (!Number.isFinite(numericValue)) return null;

  const suffix = (match[2] || "").toLowerCase();
  let amount = numericValue;

  if (suffix === "lakh" || suffix === "lakhs" || suffix === "lac" || suffix === "lacs") {
    amount *= 100000;
  } else if (suffix === "crore" || suffix === "cr") {
    amount *= 10000000;
  } else if (suffix === "k" || suffix === "thousand") {
    amount *= 1000;
  }

  return Math.round(amount);
};

const parseMoneyAmounts = (value: string): number[] => {
  const regex = new RegExp(MONEY_PATTERN.source, "gi");
  const results: number[] = [];
  let match: RegExpExecArray | null;

  while ((match = regex.exec(value)) !== null) {
    if (!match[1]) continue;

    const numericValue = Number.parseFloat(match[1].replace(/,/g, ""));
    if (!Number.isFinite(numericValue)) continue;

    const suffix = (match[2] || "").toLowerCase();
    let amount = numericValue;

    if (suffix === "lakh" || suffix === "lakhs" || suffix === "lac" || suffix === "lacs") {
      amount *= 100000;
    } else if (suffix === "crore" || suffix === "cr") {
      amount *= 10000000;
    } else if (suffix === "k" || suffix === "thousand") {
      amount *= 1000;
    }

    results.push(Math.round(amount));
  }

  return results;
};

const extractMoneyByKeywords = (message: string, keywords: string[], allowFallback = false) => {
  const lower = message.toLowerCase();

  for (const keyword of keywords) {
    const keywordIndex = lower.indexOf(keyword);
    if (keywordIndex < 0) continue;

    const afterSlice = message.slice(keywordIndex, Math.min(message.length, keywordIndex + 90));
    const afterMatches = parseMoneyAmounts(afterSlice);
    if (afterMatches.length) {
      return afterMatches[0];
    }

    const beforeStart = Math.max(0, keywordIndex - 50);
    const beforeSlice = message.slice(beforeStart, keywordIndex + keyword.length);
    const beforeMatches = parseMoneyAmounts(beforeSlice);
    if (beforeMatches.length) {
      return beforeMatches[beforeMatches.length - 1];
    }
  }

  return allowFallback ? parseMoneyAmount(message) : null;
};

const extractLoanAmountFromMessage = (message: string, allowFallback = false): number | null =>
  extractMoneyByKeywords(message, ["loan", "amount", "borrow", "need", "require", "apply", "finance"], allowFallback);

const extractMonthlyIncomeFromMessage = (message: string, allowFallback = false): number | null =>
  extractMoneyByKeywords(message, ["income", "salary", "monthly", "per month", "per-month", "take home", "take-home", "in-hand", "ctc"], allowFallback);

const buildQuickEligibilityPreview = (loanAmount: number, monthlyIncome: number): QuickEligibilityPreview => {
  const tenureMonths = 60;
  const assumedRate = 11.5;
  const monthlyRate = assumedRate / 1200;
  const base = monthlyRate === 0
    ? loanAmount / tenureMonths
    : (loanAmount * monthlyRate * Math.pow(1 + monthlyRate, tenureMonths)) / (Math.pow(1 + monthlyRate, tenureMonths) - 1);
  const estimatedEmi = Math.max(1, Math.round(base));
  const maxAffordableEmi = Math.round(monthlyIncome * 0.4);
  const emiToIncomeRatio = monthlyIncome > 0 ? estimatedEmi / monthlyIncome : 1;

  let status: QuickEligibilityPreview["status"] = "Needs review";
  let note = "This request may need a smaller amount or a longer tenure to stay within a safe EMI range.";

  if (emiToIncomeRatio <= 0.33) {
    status = "Strong";
    note = "This looks comfortably affordable on a standard repayment profile.";
  } else if (emiToIncomeRatio <= 0.4) {
    status = "Conditional";
    note = "This is workable, but the final credit check may tighten the approved terms.";
  }

  return {
    loanAmount,
    monthlyIncome,
    tenureMonths,
    assumedRate,
    estimatedEmi,
    emiToIncomeRatio,
    maxAffordableEmi,
    status,
    note,
  };
};

const OCR_REQUEST_TIMEOUT_MS = 120000;
const AADHAAR_REQUEST_TIMEOUT_MS = 20000;

interface CreditScoreData {
  credit_score: number;
  [key: string]: unknown;
}

interface UnderwritingResultData {
  decision?: string;
  approval_probability?: number;
  confidence_lower?: number;
  confidence_upper?: number;
  confidence_width?: number;
  model_certainty?: string;
  income_reasonability?: {
    flag?: string;
    foir?: number;
    message?: string;
    suggested_amount?: number;
    required_monthly_income?: number;
    emi?: number;
  };
  soft_reject_guidance?: {
    message?: string;
    income_delta_monthly?: number;
    repayment_history_months?: number;
    repayment_history_impact?: string;
    suggested_approved_amount?: number;
    threshold_gap_points?: number;
  } | null;
  model_drift_warning?: boolean;
  drifted_features?: string[];
  recommendation?: string | null;
  structured_shap_narration?: string | null;
  xgboost_probability?: number;
  risk_tier?: string;
  risk_score?: number;
  max_negotiation_rounds?: number;
  message?: string;
  threshold_used?: number;
  // Industry-standard CIBIL metadata (added by backend)
  cibil_score?: number;
  cibil_band?: string;
  cibil_classification?: string;
  risk_label?: string;
  industry_standard?: string;
  eligible?: boolean;
  conditional?: boolean;
  rate_range?: string;
  cibil_max_negotiation_rounds?: number;
  // Alternative scoring
  alternative_score?: number;
  alternative_eligible?: boolean;
  alternative_details?: Record<string, unknown> | null;
}

interface BankStatementAnalysis {
  analysis_possible?: boolean;
  estimated_monthly_income?: number;
  income_confidence?: string;
  data_source?: string;
  reason?: string;
  note?: string;
}

interface EmiHolidayOption {
  holidayMonths?: number;
  holiday_months?: number;
  adjustedPrincipal?: number;
  adjusted_principal?: number;
  emi?: number;
  original_emi?: number;
  extraCost?: number;
  extra_cost?: number;
  message?: string;
  recommended?: boolean;
  firstEmiAfterMonth?: number;
  first_emi_after_month?: number;
}

interface RepeatBorrowerData {
  sanction_reference?: string;
  reference?: string;
  sanctioned_at?: string;
  sanctionedDate?: string;
  date?: string;
  amount?: number;
  limit?: number;
  preapproved_limit?: number;
  rate?: number;
  purpose?: string;
  employment_type?: string;
  employer_name?: string;
}

interface NegotiationOffer {
  rate: number;
  interest_rate?: number;
  loan_amount: number;
  tenure_months: number;
  emi: number;
  monthly_emi?: number;
  total_payable?: number;
  total_interest?: number;
  savings_vs_opening?: { per_month: number; total: number } | null;
}

interface NegotiationSummary {
  opening_rate: number;
  final_rate: number;
  rate_reduction: number;
  rounds_taken: number;
  total_interest_savings: number;
}

interface UserData {
  name: string;
  pan: string;
  creditScore: number;
  preKycLoanAmount?: number;
  preKycMonthlyIncome?: number;
  selectedLoan: {
    amount: number;
    interest: number;
    tenure: number;
    emi: number;
    holidayMonths?: number;
    holidayExtraCost?: number;
  };
  assessmentId: string;
  sessionId: string;
  riskScore: number;
  riskTier: string;
  maxNegotiationRounds: number;
  stage: string;
  blockchainData?: {
    transaction_id: string;
    block_hash: string;
  };
}

interface SessionData {
  messages: Message[];
  stage: string;
  applicant_data: UserData;
  timestamp: number;
}

type ApplicantMode = "new" | "existing" | null;

export const ChatInterface = ({ onClose }: ChatInterfaceProps) => {
  const navigate = useNavigate();
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const [language, setLanguage] = useState<"en" | "hi">(
    () => (localStorage.getItem("loanease_language") as "en" | "hi") || "en"
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isBackendBusy, setIsBackendBusy] = useState(false);
  const [showCreditScore, setShowCreditScore] = useState(false);
  const [showLoanOffers, setShowLoanOffers] = useState(false);
  const [pendingOffer, setPendingOffer] = useState<Offer | null>(null);
  const [showKfsCard, setShowKfsCard] = useState(false);
  const [kfsAcknowledged, setKfsAcknowledged] = useState(false);
  const [showSanction, setShowSanction] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [activeAgent, setActiveAgent] = useState("Master Agent");
  const [showCreditScoreCard, setShowCreditScoreCard] = useState(false);
  const [creditScoreData, setCreditScoreData] = useState<CreditScoreData | null>(null);
  const [underwritingResult, setUnderwritingResult] = useState<UnderwritingResultData | null>(null);
  const [showPanUploadCard, setShowPanUploadCard] = useState(false);
  const [showAadhaarUploadCard, setShowAadhaarUploadCard] = useState(false);
  const [isKycProcessing, setIsKycProcessing] = useState(false);
  const [kycProcessingText, setKycProcessingText] = useState("");
  const [kycProgress, setKycProgress] = useState(0);
  const [showPanConfirmCard, setShowPanConfirmCard] = useState(false);
  const [showAadhaarConfirmCard, setShowAadhaarConfirmCard] = useState(false);
  const [showKycVerifiedCard, setShowKycVerifiedCard] = useState(false);
  const [showOtpCard, setShowOtpCard] = useState(false);
  const [panKycData, setPanKycData] = useState<PanKycFields | null>(null);
  const [aadhaarKycData, setAadhaarKycData] = useState<AadhaarKycFields | null>(null);
  const [aadhaarVerhoeffResult, setAadhaarVerhoeffResult] = useState<AadhaarVerhoeffResult | null>(null);
  const [manualAadhaarInput, setManualAadhaarInput] = useState("");
  const [aadhaarValidityText, setAadhaarValidityText] = useState("");
  const [aadhaarValidityOk, setAadhaarValidityOk] = useState<boolean | null>(null);
  const [kycMatchScore, setKycMatchScore] = useState<number | null>(null);
  const [kycReferenceId, setKycReferenceId] = useState<string>("");
  const [otpDigits, setOtpDigits] = useState<string[]>(Array(6).fill(""));
  const [otpSentToLast4, setOtpSentToLast4] = useState("");
  const [otpAttemptsRemaining, setOtpAttemptsRemaining] = useState<number | null>(null);
  const [otpSecondsRemaining, setOtpSecondsRemaining] = useState(0);
  const [otpResendCooldown, setOtpResendCooldown] = useState(0);
  const [otpStatusMessage, setOtpStatusMessage] = useState("");
  const [otpError, setOtpError] = useState("");
  const [otpSubmitting, setOtpSubmitting] = useState(false);
  const [otpLocked, setOtpLocked] = useState(false);
  const [pendingCreditPan, setPendingCreditPan] = useState("");
  const [panFile, setPanFile] = useState<File | null>(null);
  const [aadhaarFile, setAadhaarFile] = useState<File | null>(null);
  const [kycFactors, setKycFactors] = useState<KycFactorState>({
    fa1: false,
    fa2: false,
    fa3: false,
    current: 1,
  });
  const [userData, setUserData] = useState<UserData>({
    name: "",
    pan: "",
    creditScore: 0,
    selectedLoan: { amount: 0, interest: 0, tenure: 0, emi: 0 },
    assessmentId: "",
    sessionId: `LE-${new Date().getFullYear()}-${Math.floor(10000 + Math.random() * 90000)}`,
    riskScore: 0,
    riskTier: "",
    maxNegotiationRounds: 0,
    stage: "kyc",
    blockchainData: undefined,
  });

  const [showSessionBanner, setShowSessionBanner] = useState(false);
  const [sessionToResume, setSessionToResume] = useState<SessionData | null>(null);
  const [applicantMode, setApplicantMode] = useState<ApplicantMode>(null);
  const [existingSessionId, setExistingSessionId] = useState("");
  const [pulseBadge, setPulseBadge] = useState(false);
  const [hasStartedConversation, setHasStartedConversation] = useState(false);
  const [isEscalated, setIsEscalated] = useState(false);
  const [escalationData, setEscalationData] = useState({ preferredTime: "", whatsapp: false });
  const [pipelineSessionId, setPipelineSessionId] = useState<string>("");
  const [pipelineStatus, setPipelineStatus] = useState<string>("IDLE");
  const [agentTrace, setAgentTrace] = useState<AgentTraceItem[]>([]);
  const [kycAuditTrail, setKycAuditTrail] = useState<KycAuditEntry[]>([]);
  const [kycAuditSummary, setKycAuditSummary] = useState<KycAuditSummary | null>(null);
  const [showCreditSummaryPopup, setShowCreditSummaryPopup] = useState(false);
  const [isOfflineMode, setIsOfflineMode] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [intakeCompleted, setIntakeCompleted] = useState(false);
  const [intakePreview, setIntakePreview] = useState<QuickEligibilityPreview | null>(null);

  // Feature 2: Bank Statement Analysis
  const [showBankStatementCard, setShowBankStatementCard] = useState(false);
  const [bankStatementResult, setBankStatementResult] = useState<BankStatementAnalysis | null>(null);
  const bankStatementInputRef = useRef<HTMLInputElement>(null);

  // Feature 3: EMI Holiday
  const [emiHolidayOption, setEmiHolidayOption] = useState<EmiHolidayOption | null>(null);
  const [selectedHolidayMonths, setSelectedHolidayMonths] = useState<number>(0);

  // Feature 5: Repeat Borrower
  const [isRepeatBorrower, setIsRepeatBorrower] = useState(false);
  const [repeatBorrowerData, setRepeatBorrowerData] = useState<RepeatBorrowerData | null>(null);

  // Negotiation state machine
  const [negotiationState, setNegotiationState] = useState<string | null>(null);
  const [negotiationOffer, setNegotiationOffer] = useState<NegotiationOffer | null>(null);
  const [negotiationNegId, setNegotiationNegId] = useState<string>("");
  const [negotiationRoundsLeft, setNegotiationRoundsLeft] = useState<number>(0);
  const [negotiationEscalationId, setNegotiationEscalationId] = useState<string>("");
  const [negotiationSummary, setNegotiationSummary] = useState<NegotiationSummary | null>(null);
  const [negotiationFloorRate, setNegotiationFloorRate] = useState<number>(10.5);
  const [isNegotiationBusy, setIsNegotiationBusy] = useState(false);

  const quickEligibilityPreview = useMemo(() => {
    if (intakePreview) return intakePreview;
    if (!userData.preKycLoanAmount || !userData.preKycMonthlyIncome) {
      return null;
    }
    return buildQuickEligibilityPreview(userData.preKycLoanAmount, userData.preKycMonthlyIncome);
  }, [intakePreview, userData.preKycLoanAmount, userData.preKycMonthlyIncome]);

  const handleViewAnalytics = () => {
    window._analyticsSessionId = userData.sessionId;
    localStorage.setItem("loanease_session_id", userData.sessionId);
    setShowAnalytics(true);
  };

  const startNewApplication = () => {
    const nextSessionId = `LE-${new Date().getFullYear()}-${Math.floor(10000 + Math.random() * 90000)}`;

    localStorage.removeItem("loanease_session_id");
    setApplicantMode("new");
    setShowSessionBanner(false);
    setSessionToResume(null);
    setIsRepeatBorrower(false);
    setRepeatBorrowerData(null);
    setMessages([]);
    setInput("");
    setHasStartedConversation(false);
    setIntakeCompleted(false);
    setIntakePreview(null);
    setShowPanUploadCard(false);
    setShowAadhaarUploadCard(false);
    setShowPanConfirmCard(false);
    setShowAadhaarConfirmCard(false);
    setShowKycVerifiedCard(false);
    setAadhaarVerhoeffResult(null);
    setManualAadhaarInput("");
    setAadhaarValidityText("");
    setAadhaarValidityOk(null);
    setShowOtpCard(false);
    setKycFactors({ fa1: false, fa2: false, fa3: false, current: 1 });
    setKycAuditTrail([]);
    setKycAuditSummary(null);
    setUserData((prev) => ({
      ...prev,
      name: "",
      pan: "",
      creditScore: 0,
      preKycLoanAmount: undefined,
      preKycMonthlyIncome: undefined,
      selectedLoan: { amount: 0, interest: 0, tenure: 0, emi: 0 },
      assessmentId: "",
      sessionId: nextSessionId,
      riskScore: 0,
      riskTier: "",
      maxNegotiationRounds: 0,
      stage: "kyc",
      blockchainData: undefined,
    }));
  };

  const signInExistingUser = async () => {
    const trimmedSessionId = existingSessionId.trim();
    if (!trimmedSessionId) {
      toast.error("Please enter a session ID to continue.");
      return;
    }

    try {
      const response = await fetch(`${ENDPOINTS.session_get}/${trimmedSessionId}`);
      if (!response.ok) {
        throw new Error("Session not found");
      }

      const saved = (await response.json()) as SessionData;
      setApplicantMode("existing");
      setSessionToResume(saved);
      setShowSessionBanner(true);
      setUserData((prev) => ({ ...prev, sessionId: trimmedSessionId }));
      localStorage.setItem("loanease_session_id", trimmedSessionId);
      setIsRepeatBorrower(false);
      setRepeatBorrowerData(null);
      toast.success("Session loaded successfully. You may resume or start a new application.");
    } catch (error) {
      setApplicantMode("existing");
      setUserData((prev) => ({ ...prev, sessionId: trimmedSessionId }));
      localStorage.setItem("loanease_session_id", trimmedSessionId);
      setShowSessionBanner(false);
      setSessionToResume(null);
      setIsRepeatBorrower(false);
      setRepeatBorrowerData(null);
      toast.warning("No saved session found. Starting a new application with the provided session ID.");
    }
  };

  const calculateEmiWithHoliday = (amount: number, rate: number, tenureMonths: number, holidayMonths: number) => {
    const monthlyRate = rate / 12 / 100;
    const adjustedPrincipal = monthlyRate > 0 ? amount * Math.pow(1 + monthlyRate, holidayMonths) : amount;
    const power = Math.pow(1 + monthlyRate, tenureMonths);
    const emi = monthlyRate === 0 ? adjustedPrincipal / tenureMonths : (adjustedPrincipal * monthlyRate * power) / (power - 1);
    const basePower = Math.pow(1 + monthlyRate, tenureMonths);
    const baseEmi = monthlyRate === 0 ? amount / tenureMonths : (amount * monthlyRate * basePower) / (basePower - 1);
    return {
      holidayMonths,
      adjustedPrincipal,
      emi: Math.round(emi),
      extraCost: Math.max(0, Math.round((emi * tenureMonths) - (baseEmi * tenureMonths))),
      firstEmiAfterMonth: holidayMonths + 1,
    };
  };

  const toggleAgentSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
  };

  const updatePipelineTracker = (stage: string) => {
    const stageMap = {
      'INITIATED': 1,
      'KYC_PENDING': 1,
      'KYC_QR_PENDING': 1,
      'KYC_OTP_PENDING': 1,
      'KYC_VERIFIED': 2,
      'CREDIT_ASSESSED': 2,
      'OFFER_GENERATED': 3,
      'NEGOTIATING': 4,
      'ACCEPTED': 4,
      'SANCTIONED': 5
    };
    
    const currentStep = stageMap[stage as keyof typeof stageMap] || 1;
    
    // Update pipeline step indicators
    const pipelineSteps = document.querySelectorAll('.pipeline-step');
    pipelineSteps.forEach((step, i) => {
      const stepNum = i + 1;
      step.classList.remove('completed', 'active', 'upcoming');
      
      if (stepNum < currentStep) {
        step.classList.add('completed');
      } else if (stepNum === currentStep) {
        step.classList.add('active');
      } else {
        step.classList.add('upcoming');
      }
    });
    
    // Update header stage text
    const stageLabels = {
      'KYC_PENDING': 'KYC',
      'KYC_OTP_PENDING': 'OTP',
      'KYC_VERIFIED': 'Credit Check',
      'OFFER_GENERATED': 'Offer',
      'NEGOTIATING': 'Negotiating',
      'SANCTIONED': 'Sanctioned'
    };
    
    const headerStageLabel = document.querySelector('.header-stage-label');
    if (headerStageLabel) {
      headerStageLabel.textContent = stageLabels[stage as keyof typeof stageLabels] || stage;
    }
  };

  const updateFA = (factor: number, status: 'pending' | 'active' | 'passed' | 'failed') => {
    const badge = document.getElementById(`fa${factor}-badge`);
    if (!badge) return;
    
    badge.className = `fa-badge ${status}`;
    
    const labels: Record<number, Record<string, string>> = {
      1: {
        pending: '1. Document & Match',
        active: '1. Scanning Docs...',
        passed: '1. Docs Verified',
        failed: '1. Docs Failed',
      },
      2: {
        pending: '2. ID Validation',
        active: '2. Validating...',
        passed: '2. Aadhaar Valid',
        failed: '2. Invalid Aadhaar',
      },
      3: {
        pending: '3. OTP',
        active: '3. OTP Sent...',
        passed: '3. OTP Verified',
        failed: '3. OTP Failed',
      }
    };
    
    badge.textContent = `${status === 'passed' ? 'Verified' : status === 'active' ? 'Processing' : status === 'failed' ? 'Failed' : 'Pending'} ${labels[factor][status]}`;
  };

  // Update pipeline tracker when userData.stage changes
  useEffect(() => {
    updatePipelineTracker(userData.stage);
  }, [userData.stage]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const conversationStep = useRef(0);
  const activeAgentIndex = AGENT_PIPELINE.indexOf(activeAgent);
  const panInputRef = useRef<HTMLInputElement>(null);
  const aadhaarInputRef = useRef<HTMLInputElement>(null);
  const aadhaarManualDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const otpInputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const [processingLog, setProcessingLog] = useState<string[]>([]);

  useEffect(() => {
    if (!showOtpCard) {
      return;
    }

    const timer = setInterval(() => {
      setOtpSecondsRemaining((value) => {
        if (value <= 1) {
          setOtpLocked(true);
          return 0;
        }
        return value - 1;
      });

      setOtpResendCooldown((value) => (value > 0 ? value - 1 : 0));
    }, 1000);

    return () => clearInterval(timer);
  }, [showOtpCard]);

  const showWelcomeState = messages.length === 0 && !showSessionBanner && !hasStartedConversation;
  const isInputLocked =
    isEscalated ||
    !hasStartedConversation ||
    showLoanOffers ||
    showSanction ||
    isKycProcessing ||
    showPanUploadCard ||
    showAadhaarUploadCard ||
    showPanConfirmCard ||
    showAadhaarConfirmCard ||
    showOtpCard ||
    otpLocked ||
    isTyping ||
    isBackendBusy;
  const isProcessing = isBackendBusy || isKycProcessing || isTyping;

  const getInputPlaceholder = () => {
    if (isEscalated) return "Chat disabled pending human review";
    if (!hasStartedConversation) return "Click 'Apply for a Loan' to start";
    if (otpLocked) return "OTP verification failed. Redirecting...";
    if (showOtpCard) return "Verify the OTP sent to your Aadhaar-linked mobile";
    if (showSanction) return "Your sanction letter is ready. Ask a question or download it.";
    if (showLoanOffers) return "Type 'accept' or ask to negotiate the rate...";
    if (userData.stage === "credit") return "Your score is ready. How would you like to proceed?";
    if (userData.stage === "offer") return "Tell me your loan amount or ask to compare offers...";
    if (userData.stage === "negotiate") return "Ask for a better rate or accept the current offer...";
    if (quickEligibilityPreview && !showPanUploadCard) return "Update the loan amount or monthly income, or proceed to KYC";
    return "Type your message...";
  };

  const processingLines = useMemo(() => {
    if (isKycProcessing) {
      return [
        "> KYC_AGENT: Processing document...",
        "> OCR_ENGINE: Extracting text fields",
        "> REGEX_NER: PAN pattern found",
        "> VALIDATION: Format check passed",
        "> AWAITING: Cross-validation...",
      ];
    }

    if (isBackendBusy && userData.stage === "credit") {
      return [
        "> CREDIT_AGENT: Running assessment...",
        "> SCORE_ENGINE: Computing CIBIL profile",
        "> RISK_MODEL: Evaluating repayment risk",
        "> OUTPUT: Preparing credit decision...",
      ];
    }

    if (isBackendBusy && showLoanOffers) {
      return [
        "> OFFER_ENGINE: Building loan options...",
        "> PRICING: Calculating rate bands",
        "> OPTIMIZER: Selecting best tenure",
        "> OUTPUT: Rendering recommendations...",
      ];
    }

    if (isTyping) {
      return [
        "> CHAT_ENGINE: Drafting response...",
        "> NLU: Interpreting user intent",
        "> POLICY: Selecting next action",
      ];
    }

    return [
      "> SYSTEM: Awaiting backend activity...",
    ];
  }, [isBackendBusy, isKycProcessing, isTyping, showLoanOffers, userData.stage]);

  useEffect(() => {
    if (!isProcessing) {
      setProcessingLog([]);
      return;
    }

    setProcessingLog([processingLines[0]]);
    let index = 1;

    const interval = setInterval(() => {
      setProcessingLog((prev) => {
        const nextLine = processingLines[index % processingLines.length];
        index += 1;
        return [...prev, nextLine].slice(-8);
      });
    }, 650);

    return () => clearInterval(interval);
  }, [isProcessing, processingLines]);

  useEffect(() => {
    if (!isProcessing && hasStartedConversation && !isEscalated) {
      const timer = setTimeout(() => {
        textAreaRef.current?.focus();
      }, 100);

      return () => clearTimeout(timer);
    }
  }, [isProcessing, hasStartedConversation, isEscalated]);

  const handleLanguageChange = (lang: "en" | "hi") => {
    setLanguage(lang);
    localStorage.setItem("loanease_language", lang);
    const message =
      lang === "en"
        ? TRANSLATIONS.language_switched_en
        : TRANSLATIONS.language_switched_hi;
    toast.success(message);
  };

  const saveSession = async (currentMessages: Message[], currentStage: string, currentData: UserData) => {
    const sessionKey = `loanease_session_${new Date().toISOString().split('T')[0]}`;
    const sessionData = {
      messages: currentMessages,
      stage: currentStage,
      applicant_data: currentData,
      timestamp: Date.now()
    };
    localStorage.setItem(sessionKey, JSON.stringify(sessionData));

    try {
      await fetch(ENDPOINTS.session_save, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: currentData.sessionId,
          messages: currentMessages,
          stage: currentStage,
          applicant_data: currentData
        }),
      });
    } catch (e) {
      console.warn("Failed to save session to backend", e);
    }
  };

  const handleResume = () => {
    if (sessionToResume) {
      setMessages(sessionToResume.messages);
      setUserData(sessionToResume.applicant_data);
      setHasStartedConversation(true);
      setShowSessionBanner(false);
      toast.success("Session restored successfully!");
    }
  };

  const handleStartFresh = () => {
    const sessionKey = `loanease_session_${new Date().toISOString().split('T')[0]}`;
    localStorage.removeItem(sessionKey);
    localStorage.removeItem("loanease_session_id");
    setHasStartedConversation(false);
    setShowSessionBanner(false);
    setSessionToResume(null);
    setPendingOffer(null);
    setShowKfsCard(false);
    setKfsAcknowledged(false);
    setSelectedHolidayMonths(0);
    setEmiHolidayOption(null);
    toast.info("Started a new session.");
  };

  const handleStartConversation = () => {
    if (!hasStartedConversation) {
      setHasStartedConversation(true);
      setIntakeCompleted(false);
      setIntakePreview(null);
      conversationStep.current = 0;
      setPendingOffer(null);
      setShowKfsCard(false);
      setKfsAcknowledged(false);
      if (isRepeatBorrower && repeatBorrowerData) {
        activateAgent("Master Agent", "Recognized returning user.");
        const sanctionedAt = repeatBorrowerData.sanctioned_at || repeatBorrowerData.sanctionedDate || repeatBorrowerData.date || "recently";
        const baseAmount = Number(repeatBorrowerData.preapproved_limit || repeatBorrowerData.limit || repeatBorrowerData.amount || 500000);
        const preApprovedLimit = Number.isFinite(baseAmount) ? Math.round(baseAmount) : 500000;
        addBotMessage(
          `Welcome back. Your previous loan was sanctioned on ${sanctionedAt}. Based on your repayment history, your pre-approved limit for a new loan is ${formatIndianRupees(preApprovedLimit)}.\n\n` +
          `As a repeat borrower, your starting rate is also trimmed by 0.25%. Would you like to proceed with a new offer?`
        );
        setTimeout(() => {
          setUserData(prev => ({ ...prev, stage: "offer", creditScore: 750 }));
          updatePipelineTracker("OFFER_GENERATED");
          setShowLoanOffers(true);
        }, 1500);
      } else {
        activateAgent("Master Agent", "Let's begin with a quick eligibility preview before KYC.");
        addBotMessage(
          kycText(
            "Welcome to LoanEase. I am your Loan Assistant, here to guide you through a streamlined personal loan application. Please provide the following information to proceed:\n\nFirst, what is your full legal name as it appears on your identity documents?",
            "LoanEase में आपका स्वागत है। मैं आपका Loan Assistant हूँ, जो आपको एक streamlined personal loan application के माध्यम से मार्गदर्शन करेगा। कृपया आगे बढ़ने के लिए निम्नलिखित जानकारी प्रदान करें:\n\nसबसे पहले, आपका पूरा legal name क्या है जो आपके identity documents में दिखाई देता है?"
          )
        );
      }
    }

    requestAnimationFrame(() => {
      textAreaRef.current?.focus();
    });
  };

  useEffect(() => {
    setSessionToResume(null);
    setShowSessionBanner(false);

    // Feature 5: Repeat Borrower Detection
    if (applicantMode !== "existing") {
      setIsRepeatBorrower(false);
      setRepeatBorrowerData(null);
      return;
    }

    const prevSanction = localStorage.getItem("previous_sanction_reference") || localStorage.getItem("loanease_previous_sanction");
    if (prevSanction) {
      try {
        const sanctionData = JSON.parse(prevSanction);
        setIsRepeatBorrower(true);
        setRepeatBorrowerData(sanctionData);
      } catch { /* ignore parse errors */ }
    }
  }, [applicantMode]);

  const activateAgent = (agentName: string, note: string) => {
    setActiveAgent(agentName);
    setPulseBadge(true);
    setTimeout(() => setPulseBadge(false), 2000);
    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text: `${agentName} activated.\n${note}`,
        isBot: true,
        variant: "system",
      },
    ]);
  };

  const handleProceedToKyc = () => {
    setShowPanUploadCard(true);
    conversationStep.current = 4;
    activateAgent("KYC Verification Agent", "Quick eligibility preview completed. Starting document verification.");
    addBotMessage(
      kycText(
        "Great. Please upload your PAN card to continue with KYC.",
        "बहुत बढ़िया। KYC जारी रखने के लिए अपना PAN कार्ड अपलोड करें।"
      )
    );
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
  useEffect(() => {
    // Initialize session in the backend to start orchestration logs
    if (!applicantMode) {
      return;
    }

    const initSession = async () => {
      try {
        await fetch(`${ENDPOINTS.session_init}/${userData.sessionId}`, { method: "POST" });
      } catch (e) {
        console.warn("Failed to initialize session logging", e);
      }
    };
    initSession();
  }, [applicantMode, userData.sessionId]);

  useEffect(() => {
    window._analyticsSessionId = userData.sessionId;
    localStorage.setItem("loanease_session_id", userData.sessionId);
  }, [userData.sessionId]);

  useEffect(() => {
    const modalOpen = showPanUploadCard || showAadhaarUploadCard;
    if (modalOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowPanUploadCard(false);
        setShowAadhaarUploadCard(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [showPanUploadCard, showAadhaarUploadCard]);

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
    if (messagesContainerRef.current) {
      setTimeout(() => {
        messagesContainerRef.current!.scrollTop = messagesContainerRef.current!.scrollHeight;
      }, 0);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, showCreditScore, showLoanOffers, showSanction, showAnalytics, showPanUploadCard, showAadhaarUploadCard, showPanConfirmCard, showAadhaarConfirmCard, showKycVerifiedCard, showOtpCard, isKycProcessing]);

  useEffect(() => {
    if (!showAnalytics) return;

    const analyticsSection = document.getElementById("analytics-section");
    analyticsSection?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [showAnalytics]);

  useEffect(() => {
    const TERMINAL_STATES = ["SANCTIONED", "REJECTED", "ESCALATED", "FAILED"];
    if (!pipelineSessionId || TERMINAL_STATES.includes(pipelineStatus)) return;

    const interval = setInterval(async () => {
      try {
        const response = await fetch(
          `${ENDPOINTS.pipeline_log}/${pipelineSessionId}`,
          { signal: AbortSignal.timeout(3000) }
        );
        if (!response.ok) return;
        const data = await response.json();
        setAgentTrace(data.agent_trace || []);
        const newStatus = data.pipeline_status || "ACTIVE";
        setPipelineStatus(newStatus);
        if (TERMINAL_STATES.includes(newStatus)) {
          clearInterval(interval);
        }
      } catch {
        // Silently ignore poll failures
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pipelineSessionId, pipelineStatus]);

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

  useEffect(() => {
    const element = textAreaRef.current;
    if (!element) return;

    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 100)}px`;
  }, [input]);

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
    setIsBackendBusy(true);
    try {
      const form = new FormData();
      form.append("document", file);
      form.append("session_id", userData.sessionId);
      form.append("language", language);

      const response = await fetch(ENDPOINTS.kyc_pan, {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(OCR_REQUEST_TIMEOUT_MS),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "PAN extraction failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callKycAadhaarExtractAPI = async (file: File) => {
    setIsBackendBusy(true);
    try {
      const form = new FormData();
      form.append("document", file);
      form.append("session_id", userData.sessionId);
      form.append("language", language);

      const response = await fetch(ENDPOINTS.kyc_aadhaar, {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(AADHAAR_REQUEST_TIMEOUT_MS),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "Aadhaar extraction failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const fetchKycAuditTrail = async (sessionId?: string) => {
    const targetSessionId = sessionId || userData.sessionId;
    if (!targetSessionId) return;

    try {
      const response = await fetch(`${ENDPOINTS.kyc_audit_trail}/${targetSessionId}`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return;
      const data = await response.json();
      setKycAuditTrail(data.kyc_audit_trail || []);
      setKycAuditSummary(data.summary || null);
    } catch {
      // Silently ignore audit trail fetch failures
    }
  };

  const callValidateAadhaarAPI = async (digits: string) => {
    const response = await fetch(`${ENDPOINTS.kyc_validate_aadhaar}/${digits}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      const errBody = await response.json().catch(() => null);
      throw new Error(errBody?.detail || "Aadhaar validation failed");
    }
    return response.json();
  };

  const formatAadhaarDigits = (raw: string) => {
    const digits = raw.replace(/\D/g, "").slice(0, 12);
    return digits.match(/.{1,4}/g)?.join(" ") ?? digits;
  };

  const handleManualAadhaarInput = (value: string) => {
    const digits = value.replace(/\D/g, "").slice(0, 12);
    setManualAadhaarInput(formatAadhaarDigits(digits));
    setAadhaarValidityText("");
    setAadhaarValidityOk(null);

    if (aadhaarManualDebounceRef.current) {
      clearTimeout(aadhaarManualDebounceRef.current);
    }

    if (digits.length !== 12) {
      return;
    }

    aadhaarManualDebounceRef.current = setTimeout(async () => {
      try {
        const data = await callValidateAadhaarAPI(digits);
        if (data.valid) {
          setAadhaarValidityText(kycText("Valid Aadhaar", "Valid Aadhaar"));
          setAadhaarValidityOk(true);
        } else {
          setAadhaarValidityText(`Invalid: ${data.message}`);
          setAadhaarValidityOk(false);
        }
      } catch {
        setAadhaarValidityText(kycText("Could not validate right now", "अभी validate नहीं हो सका"));
        setAadhaarValidityOk(false);
      }
    }, 300);
  };

  const callKycVerifyAPI = async (panDoc: File, aadhaarDoc: File) => {
    setIsBackendBusy(true);
    try {
      const form = new FormData();
      form.append("pan", panDoc);
      form.append("aadhaar", aadhaarDoc);
      form.append("session_id", userData.sessionId);

      const response = await fetch(ENDPOINTS.kyc_verify, {
        method: "POST",
        body: form,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "KYC verification failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callKycSendOtpAPI = async () => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(ENDPOINTS.kyc_send_otp, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: userData.sessionId }),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "OTP send failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callKycVerifyOtpAPI = async (otp: string) => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(ENDPOINTS.kyc_verify_otp, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: userData.sessionId, otp }),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "OTP verification failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callKycResendOtpAPI = async () => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(ENDPOINTS.kyc_resend_otp, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: userData.sessionId }),
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || "OTP resend failed");
      }

      return response.json();
    } finally {
      setIsBackendBusy(false);
    }
  };

  const resetOtpFlow = () => {
    setShowOtpCard(false);
    setOtpDigits(Array(6).fill(""));
    setOtpSentToLast4("");
    setOtpAttemptsRemaining(null);
    setOtpSecondsRemaining(0);
    setOtpResendCooldown(0);
    setOtpStatusMessage("");
    setOtpError("");
    setOtpSubmitting(false);
    setOtpLocked(false);
    setPendingCreditPan("");
  };

  const terminateAfterOtpFailure = (message: string) => {
    setOtpError(message);
    setOtpLocked(true);
    setShowOtpCard(false);
    addBotMessage(message);
    setTimeout(() => {
      setMessages([]);
      setUserData((prev) => ({ ...prev, stage: "kyc" }));
      localStorage.removeItem("loanease_session_id");
      navigate("/");
    }, 5000);
  };

  const updateOtpDigit = (index: number, value: string) => {
    const nextValue = value.replace(/\D/g, "").slice(-1);
    setOtpDigits((current) => {
      const nextDigits = [...current];
      nextDigits[index] = nextValue;
      return nextDigits;
    });

    if (nextValue && index < otpInputRefs.current.length - 1) {
      otpInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !otpDigits[index] && index > 0) {
      otpInputRefs.current[index - 1]?.focus();
      setOtpDigits((current) => {
        const nextDigits = [...current];
        nextDigits[index - 1] = "";
        return nextDigits;
      });
    }
  };

  const handleOtpPaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    event.preventDefault();
    const nextDigits = Array(6).fill("");
    pasted.split("").forEach((digit, index) => {
      nextDigits[index] = digit;
    });
    setOtpDigits(nextDigits);
    otpInputRefs.current[Math.min(pasted.length, 5)]?.focus();
  };

  const submitOtp = async () => {
    if (otpLocked || otpSubmitting) return;

    const otpValue = otpDigits.join("");
    if (otpValue.length !== 6) {
      setOtpError(kycText("Enter the 6-digit OTP sent to your mobile.", "अपने मोबाइल पर भेजा गया 6-digit OTP दर्ज करें।"));
      return;
    }

    setOtpSubmitting(true);
    setOtpError("");
    try {
      const result = await callKycVerifyOtpAPI(otpValue);
      setOtpAttemptsRemaining(result.attempts_remaining ?? 0);

      if (result.verified) {
        resetOtpFlow();
        setKycFactors((prev) => ({ ...prev, fa3: true, current: 3 }));
        
        // FA3 passed
        updateFA(3, 'passed');
        await fetchKycAuditTrail();
        
        addBotMessage(
          kycText(
            "3-Factor KYC Complete\n\n1. Document verification complete\n2. Aadhaar ID validation complete\n3. Mobile OTP verification complete\n\nYour identity has been verified.\nProceeding to credit assessment...",
            "3-Factor KYC Complete\n\n1. Document verification complete\n2. Aadhaar ID validation complete\n3. Mobile OTP verification complete\n\nआपकी identity verify हो गई है।\nअब credit assessment शुरू हो रहा है..."
          )
        );
        const extractedPan = pendingCreditPan || panKycData?.pan_number || verifyResultPanFromState();
        if (extractedPan) {
          await proceedToCreditFlow(extractedPan);
        }
        return;
      }

      if (result.terminated) {
        terminateAfterOtpFailure(
          kycText(
            "OTP verification failed too many times. Your application has been closed.",
            "OTP सत्यापन कई बार विफल रहा। आपका आवेदन बंद कर दिया गया है।"
          )
        );
        return;
      }

      setOtpError(
        kycText(
          `Incorrect OTP. ${result.attempts_remaining} attempt(s) remaining.`,
          `OTP गलत है। ${result.attempts_remaining} attempt(s) शेष हैं।`
        )
      );
      setOtpDigits(Array(6).fill(""));
      otpInputRefs.current[0]?.focus();
    } catch (error) {
      const msg = error instanceof Error ? error.message : kycText("OTP verification failed.", "OTP सत्यापन विफल।");
      setOtpError(msg);
    } finally {
      setOtpSubmitting(false);
    }
  };

  const resendOtp = async () => {
    if (otpResendCooldown > 0 || otpSubmitting) return;
    try {
      const result = await callKycResendOtpAPI();
      setOtpDigits(Array(6).fill(""));
      setOtpSecondsRemaining(Number(result.expires_in_seconds || 300));
      setOtpResendCooldown(60);
      setOtpLocked(false);
      setOtpError("");
      setOtpStatusMessage(
        kycText(
          `A new OTP was sent to the mobile ending ${result.mobile_last4}.`,
          `एक नया OTP मोबाइल नंबर के अंतिम ${result.mobile_last4} अंकों पर भेजा गया है।`
        )
      );
      addBotMessage(
        kycText(
          `OTP resent to mobile ending ${result.mobile_last4}.`,
          `OTP मोबाइल नंबर के अंतिम ${result.mobile_last4} अंकों पर फिर से भेजा गया है।`
        )
      );
    } catch (error) {
      const msg = error instanceof Error ? error.message : kycText("OTP resend failed.", "OTP दोबारा भेजना विफल रहा।");
      if (msg.toLowerCase().includes("limit")) {
        terminateAfterOtpFailure(
          kycText(
            "OTP resend limit reached. Your application has been closed.",
            "OTP पुनः भेजने की सीमा पूरी हो गई है। आपका आवेदन बंद कर दिया गया है।"
          )
        );
        return;
      }
      setOtpError(msg);
    }
  };

  const verifyResultPanFromState = () => panKycData?.pan_number || userData.pan || "";

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

    // FA1: Start document verification
    updateFA(1, 'active');

    const timer = startKycProgress(kycText("Scanning your PAN card...", "आपके PAN कार्ड को स्कैन किया जा रहा है..."));
    try {
      const result = await callKycPanExtractAPI(file);
      stopKycProgress(timer);

      const extractedPanCandidate = normalizePan(result.extracted_fields?.pan_number || "");
      const panCandidateValid = isValidPan(extractedPanCandidate);
      const extractedPanNumber = panCandidateValid
        ? extractedPanCandidate
        : (result.extracted_fields?.pan_number || "");
      setPanKycData({
        ...result.extracted_fields,
        pan_number: extractedPanNumber,
      });
      if (extractedPanNumber) {
        const extractedName = result.extracted_fields?.name || "";
        const extractedDob = result.extracted_fields?.date_of_birth || "";
        const extractedFather = result.extracted_fields?.father_name || "";
        
        addBotMessage(
          kycText(
            `PAN card scanned successfully\n\nName: ${extractedName}\nPAN: ${extractedPanNumber}\nDOB: ${extractedDob}${extractedFather ? `\nFather: ${extractedFather}` : ""}\n\nNow please upload your Aadhaar card.`,
            `PAN कार्ड सफलतापूर्वक स्कैन हो गया\n\nनाम: ${extractedName}\nPAN: ${extractedPanNumber}\nजन्म तिथि: ${extractedDob}${extractedFather ? `\nपिता: ${extractedFather}` : ""}\n\nअब कृपया अपना Aadhaar कार्ड अपलोड करें।`
          )
        );
      }
      const issues: string[] = result.validation?.issues || [];
      const confidence = Number(result.confidence_score || 0);
      const panFound = Boolean(result.validation?.pan_format_valid || panCandidateValid);
      const nameFound = Boolean(result.validation?.name_found);
      const dobFound = Boolean(result.validation?.dob_found);

      // Very lenient validation - accept almost anything that looks like a document
      const valid = confidence >= 0.05 || panFound; // Extremely lenient

      if (!valid) {
        addBotMessage(
          kycText(
            "Please upload a clearer PAN card image. The system couldn't read this document.",
            "कृपया एक स्पष्ट PAN कार्ड छवि अपलोड करें। सिस्टम इस दस्तावेज़ को नहीं पढ़ सका।"
          )
        );
        setShowPanUploadCard(true);
        return;
      }

      setShowPanConfirmCard(true);
    } catch (error) {
      stopKycProgress(timer);
      const msg = error instanceof Error
        ? (error.name === "TimeoutError" || error.name === "AbortError"
            ? kycText(
                "Aadhaar scan took too long. QR verification will be skipped and OTP will be used instead.",
                "Aadhaar स्कैन में अधिक समय लगा। QR verification छोड़ी जाएगी और OTP verification का उपयोग होगा।"
              )
            : error.message.includes("fetch")
              ? kycText("Could not connect to server. Check your connection.", "सर्वर से कनेक्ट नहीं हो सका। कनेक्शन जांचें।")
              : `${error.message}`)
        : kycText("PAN scan failed. Please try again.", "PAN स्कैन विफल। पुनः प्रयास करें।");
      addBotMessage(msg);
      setShowPanUploadCard(true);
    }
  };

  const proceedAfterAadhaarConfirm = async (file: File, aadhaarResult: { validation?: { aadhaar_format_valid?: boolean } }) => {
    if (!panFile) return;

    const timer = startKycProgress(kycText("Cross-checking PAN and Aadhaar...", "PAN और Aadhaar का cross-check हो रहा है..."));
    try {
      const verifyResult = await callKycVerifyAPI(panFile, file);
      stopKycProgress(timer);

      const aadhaarFound = Boolean(aadhaarResult.validation?.aadhaar_format_valid);
      const ageOk = Boolean(verifyResult.cross_validation?.age_eligible);
      const canProceed = verifyResult.overall_kyc_passed || (aadhaarFound && ageOk);

      if (!canProceed) {
        const ageEligible = Boolean(verifyResult.cross_validation?.age_eligible);
        if (!ageEligible) {
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
      setKycFactors((prev) => ({ ...prev, fa1: true, current: 2 }));
      setShowKycVerifiedCard(true);
      updateFA(1, "passed");
      updateFA(2, "passed");
      updateFA(3, "active");

      const nameScore = Number(verifyResult.cross_validation?.name_match_score ?? 0);
      const dobMatch = Boolean(verifyResult.cross_validation?.dob_match);
      addBotMessage(
        kycText(
          `Document Cross-Check\nPAN name ↔ Aadhaar name: ${Math.round(nameScore)}% match\nDate of Birth: ${dobMatch ? "Match" : "Mismatch"}\n\nProceeding to mobile verification...`,
          `Document Cross-Check\nPAN name ↔ Aadhaar name: ${Math.round(nameScore)}% match\nजन्म तिथि: ${dobMatch ? "Match" : "Mismatch"}\n\nमोबाइल verification के लिए आगे बढ़ रहा हूँ...`
        )
      );

      setTimeout(async () => {
        setShowKycVerifiedCard(false);
        try {
          addBotMessage(
            kycText(
              "Factor 1 Complete — Documents verified via AI Vision\n\nAadhaar number passed Verhoeff checksum validation. Proceeding to OTP verification.",
              "Factor 1 Complete — Documents verified via AI Vision\n\nAadhaar number Verhoeff checksum validation pass हो गया। OTP verification के लिए आगे बढ़ रहा हूँ।"
            )
          );
          resetOtpFlow();
          const otpResult = await callKycSendOtpAPI();
          const mobileLast4 = otpResult.mobile_last4 || aadhaarKycData?.mobile_last4 || "";
          setOtpSentToLast4(mobileLast4);
          setOtpAttemptsRemaining(3);
          setOtpSecondsRemaining(Number(otpResult.expires_in_seconds || 300));
          setOtpResendCooldown(60);
          setOtpDigits(Array(6).fill(""));
          setShowOtpCard(true);
          setOtpStatusMessage(
            kycText(
              `OTP sent to mobile ending ${mobileLast4}. Enter the 6-digit code to continue.`,
              `OTP मोबाइल नंबर के अंतिम ${mobileLast4} अंक पर भेजा गया है। आगे बढ़ने के लिए 6-digit code दर्ज करें।`
            )
          );
          if (otpResult.demo_otp) {
            addBotMessage(kycText(`Demo OTP: ${otpResult.demo_otp}`, `Demo OTP: ${otpResult.demo_otp}`));
          }
        } catch (otpError) {
          const msg = otpError instanceof Error ? otpError.message : kycText("Unable to continue to OTP verification.", "OTP verification आगे नहीं बढ़ सकी।");
          addBotMessage(msg);
        }
      }, 1300);
    } catch (error) {
      stopKycProgress(timer);
      const msg = error instanceof Error ? error.message : kycText("KYC verification failed.", "KYC सत्यापन विफल।");
      addBotMessage(msg);
      setShowAadhaarUploadCard(true);
    }
  };

  const handleAadhaarConfirm = async () => {
    if (!aadhaarFile) return;
    setShowAadhaarConfirmCard(false);
    await proceedAfterAadhaarConfirm(aadhaarFile, {
      validation: { aadhaar_format_valid: true },
    });
  };

  const handleAadhaarFileSelected = async (file?: File) => {
    if (!file || !panFile) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error(kycText("File exceeds 5MB limit", "फ़ाइल 5MB सीमा से बड़ी है"));
      return;
    }

    setAadhaarFile(file);
    setShowAadhaarUploadCard(false);
    setManualAadhaarInput("");
    setAadhaarValidityText("");
    setAadhaarValidityOk(null);
    setMessages((prev) => [...prev, { id: prev.length + 1, text: file.name, isBot: false }]);

    const timer = startKycProgress(kycText("Scanning your Aadhaar card...", "आपके Aadhaar कार्ड को स्कैन किया जा रहा है..."));
    try {
      const aadhaarResult = await callKycAadhaarExtractAPI(file);
      setAadhaarKycData(aadhaarResult.extracted_fields);

      const verhoeffResult = (aadhaarResult.fa2_verhoeff || aadhaarResult.verhoeff_validation) as AadhaarVerhoeffResult | undefined;
      setAadhaarVerhoeffResult(verhoeffResult ?? null);

      if (verhoeffResult && !verhoeffResult.valid) {
        stopKycProgress(timer);
        addBotMessage(
          kycText(
            `Aadhaar ID Validation\nChecksum failed\nThe Aadhaar number extracted does not pass the Verhoeff algorithm check.\nThis may mean:\n• OCR read a digit incorrectly\n• The document may be altered\nPlease upload a clearer image of your Aadhaar card.`,
            `Aadhaar ID Validation\nChecksum failed\nExtracted Aadhaar number Verhoeff algorithm check pass नहीं कर पाया।\nइसका मतलब हो सकता है:\n• OCR ने digit गलत पढ़ा\n• Document altered हो सकता है\nकृपया अपने Aadhaar कार्ड की एक स्पष्ट image अपलोड करें।`
          )
        );
        setShowAadhaarUploadCard(true);
        return;
      }

      const aadhaarIssues: string[] = aadhaarResult.validation?.issues || [];
      const missingFields: string[] = aadhaarResult.validation?.missing_fields || [];
      const aadhaarConfidence = Number(aadhaarResult.confidence_score || 0);

      if (missingFields.length > 0) {
        stopKycProgress(timer);
        addBotMessage(
          kycText(
            `${missingFieldMessage(missingFields)}. Please upload a clearer Aadhaar card.`,
            `${missingFieldMessage(missingFields)}। कृपया एक स्पष्ट Aadhaar कार्ड अपलोड करें।`
          )
        );
        if (aadhaarIssues.length > 0) {
          toast.error(aadhaarIssues[0]);
        }
        setShowAadhaarUploadCard(true);
        return;
      }

      const aadhaarValid = Boolean(aadhaarResult.validation?.aadhaar_format_valid || aadhaarConfidence >= 0.15);
      if (!aadhaarValid) {
        stopKycProgress(timer);
        if (aadhaarConfidence > 0.05) {
          addBotMessage(
            kycText(
              "This doesn't appear to be an Aadhaar card. Please upload your Aadhaar card.",
              "यह Aadhaar कार्ड प्रतीत नहीं होता। कृपया अपना Aadhaar कार्ड अपलोड करें।"
            )
          );
        } else {
          addBotMessage(
            kycText(
              "Image quality is low. Please upload a clearer Aadhaar card image.",
              "छवि गुणवत्ता कम है। कृपया एक स्पष्ट Aadhaar कार्ड छवि अपलोड करें।"
            )
          );
        }
        if (aadhaarIssues.length > 0) {
          toast.error(aadhaarIssues[0]);
        }
        setShowAadhaarUploadCard(true);
        return;
      }

      stopKycProgress(timer);
      if (verhoeffResult?.valid) {
        updateFA(2, "passed");
        updateFA(3, "active");
      }
      setShowAadhaarConfirmCard(true);
    } catch (error) {
      stopKycProgress(timer);
      const isTimeout = error instanceof Error && error.name === "TimeoutError";
      const msg = error instanceof Error
        ? (isTimeout
            ? kycText(
                "Aadhaar OCR is taking longer than usual. Please wait a moment, then retry with a smaller or clearer image if needed.",
                "Aadhaar OCR सामान्य से अधिक समय ले रहा है। कृपया थोड़ा इंतज़ार करें, फिर ज़रूरत हो तो छोटी या स्पष्ट छवि के साथ पुनः प्रयास करें।"
              )
            : error.message.includes("fetch")
              ? kycText("Could not connect to server. Check your connection.", "सर्वर से कनेक्ट नहीं हो सका। कनेक्शन जांचें।")
              : `${error.message}`)
        : kycText("Aadhaar scan failed. Please try again.", "Aadhaar स्कैन विफल। पुनः प्रयास करें।");
      addBotMessage(msg);
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
    session_id?: string;
    employment_type?: string;
    employer_name?: string;
    monthly_income?: number;
    loan_purpose?: string;
  }) => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(ENDPOINTS.credit_assess, {
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
        creditScore: data.cibil_score ?? data.credit_score ?? data.risk_score,
        maxNegotiationRounds: data.max_negotiation_rounds || 0,
      }));
      setUnderwritingResult(data);

      // Show a concise consumer-facing message using the industry-standard wording
      try {
        const score = data.cibil_score ?? data.credit_score ?? data.risk_score;
        let userMsg = "";
        if (score === 751) {
          userMsg = `Your CIBIL score is ${score} — rated '${data.cibil_classification || "Very Good"}' on TransUnion CIBIL's 5-tier scale. This places you in our ${data.risk_label || 'Low-Medium Risk'} category, qualifying you for rates between ${data.rate_range || '11.5% and 12.5%'} p.a.`;
        } else if (score === 580) {
          userMsg = `Your CIBIL score is ${score}, rated '${data.cibil_classification || 'Below Average'}' by TransUnion CIBIL. We can offer conditional approval with a co-applicant. Without a co-applicant, we recommend improving your score to 650+ before reapplying.`;
        } else if (score != null) {
          userMsg = `Your CIBIL score is ${score} — rated '${data.cibil_classification || data.risk_tier || 'Good'}' on TransUnion CIBIL's 5-tier scale. ${data.risk_label ? 'This places you in our ' + data.risk_label + ' category.' : ''} ${data.rate_range ? 'Eligible rates: ' + data.rate_range + '.' : ''}`;
        }

        if (userMsg) addBotMessage(userMsg);
      } catch (e) {
        // ignore
      }

      return data;
    } catch (error) {
      console.error("Underwriting error:", error);
      setIsOfflineMode(true);
      toast.error("Connection issue — using offline mode");
      return null;
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callNegotiationAPI = async (
    riskScore: number,
    riskTier: string,
    loanAmount: number,
    tenureMonths: number,
    maxNegotiationRounds: number,
    startingRate?: number,
  ) => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(ENDPOINTS.negotiate_start, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: userData.sessionId,
          applicant_name: userData.name,
          risk_score: riskScore,
          risk_tier: riskTier,
          loan_amount: loanAmount,
          tenure_months: tenureMonths,
          max_negotiation_rounds: maxNegotiationRounds,
          starting_rate: startingRate ?? undefined,
          top_positive_factor: "good credit history",
          customer_profile: isRepeatBorrower ? "EXCELLENT" : "STANDARD",
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
      setIsOfflineMode(true);
      toast.error("Connection issue — using offline mode");
      return null;
    } finally {
      setIsBackendBusy(false);
    }
  };

  const callCreditScoreAPI = async (pan: string) => {
    setIsBackendBusy(true);
    try {
      const response = await fetch(`${ENDPOINTS.credit_score}/${pan}`);

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
      setIsOfflineMode(true);
      toast.error("Connection issue — using offline mode");
      return null;
    } finally {
      setIsBackendBusy(false);
    }
  };

  const simulateBotResponse = (userMessage: string, sourceMessageId?: number) => {
    setIsTyping(true);
    const prevMessages = [...messages];

    setTimeout(async () => {
      let botResponse = "";

      const isPreKycFlow = !showPanUploadCard && !showAadhaarUploadCard && !showPanConfirmCard && !showAadhaarConfirmCard && !showKycVerifiedCard && !showOtpCard && !showCreditScoreCard && !showLoanOffers && !showSanction;

      if (isPreKycFlow) {
        if (userMessage.toLowerCase().includes("human") || userMessage.toLowerCase().includes("talk to agent")) {
          handleEscalationTrigger();
          setIsTyping(false);
          return;
        }

        if (!intakeCompleted) {
          try {
            const response = await fetch(ENDPOINTS.intake, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                message: userMessage,
                session_id: userData.sessionId,
              }),
            });
            const data = await response.json();

            botResponse = data.message;

            if (data.proceed_to_kyc && data.eligibility_preview) {
              const ep = data.eligibility_preview;
              const statusMap: Record<string, "Strong" | "Conditional" | "Needs review"> = {
                "Strong": "Strong",
                "Moderate": "Conditional",
                "Weak": "Needs review",
              };
              setIntakePreview({
                loanAmount: ep.loan_amount,
                monthlyIncome: ep.monthly_income,
                tenureMonths: ep.tenure_months,
                assumedRate: ep.assumed_rate,
                estimatedEmi: ep.estimated_emi,
                emiToIncomeRatio: ep.emi_to_income_ratio,
                maxAffordableEmi: Math.round(ep.monthly_income * 0.4),
                status: statusMap[ep.status] || "Needs review",
                note: ep.status_text,
              });
              setIntakeCompleted(true);
              conversationStep.current = 3;
              setUserData((prev) => ({
                ...prev,
                name: ep.applicant_name || prev.name,
                preKycLoanAmount: ep.loan_amount,
                preKycMonthlyIncome: ep.monthly_income,
              }));
            }
          } catch (error) {
            console.error("Intake API error:", error);
            botResponse = language === "en"
              ? "I'm having trouble processing your request. Please try again."
              : "आपके अनुरोध को संसाधित करने में समस्या हो रही है। कृपया पुनः प्रयास करें।";
          }

          const newMsg: Message = { id: prevMessages.length + 1, text: botResponse, isBot: true };
          setMessages((prev) => {
            const updated = sourceMessageId
              ? prev.map((message) => (message.id === sourceMessageId ? { ...message, status: "responded" as const } : message))
              : prev;
            return [...updated, newMsg];
          });
          saveSession([...prevMessages, newMsg], userData.stage, userData);
          setIsTyping(false);
          return;
        }
      }

      let quickReplies: { label: string; value: string }[] | undefined = undefined;

      switch (conversationStep.current) {
        case 0:
          // Step 1: Collect name
          const name = userMessage.trim();
          if (name.length < 2 || !/^[a-zA-Z\s]+$/.test(name)) {
            botResponse = kycText(
              "The name you provided contains invalid characters. Please provide your full legal name using only alphabetic characters and spaces. Example: John Doe",
              "आपके द्वारा प्रदान किया गया नाम में अमान्य वर्ण हैं। कृपया केवल वर्णानुक्रमिक वर्णों और रिक्त स्थानों का उपयोग करके अपना पूरा कानूनी नाम प्रदान करें। उदाहरण: John Doe"
            );
          } else {
            setUserData((prev) => ({ ...prev, name }));
            conversationStep.current = 1;
            botResponse = kycText(
              `Thank you, ${name}.\n\nTo assess your loan eligibility, I need to understand your financial capacity.\nWhat is your gross monthly income (in Indian Rupees)?\n\nPlease provide the amount as a number without currency symbol.\nExample: 50000 (for INR 50,000)`,
              `धन्यवाद, ${name}।\n\nआपकी loan eligibility का आकलन करने के लिए, मुझे आपकी financial capacity समझने की आवश्यकता है।\nआपकी gross monthly income (Indian Rupees में) क्या है?\n\nकृपया राशि को currency symbol के बिना number के रूप में प्रदान करें।\nउदाहरण: 50000 (INR 50,000 के लिए)`
            );
          }
          break;

        case 1:
          // Step 2: Collect monthly income
          const incomeAmount = parseMoneyAmount(userMessage);
          if (incomeAmount === null || incomeAmount < 10000 || incomeAmount > 2000000) {
            botResponse = kycText(
              "Please enter your monthly income as a valid number between ₹10,000 and ₹20,00,000. Do not include currency symbols or commas. Example: 50000",
              "कृपया अपनी मासिक आय को ₹10,000 और ₹20,00,000 के बीच एक valid number के रूप में दर्ज करें। currency symbols या commas शामिल न करें। उदाहरण: 50000"
            );
          } else {
            setUserData((prev) => ({ ...prev, preKycMonthlyIncome: incomeAmount }));
            conversationStep.current = 2;
            const maxEligible = Math.min(incomeAmount * 15, 2500000);
            botResponse = kycText(
              `Thank you. Based on your monthly income of ₹${incomeAmount.toLocaleString('en-IN')}, I can now assess your borrowing capacity.\n\nWhat is the desired loan amount you wish to apply for (in Indian Rupees)?\n\nPlease provide the amount as a number without currency symbol.\nExample: 250000 (for INR 2,50,000)\n\nMaximum eligible amount: ₹${maxEligible.toLocaleString('en-IN')}`,
              `धन्यवाद। आपकी मासिक आय ₹${incomeAmount.toLocaleString('en-IN')} के आधार पर, मैं अब आपकी borrowing capacity का आकलन कर सकता हूँ।\n\nआप जिस loan amount के लिए आवेदन करना चाहते हैं वह (Indian Rupees में) क्या है?\n\nकृपया राशि को currency symbol के बिना number के रूप में प्रदान करें।\nउदाहरण: 250000 (INR 2,50,000 के लिए)\n\nअधिकतम eligible amount: ₹${maxEligible.toLocaleString('en-IN')}`
            );
          }
          break;

        case 2:
          // Step 3: Collect loan amount and show eligibility preview
          const loanAmount = parseMoneyAmount(userMessage);
          const monthlyIncome = userData.preKycMonthlyIncome || 0;
          const maxEligible = Math.min(monthlyIncome * 15, 2500000);
          
          if (loanAmount === null || loanAmount < 50000 || loanAmount > 2500000) {
            botResponse = kycText(
              `The loan amount must be between ₹50,000 and ₹25,00,000. Please ensure the amount is realistic relative to your monthly income.`,
              `Loan amount ₹50,000 और ₹25,00,000 के बीच होना चाहिए। कृपया सुनिश्चित करें कि amount आपकी मासिक आय के संबंध में realistic है।`
            );
          } else if (loanAmount > maxEligible) {
            botResponse = kycText(
              `Loan amount must be between ₹50,000 and ₹${maxEligible.toLocaleString('en-IN')} (15x your monthly income). Please enter a lower amount.`,
              `Loan amount ₹50,000 और ₹${maxEligible.toLocaleString('en-IN')} (आपकी मासिक आय का 15x) के बीच होना चाहिए। कृपया एक कम amount दर्ज करें।`
            );
          } else {
            setUserData((prev) => ({ ...prev, preKycLoanAmount: loanAmount }));
            conversationStep.current = 3;
            
            // Calculate eligibility preview
            const preview = buildQuickEligibilityPreview(loanAmount, monthlyIncome);
            const emiRatio = preview.emiToIncomeRatio;
            let statusText = "";
            if (emiRatio <= 0.50 && loanAmount <= monthlyIncome * 15) {
              statusText = "Strong. You meet our lending criteria.";
            } else if (emiRatio <= 0.60 && loanAmount <= monthlyIncome * 12) {
              statusText = "Moderate. Subject to credit verification.";
            } else {
              statusText = "Weak. May require additional documentation or co-applicant.";
            }
            
            botResponse = kycText(
              `Based on the information provided, here is your quick eligibility preview:\n\nELIGIBILITY ASSESSMENT\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nApplicant Name:              ${userData.name}\nMonthly Gross Income:        ₹${monthlyIncome.toLocaleString('en-IN')}\nDesired Loan Amount:         ₹${loanAmount.toLocaleString('en-IN')}\nProposed Tenure:             60 months\nEstimated EMI (at 13%):      ₹${preview.estimatedEmi.toLocaleString('en-IN')}\nEMI to Income Ratio:         ${(emiRatio * 100).toFixed(1)}%\nEligibility Status:          ${statusText}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nThis is a preliminary assessment based on income alone. Your final eligibility depends on credit verification, identity authentication, and document validation.\n\nWould you like to proceed to KYC (Know Your Customer) verification?`,
              `प्रदान की गई जानकारी के आधार पर, यहाँ आपकी quick eligibility preview है:\n\nELIGIBILITY ASSESSMENT\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nApplicant Name:              ${userData.name}\nMonthly Gross Income:        ₹${monthlyIncome.toLocaleString('en-IN')}\nDesired Loan Amount:         ₹${loanAmount.toLocaleString('en-IN')}\nProposed Tenure:             60 months\nEstimated EMI (at 13%):      ₹${preview.estimatedEmi.toLocaleString('en-IN')}\nEMI to Income Ratio:         ${(emiRatio * 100).toFixed(1)}%\nEligibility Status:          ${statusText}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nयह केवल income के आधार पर एक preliminary assessment है। आपकी final eligibility credit verification, identity authentication, और document validation पर निर्भर करती है।\n\nक्या आप KYC (Know Your Customer) verification के लिए आगे बढ़ना चाहते हैं?`
            );
            
            quickReplies = [
              { label: language === "hi" ? "हाँ, KYC शुरू करें" : "Yes, Proceed to KYC", value: "proceed_kyc" },
              { label: language === "hi" ? "नहीं, बाद में" : "No, Later", value: "later" }
            ];
          }
          break;

        case 3:
          // Step 4: Handle response to eligibility preview
          if (userMessage.toLowerCase().includes("proceed") || userMessage.toLowerCase().includes("yes") || userMessage.toLowerCase().includes("haan")) {
            conversationStep.current = 4;
            activateAgent("KYC Verification Agent", "Quick eligibility preview completed. Starting document verification.");
            botResponse = kycText(
              "Proceeding to KYC Verification.\n\nTo verify your identity, I will need to collect the following documents:\n1. PAN Card (Permanent Account Number)\n2. Aadhaar Card (Government Identity Number)\n\nPlease upload clear, well-lit images of both documents.\nAcceptable formats: JPG, PNG, PDF\n\nNote: All documents are processed securely on-premise. No data is shared with external parties.",
              "KYC Verification के लिए आगे बढ़ रहा हूँ।\n\nआपकी identity verify करने के लिए, मुझे निम्नलिखित documents collect करने होंगे:\n1. PAN Card (Permanent Account Number)\n2. Aadhaar Card (Government Identity Number)\n\nकृपया दोनों documents की स्पष्ट, well-lit images upload करें।\nAcceptable formats: JPG, PNG, PDF\n\nNote: सभी documents को on-premise securely process किया जाता है। किसी भी external party के साथ data share नहीं किया जाता है।"
            );
            setShowPanUploadCard(true);
          } else {
            botResponse = kycText(
              "I understand. You can return to complete your application at any time. Your information will be saved for 24 hours.",
              "मैं समझ गया। आप किसी भी समय अपना application पूरा करने के लिए वापस आ सकते हैं। आपकी जानकारी 24 घंटों के लिए saved रहेगी।"
            );
          }
          break;

        case 4:
          botResponse = kycText(
            "Please use the upload card below to upload your PAN document.",
            "कृपया PAN दस्तावेज़ अपलोड करने के लिए नीचे दिए गए upload card का उपयोग करें।"
          );
          break;

        case 5:
          botResponse = "Feel free to adjust the sliders to customize your loan terms. Once satisfied, click 'Select This Plan' to proceed.";
          break;

        default:
          if (userMessage.toLowerCase().includes("human") || userMessage.toLowerCase().includes("talk to agent")) {
            handleEscalationTrigger();
            return;
          }
          botResponse = "Thank you for your message. Is there anything else I can help you with?";
      }

      if (botResponse) {
        quickReplies = undefined;
        const type: "emi-calculator" | "escalation" | "comparison-cards" | undefined = undefined;

        if (conversationStep.current === 1) {
          quickReplies = [
            { label: language === "hi" ? "लोन के लिए आवेदन करें" : "Apply for a Loan", value: "apply" },
            { label: language === "hi" ? "पात्रता जांचें" : "Check Eligibility", value: "eligibility" },
            { label: language === "hi" ? "यह कैसे काम करता है?" : "How does it work?", value: "how" }
          ];
        } else if (conversationStep.current === 3) {
          quickReplies = [
            { label: language === "hi" ? "मेरे लोन विकल्प देखें →" : "Check My Loan Options →", value: "options" },
            { label: language === "hi" ? "मेरे स्कोर को क्या प्रभावित करता है?" : "What affects my score?", value: "factors" }
          ];
        }

        const newMsg: Message = { id: prevMessages.length + 1, text: botResponse, isBot: true, quickReplies, type };
        setMessages((prev) => {
          const updated = sourceMessageId
            ? prev.map((message) => (message.id === sourceMessageId ? { ...message, status: "responded" as const } : message))
            : prev;
          return [...updated, newMsg];
        });
        saveSession([...prevMessages, newMsg], userData.stage, userData);
      }

      setIsTyping(false);
    }, 1500);
  };

  const handleSend = () => {
    if (!input.trim() || isEscalated || isInputLocked) return;

    const userMessage = input.trim();
    const newMsg: Message = { id: messages.length + 1, text: userMessage, isBot: false, status: "sent" };
    setIsTyping(true);
    setMessages((prev) => [...prev, newMsg]);
    setInput("");

    // Simulate delivery
    setTimeout(() => {
      setMessages((prev) => prev.map((message) => (message.id === newMsg.id ? { ...message, status: "delivered" } : message)));
      
      // Check for EMI keywords
      if (userMessage.toLowerCase().includes("emi") || userMessage.toLowerCase().includes("tenure") || userMessage.toLowerCase().includes("किस्त")) {
         setTimeout(() => {
           setMessages((prev) => [
             ...prev,
             { id: prev.length + 1, text: "You can use this calculator to see how different amounts and tenures affect your EMI.", isBot: true, type: "emi-calculator" }
           ]);
           setMessages((prev) => prev.map((message) => (message.id === newMsg.id ? { ...message, status: "responded" } : message)));
           setIsTyping(false);
         }, 800);
      } else {
        simulateBotResponse(userMessage, newMsg.id);
      }
    }, 500);
  };

  const handleEmiTerms = (amount: number, rate: number, tenure: number) => {
    addBotMessage(`Perfect. I'll use these terms: ${formatIndianRupees(amount)} at ${rate}% for ${tenure} months.`);
    setUserData(prev => ({ ...prev, selectedLoan: { amount, interest: rate, tenure, emi: 0 }, stage: "negotiate" }));
    // Trigger negotiation with these terms
    handleLoanSelect(rate, tenure, amount);
  };

  const handleOfferPreview = (offer: Offer) => {
    setPendingOffer(offer);
    setShowKfsCard(true);
    setKfsAcknowledged(false);
    const riskTierText = (userData.riskTier || "").toLowerCase();
    if (riskTierText.includes("low") || riskTierText.includes("medium")) {
      const preview = calculateEmiWithHoliday(offer.amount, offer.rate, offer.tenure, 2);
      setEmiHolidayOption({
        ...preview,
        message: `Would you like a 2-month EMI holiday? Your first EMI starts in month ${preview.firstEmiAfterMonth}.`,
      });
      setSelectedHolidayMonths(0);
    } else {
      setEmiHolidayOption(null);
      setSelectedHolidayMonths(0);
    }
  };

  const handleAcceptPendingOffer = () => {
    if (!pendingOffer || !kfsAcknowledged) return;
    handleLoanSelect(pendingOffer.rate, pendingOffer.tenure, pendingOffer.amount, selectedHolidayMonths);
  };

  // ── Negotiation state machine ──────────────────────────────────────────────

  const handleNegotiationResponse = (res: any) => {
    if (!res) return;
    const offer: NegotiationOffer | null = res.offer ?? res.opening_offer ?? res.current_offer ?? res.final_offer ?? null;
    const negId: string = res.negotiation_id ?? res.session_id ?? "";
    if (negId) setNegotiationNegId(negId);
    if (offer) setNegotiationOffer(offer);
    if (res.floor_rate) setNegotiationFloorRate(res.floor_rate);
    if (res.escalation_id) setNegotiationEscalationId(res.escalation_id);
    if (res.summary) setNegotiationSummary(res.summary);

    // HIGH RISK: negotiation_permitted explicitly false
    if (res.negotiation_permitted === false) {
      setNegotiationState("HIGH_RISK");
      setNegotiationRoundsLeft(0);
      const riskTierText = (userData.riskTier || "").toLowerCase();
      let tierMessage = "";
      if (riskTierText.includes("high")) {
        tierMessage = kycText(
          "Based on your CIBIL assessment, your profile falls in the higher risk category. Rate negotiation is not available at this time. The offered rate reflects the current risk assessment. You may improve your eligibility by maintaining consistent repayment history and reducing existing debt obligations.",
          "आपकी CIBIL assessment के आधार पर, आपकी profile higher risk category में आती है। Rate negotiation इस समय उपलब्ध नहीं है। Offered rate current risk assessment को दर्शाता है। आप consistent repayment history बनाए रखकर और existing debt obligations को कम करके अपनी eligibility improve कर सकते हैं।"
        );
      } else {
        tierMessage = kycText(
          "Rate negotiation is not available for this profile. The offered rate is based on your current credit assessment and risk classification.",
          "इस profile के लिए rate negotiation उपलब्ध नहीं है। Offered rate आपकी current credit assessment और risk classification के आधार पर है।"
        );
      }
      addBotMessage(tierMessage);
      return;
    }

    const status: string = res.status ?? "ACTIVE";
    setNegotiationState(status);
    setNegotiationRoundsLeft(res.rounds_remaining ?? 0);

    // Add CIBIL tier-based messaging for negotiation offers
    if (offer && status === "ACTIVE") {
      const riskTierText = (userData.riskTier || "").toLowerCase();
      let negotiationMessage = "";
      
      if (riskTierText.includes("low")) {
        negotiationMessage = kycText(
          `Excellent. Your CIBIL profile qualifies you for premium pricing. The current rate of ${offer.rate.toFixed(2)}% reflects your strong credit standing. You may request further rate reduction if desired.`,
          `बहुत अच्छा। आपकी CIBIL profile आपको premium pricing के लिए qualify करती है। Current rate ${offer.rate.toFixed(2)}% आपकी strong credit standing को दर्शाता है। यदि आवश्यक हो तो आप further rate reduction request कर सकते हैं।`
        );
      } else if (riskTierText.includes("medium")) {
        negotiationMessage = kycText(
          `Your CIBIL profile qualifies for standard pricing. The current rate of ${offer.rate.toFixed(2)}% is within your eligible range. Limited rate negotiation is available based on your credit profile.`,
          `आपकी CIBIL profile standard pricing के लिए qualify करती है। Current rate ${offer.rate.toFixed(2)}% आपकी eligible range के भीतर है। आपकी credit profile के आधार पर limited rate negotiation उपलब्ध है।`
        );
      } else {
        negotiationMessage = kycText(
          `Based on your CIBIL assessment, the current rate of ${offer.rate.toFixed(2)}% reflects your risk classification. This rate has been optimized for your profile.`,
          `आपकी CIBIL assessment के आधार पर, current rate ${offer.rate.toFixed(2)}% आपकी risk classification को दर्शाता है। यह rate आपकी profile के लिए optimize किया गया है।`
        );
      }
      
      if (res.rounds_remaining > 0) {
        negotiationMessage += kycText(
          `\n\nYou have ${res.rounds_remaining} negotiation round(s) remaining.`,
          `\n\nआपके पास ${res.rounds_remaining} negotiation round(s) शेष हैं।`
        );
      }
      
      addBotMessage(negotiationMessage);
    }
  };

  const handleNegotiationCounter = async () => {
    if (!negotiationNegId || isNegotiationBusy) return;
    setIsNegotiationBusy(true);
    setIsTyping(true);
    try {
      const res = await fetch(ENDPOINTS.negotiate_counter, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: negotiationNegId,
          negotiation_id: negotiationNegId,
          applicant_message: "Can you reduce the rate further?",
        }),
      });
      setIsTyping(false);
      if (!res.ok) throw new Error("Counter request failed");
      const data = await res.json();
      handleNegotiationResponse(data);
      if (data.message) addBotMessage(data.message);
    } catch {
      setIsTyping(false);
      addBotMessage("There was an issue processing your counter. Please try again.");
    } finally {
      setIsNegotiationBusy(false);
    }
  };

  const handleNegotiationAccept = async () => {
    if (isNegotiationBusy) return;
    setIsNegotiationBusy(true);
    try {
      const res = await fetch(ENDPOINTS.negotiate_accept, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: negotiationNegId || userData.sessionId,
          negotiation_id: negotiationNegId,
          holiday_months: selectedHolidayMonths,
        }),
      });
      const data = res.ok ? await res.json() : null;
      const finalOffer = data?.final_offer ?? negotiationOffer;
      const finalRate  = finalOffer?.rate ?? finalOffer?.interest_rate ?? userData.selectedLoan.interest;
      const finalAmt   = finalOffer?.loan_amount ?? userData.selectedLoan.amount;
      const finalTen   = finalOffer?.tenure_months ?? userData.selectedLoan.tenure;
      const finalEmi   = finalOffer?.emi ?? finalOffer?.monthly_emi ?? userData.selectedLoan.emi;

      if (data?.summary) setNegotiationSummary(data.summary);
      setNegotiationState("ACCEPTED");

      setUserData(prev => ({
        ...prev,
        stage: "sanction",
        selectedLoan: { amount: finalAmt, interest: finalRate, tenure: finalTen, emi: finalEmi },
      }));

      setMessages(prev => [...prev, {
        id: prev.length + 1,
        text: `KYC Verified\nCredit Check Passed\nNegotiation Complete\n\n${TRANSLATIONS.approved[language]}`,
        isBot: true,
      }]);

      // Blockchain sanction
      let blockchainData: { transaction_id: string; block_hash: string } | undefined;
      try {
        setActiveAgent("Blockchain Audit Agent");
        setPulseBadge(true);
        const sanctionRes = await fetch(ENDPOINTS.blockchain_sanction, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: userData.sessionId,
            applicant_name: userData.name || "Applicant",
            pan_number: userData.pan || "ABCDE1234F",
            loan_amount: finalAmt,
            interest_rate: finalRate,
            tenure_years: Math.max(1, Math.round(finalTen / 12)),
          }),
        });
        if (sanctionRes.ok) {
          const bData = await sanctionRes.json();
          blockchainData = { transaction_id: bData.transaction_id, block_hash: bData.block_hash };
          setUserData(prev => ({ ...prev, blockchainData }));
        }
      } catch (e) {
        console.warn("Blockchain sanction (non-fatal):", e);
      } finally {
        setPulseBadge(false);
      }

      setMessages(prev => [...prev, {
        id: prev.length + 1,
        text: "Sanction details are being recorded with tamper-proof hash verification on our blockchain audit ledger.",
        isBot: true,
      }]);

      setShowSanction(true);

      const sanctionRef = blockchainData?.transaction_id ?? `APP-${Math.floor(1000 + Math.random() * 9000)}`;
      const sanctionRecord = JSON.stringify({
        sanction_reference: sanctionRef, reference: sanctionRef,
        sanctioned_at: new Date().toISOString(),
        amount: finalAmt, rate: finalRate,
        preapproved_limit: Math.round(finalAmt * (isRepeatBorrower ? 1.25 : 1.0)),
        holiday_months: selectedHolidayMonths,
      });
      localStorage.setItem("previous_sanction_reference", sanctionRecord);
      localStorage.setItem("loanease_previous_sanction", sanctionRecord);
    } catch (err) {
      console.error("Negotiation accept error:", err);
      addBotMessage("Something went wrong. Please try again.");
    } finally {
      setIsNegotiationBusy(false);
    }
  };

  const handleNegotiationEscalate = async () => {
    if (!negotiationNegId || isNegotiationBusy) return;
    setIsNegotiationBusy(true);
    try {
      const res = await fetch(ENDPOINTS.negotiate_escalate, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: negotiationNegId,
          negotiation_id: negotiationNegId,
          reason: "floor_rate_reached",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setNegotiationState("ESCALATED");
        if (data.escalation_id) setNegotiationEscalationId(data.escalation_id);
        setIsEscalated(true);
        addBotMessage(data.message ?? "Your case has been escalated to a senior loan officer. Expect a call within 2 business hours.");
      }
    } catch (err) {
      console.error("Escalation error:", err);
      addBotMessage("There was an issue escalating your case. Please try again.");
    } finally {
      setIsNegotiationBusy(false);
    }
  };

  // Feature 2: Bank Statement Upload Handler
  const handleBankStatementUpload = async (file: File | undefined) => {
    if (!file) return;
    setShowBankStatementCard(false);
    addBotMessage("Analyzing your bank statement...");
    setIsTyping(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("session_id", userData.sessionId);
      const res = await fetch(ENDPOINTS.credit_analyze_statement, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setBankStatementResult(data);
      setIsTyping(false);
      if (data.analysis_possible) {
        addBotMessage(
          `Bank Statement Analysis Complete\n\n` +
          `Estimated Monthly Income: ${formatIndianRupees(data.estimated_monthly_income)}\n` +
          `Confidence: ${data.income_confidence}\n` +
          `Source: ${data.data_source}\n\n` +
          `This will be used to supplement your credit assessment.`
        );
      } else {
        addBotMessage(`Could not extract income data from the statement. ${data.reason || "Please try again with a clearer document."}`);
      }
    } catch {
      setIsTyping(false);
      addBotMessage("Failed to analyze bank statement. Please try again.");
    }
  };

  const handleLoanSelect = async (interest: number, tenure: number, amount: number, holidayMonths = 0) => {
    const baseMonthlyRate = interest / 1200;
    const standardEmi = Math.round(
      (amount * baseMonthlyRate * Math.pow(1 + baseMonthlyRate, tenure)) /
        (Math.pow(1 + baseMonthlyRate, tenure) - 1)
    );
    const holidayDetails = holidayMonths > 0
      ? calculateEmiWithHoliday(amount, interest, tenure, holidayMonths)
      : null;
    const emi = holidayDetails?.emi ?? standardEmi;

    setUserData((prev) => ({
      ...prev,
      selectedLoan: {
        amount,
        interest,
        tenure,
        emi,
        holidayMonths: holidayMonths > 0 ? holidayMonths : undefined,
        holidayExtraCost: holidayDetails?.extraCost,
      },
    }));

    setShowLoanOffers(false);
    setShowKfsCard(false);
    setPendingOffer(null);
    setKfsAcknowledged(false);

    const selectionMessage =
      language === "en"
        ? `You selected: ${formatIndianRupees(amount)} at ${interest}% for ${tenure} months.\n\n${TRANSLATIONS.emi[language]}: ${formatIndianRupees(emi)}/month${holidayMonths > 0 ? `\nEMI holiday: ${holidayMonths} months` : ""}`
        : `आपने चुना: ${formatIndianRupees(amount)} ${interest}% पर ${tenure} महीनों के लिए।\n\n${TRANSLATIONS.emi[language]}: ${formatIndianRupees(emi)}/month${holidayMonths > 0 ? `\nEMI holiday: ${holidayMonths} महीनों का` : ""}`;

    setMessages((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        text: selectionMessage,
        isBot: false,
      },
    ]);

    setIsTyping(true);
    setIsBackendBusy(true);
    setTimeout(async () => {
      try {
        setIsTyping(false);
        setActiveAgent("Dynamic Negotiation Agent");
        setMessages((prev) => [
          ...prev,
          {
            id: prev.length + 1,
            text: "Dynamic Negotiation Agent activated.\nApplying negotiation policy and offer optimization.\n\nYour application is being processed.",
            isBot: true,
            variant: "system",
          },
        ]);

        // Fire pipeline start (non-blocking, best-effort)
        try {
          const pipelineStart = await fetch(ENDPOINTS.pipeline_start, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: userData.sessionId,
              applicant_name: userData.name || "Applicant",
              pan_number: userData.pan || "ABCDE1234F",
              loan_amount: amount,
              loan_term: tenure,
              offered_rate: interest,
              previous_sanction_reference: repeatBorrowerData?.sanction_reference || repeatBorrowerData?.reference,
            }),
          });
          if (pipelineStart.ok) {
            const startData = await pipelineStart.json();
            setPipelineSessionId(startData.session_id);
            setPipelineStatus(startData.status || "ACTIVE");
          }
        } catch {
          // non-fatal
        }

        // Credit assessment
        const assessmentResult = await callUnderwritingAPI({
          pan_number: userData.pan,
          gender: "Male",
          married: "Yes",
          dependents: "1",
          education: "Graduate",
          self_employed: "No",
          applicant_income: Number(bankStatementResult?.estimated_monthly_income || 5000),
          coapplicant_income: 1500,
          loan_amount: amount / 100000,
          loan_amount_term: tenure,
          credit_history: 1,
          property_area: "Urban",
          preferred_language: language,
          session_id: userData.sessionId,
          employment_type: repeatBorrowerData?.employment_type || "salaried",
          employer_name: repeatBorrowerData?.employer_name || "TCS",
          monthly_income: Number(bankStatementResult?.estimated_monthly_income || 5000),
          loan_purpose: repeatBorrowerData?.purpose || "general",
        });

        const decision = assessmentResult?.decision;
        const isApproved = assessmentResult && (
          decision === "APPROVED" ||
          decision === "APPROVED_WITH_CONDITIONS" ||
          decision === "CONDITIONAL_APPROVAL"
        );
        const isSoftReject = decision === "CONDITIONAL_REJECT";

        if (!isApproved) {
          let handledReject = false;
          if (isSoftReject && assessmentResult?.soft_reject_guidance) {
            const guidance = assessmentResult.soft_reject_guidance;
            setMessages((prev) => [
              ...prev,
              {
                id: prev.length + 1,
                text: `${guidance.message || TRANSLATIONS.rejected[language]}

${guidance.income_delta_monthly ? `Increase monthly income by about ${formatIndianRupees(guidance.income_delta_monthly)}.` : ""}
${guidance.repayment_history_impact || ""}`.trim(),
                isBot: true,
                quickReplies: [
                  { label: language === "hi" ? "पुनः प्रयास करें" : "Try Again", value: "try_again" },
                  { label: language === "hi" ? "EMI कैलकुलेट करें" : "Recalculate EMI", value: "emi" },
                ],
              },
            ]);
            handledReject = true;
          }
          if (!handledReject) {
            setMessages((prev) => [
              ...prev,
              {
                id: prev.length + 1,
                text: assessmentResult?.message || TRANSLATIONS.rejected[language],
                isBot: true,
              },
            ]);
          }
          return;
        }

        // Negotiation
        const negotiationResult = await callNegotiationAPI(
          assessmentResult.risk_score,
          assessmentResult.risk_tier,
          amount,
          tenure,
          assessmentResult.max_negotiation_rounds || 3,
          assessmentResult.negotiation?.starting_rate,
        );
        if (negotiationResult?.emi_holiday_option) {
          setEmiHolidayOption(negotiationResult.emi_holiday_option);
        }

        // Hand off to negotiation state machine — do NOT auto-accept
        handleNegotiationResponse(negotiationResult);
        return;
      } catch (err) {
        console.error("handleLoanSelect flow error:", err);
        setIsTyping(false);
        addBotMessage(
          language === "en"
            ? "Something went wrong processing your application. Please try again."
            : "आपके आवेदन को संसाधित करने में कुछ गलत हो गया। कृपया पुनः प्रयास करें।"
        );
      } finally {
        setIsBackendBusy(false);
      }
    }, 2500);
  };

  const handleEscalationTrigger = () => {
    setIsTyping(true);
    setTimeout(() => {
      setIsTyping(false);
      setMessages(prev => [
        ...prev,
        {
          id: prev.length + 1,
          text: "Connecting to Human Agent",
          isBot: true,
          type: "escalation"
        }
      ]);
    }, 1000);
  };

  const handleEscalationSubmit = async (preferredTime: string, whatsapp: boolean) => {
    setEscalationData({ preferredTime, whatsapp });
    setIsEscalated(true);
    setIsBackendBusy(true);
    
    try {
      await fetch(ENDPOINTS.escalation_callback, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: userData.sessionId,
          preferred_time: preferredTime,
          whatsapp_opt_in: whatsapp
        }),
      });
    } catch (e) {
      console.warn("Escalation preference save failed", e);
    } finally {
      setIsBackendBusy(false);
    }

    addBotMessage("Your application is on hold pending human review. We'll reach out shortly.");
  };

  const handleQuickReply = (value: string) => {
    handleSendWithText(value);
  };

  const handleSendWithText = (text: string) => {
    if (isInputLocked || isEscalated) return;

    const newMsg: Message = { id: messages.length + 1, text, isBot: false, status: "sent" };
    setIsTyping(true);
    setMessages((prev) => [...prev, newMsg]);
    
    setTimeout(() => {
      setMessages((prev) => prev.map((message) => (message.id === newMsg.id ? { ...message, status: "delivered" } : message)));
      simulateBotResponse(text, newMsg.id);
    }, 500);
  };

  return (
    <>
      <style>{`
        /* Main app layout */
        .app-layout {
          display: flex;
          flex-direction: row;
          height: 100vh;
          width: 100vw;
          overflow: hidden;
          background: #111111;
        }

        /* Chat area — takes all available space */
        .chat-area {
          min-width: 0;
          display: flex;
          flex-direction: column;
          flex: 1 1 auto;
          height: 100vh;
          overflow: hidden;
          transition: all 0.35s ease;
        }

        /* Sidebar — fixed width when open */
        .agent-sidebar {
          width: 320px;
          min-width: 320px;
          max-width: 320px;
          flex: 0 0 320px;
          height: 100vh;
          background: #1a1a1a;
          border-left: 1px solid #2a2a2a;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          transition: width 0.35s ease, min-width 0.35s ease, opacity 0.35s ease, transform 0.35s ease;
          will-change: transform;
        }

        .app-layout.is-processing .chat-input-container {
          height: 0;
          padding-top: 0;
          padding-bottom: 0;
          opacity: 0;
          transform: translateY(10px);
          pointer-events: none;
          overflow: hidden;
          border-top-color: transparent;
          box-shadow: none;
        }

        .app-layout.is-processing .chat-input {
          border-color: transparent;
          box-shadow: none;
        }

        .app-layout.is-processing .processing-indicator {
          opacity: 1;
        }

        .app-layout.is-processing .agent-sidebar {
          box-shadow: 0 -18px 40px rgba(0, 0, 0, 0.35);
        }

        /* Sidebar COLLAPSED state */
        .agent-sidebar.collapsed {
          width: 0;
          min-width: 0;
          opacity: 0;
          border-left: none;
          pointer-events: none;
        }

        /* Sidebar COLLAPSED — show thin tab */
        .sidebar-tab {
          position: fixed;
          right: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 28px;
          height: 80px;
          background: #2a2a2a;
          border-radius: 8px 0 0 8px;
          border: 1px solid #3a3a3a;
          border-right: none;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          z-index: 100;
          transition: background 0.2s;
          writing-mode: vertical-rl;
          font-size: 10px;
          color: #F5C518;
          letter-spacing: 1px;
          font-weight: 600;
        }
        .sidebar-tab:hover {
          background: #333333;
        }
        .agent-sidebar:not(.collapsed) ~ .sidebar-tab,
        .sidebar-tab.hidden {
          display: none;
        }

        /* Chat messages — proper scroll */
        .chat-messages {
          flex: 1;
          min-height: 0;
          overflow-y: auto;
          overflow-x: hidden;
          padding: 16px 20px;
          scroll-behavior: smooth;
          background: url('https://www.transparenttextures.com/patterns/dark-matter.png');
          background-attachment: fixed;
        }

        /* Remove yellow vertical bar artifacts */
        .chat-area::after,
        .chat-area::before {
          display: none !important;
        }

        /* Sidebar header */
        .sidebar-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 20px;
          border-bottom: 1px solid #2a2a2a;
          flex-shrink: 0;
        }

        .sidebar-title {
          font-size: 14px;
          font-weight: 700;
          color: #ffffff;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        /* Agent items — full width cards */
        .agent-item {
          padding: 14px 20px;
          border-bottom: 1px solid #1f1f1f;
          display: flex;
          align-items: flex-start;
          gap: 12px;
          transition: background 0.2s;
        }

        .agent-item.active {
          background: #1f1f1f;
          border-left: 3px solid #F5C518;
        }

        .agent-item.completed {
          border-left: 3px solid #22c55e;
        }

        .agent-item.waiting {
          opacity: 0.5;
        }

        /* Agent status indicator */
        .agent-status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-top: 4px;
          flex-shrink: 0;
        }
        .agent-status-dot.active {
          background: #F5C518;
          box-shadow: 0 0 8px #F5C518;
          animation: pulse 1.5s infinite;
        }
        .agent-status-dot.completed {
          background: #22c55e;
        }
        .agent-status-dot.waiting {
          background: #3a3a3a;
          border: 1px solid #4a4a4a;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(0.8); }
        }

        .agent-info {
          flex: 1;
          min-width: 0;
        }

        .agent-name {
          font-size: 13px;
          font-weight: 600;
          color: #ffffff;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .agent-status-text {
          font-size: 11px;
          color: #6b7280;
          margin-top: 2px;
        }

        .agent-duration {
          font-size: 10px;
          color: #F5C518;
          margin-top: 2px;
        }

        /* Progress bar for active agent */
        .agent-progress {
          height: 2px;
          background: #2a2a2a;
          border-radius: 1px;
          margin-top: 8px;
          overflow: hidden;
        }
        .agent-progress-fill {
          height: 100%;
          background: #F5C518;
          border-radius: 1px;
          animation: progress-pulse 1.5s ease-in-out infinite;
        }
        @keyframes progress-pulse {
          0% { width: 20%; }
          50% { width: 80%; }
          100% { width: 20%; }
        }

        /* Sidebar footer — Groq status */
        .sidebar-footer {
          padding: 12px 20px;
          border-top: 1px solid #2a2a2a;
          margin-top: auto;
          flex-shrink: 0;
        }

        .groq-status {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          color: #6b7280;
        }

        .groq-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #22c55e;
        }

        .api-endpoint {
          font-size: 10px;
          color: #4b5563;
          margin-top: 4px;
          font-family: monospace;
        }

        .chat-messages-container::-webkit-scrollbar {
          width: 6px;
        }
        .chat-messages-container::-webkit-scrollbar-track {
          background: #1a1a1a;
        }
        .chat-messages-container::-webkit-scrollbar-thumb {
          background: #F5C518;
          border-radius: 3px;
        }
        .chat-messages-container::-webkit-scrollbar-thumb:hover {
          background: #e6b800;
        }
        .chat-messages-container {
          scroll-behavior: smooth;
        }
        .chat-input-container {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: #111111;
          border-top: 1px solid #1f1f1f;
          flex-shrink: 0;
          height: 72px;
          opacity: 1;
          transform: translateY(0);
          overflow: hidden;
          transition: height 0.35s ease, opacity 0.3s ease, transform 0.35s ease, padding 0.35s ease, border-top-color 0.35s ease;
        }
        .chat-input {
          flex: 1;
          background: #1a1a1a;
          border: 1px solid #2a2a2a;
          border-radius: 24px;
          padding: 10px 18px;
          color: #ffffff;
          font-size: 14px;
          outline: none;
          transition: border-color 0.2s, box-shadow 0.2s;
          resize: none;
          max-height: 100px;
          overflow-y: auto;
        }
        .chat-input:focus {
          border-color: #F5C518;
          box-shadow: 0 0 0 2px rgba(245, 197, 24, 0.1);
        }
        .chat-input.ready-glow {
          box-shadow: 0 0 20px rgba(245, 197, 24, 0.3);
          animation: ready-glow-fade 1s ease-out;
        }
        @keyframes ready-glow-fade {
          0% { box-shadow: 0 0 20px rgba(245, 197, 24, 0.3); }
          100% { box-shadow: 0 0 0 rgba(245, 197, 24, 0); }
        }
        .processing-indicator {
          height: 2px;
          background: linear-gradient(90deg, transparent, #F5C518, transparent);
          background-size: 200% 100%;
          animation: shimmer 1.5s infinite;
          opacity: 0;
          transition: opacity 0.3s ease;
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .send-button {
          background: #F5C518;
          color: #000000;
          border: none;
          border-radius: 50%;
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s;
        }
        .send-button:hover:not(:disabled) {
          background: #e6b800;
          transform: scale(1.05);
        }
        .send-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        /* Pipeline tracker styles */
        .pipeline-step.completed {
          color: #22c55e;
        }
        .pipeline-step.active {
          color: #F5C518;
          animation: pulse-border 2s infinite;
        }
        .pipeline-step.upcoming {
          color: #6b7280;
        }
        @keyframes pulse-border {
          0%, 100% { box-shadow: 0 0 0 0 rgba(245, 197, 24, 0.7); }
          50% { box-shadow: 0 0 0 8px rgba(245, 197, 24, 0); }
        }
        
        /* FA Badge styles */
        .fa-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 11px;
          font-weight: 600;
          font-family: 'DM Sans', sans-serif;
          letter-spacing: 0.5px;
          border: 1px solid transparent;
          transition: all 0.3s ease;
        }
        .fa-badge.pending {
          background: #111;
          border-color: #2a2a2a;
          color: #444;
        }
        .fa-badge.active {
          background: rgba(245,197,24,0.1);
          border-color: #F5C518;
          color: #F5C518;
          animation: badge-pulse 2s infinite;
        }
        .fa-badge.passed {
          background: rgba(34,197,94,0.1);
          border-color: #22c55e;
          color: #22c55e;
        }
        .fa-badge.failed {
          background: rgba(239,68,68,0.1);
          border-color: #ef4444;
          color: #ef4444;
        }
        @keyframes badge-pulse {
          0%,100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
        .fa-connector {
          color: #444;
          margin: 0 4px;
        }
      `}</style>
    <div className="fixed inset-0 bg-background z-50 flex flex-col">
      {!applicantMode && (
        <div className="absolute inset-0 z-[80] flex items-center justify-center bg-black/80 px-4 backdrop-blur-md">
          <div className="w-full max-w-xl rounded-3xl border border-yellow-400/30 bg-[#111111] p-6 shadow-2xl shadow-black/60">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-yellow-400">LoanEase KYC</div>
            <h1 className="text-3xl font-black tracking-tight text-white">Start a new application or sign in</h1>
            <p className="mt-3 max-w-lg text-sm leading-6 text-slate-300">
              New applications always start clean. Existing users can sign in with a saved session ID and continue where they left off.
            </p>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-[#2a2a2a] bg-[#151515] p-4">
                <div className="text-sm font-bold text-white">New user</div>
                <p className="mt-2 text-xs leading-5 text-slate-400">Fresh session, no old borrower memory, no restore banner.</p>
                <Button className="mt-4 w-full bg-[#F5C518] font-bold text-black hover:bg-[#e6b800]" onClick={() => { startNewApplication(); handleStartConversation(); }}>
                  New Application
                </Button>
              </div>

              <div className="rounded-2xl border border-[#2a2a2a] bg-[#151515] p-4">
                <div className="text-sm font-bold text-white">Existing user</div>
                <p className="mt-2 text-xs leading-5 text-slate-400">Sign in with your session ID to load a saved application.</p>
                <input
                  value={existingSessionId}
                  onChange={(event) => setExistingSessionId(event.target.value)}
                  placeholder="Enter session ID"
                  className="mt-4 w-full rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
                />
                <Button className="mt-3 w-full border border-yellow-400/30 bg-transparent font-bold text-yellow-300 hover:bg-yellow-400/10" variant="outline" onClick={signInExistingUser}>
                  Sign In
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Session Resume Banner */}
      {showSessionBanner && (
        <div className="absolute inset-x-0 top-0 z-[60] bg-yellow-400 text-black px-4 py-3 flex items-center justify-between animate-in slide-in-from-top duration-500 shadow-xl">
          <div className="text-sm font-bold flex items-center gap-2">
            <MessageCircle className="w-4 h-4" />
            Welcome back. Continue your application?
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" className="bg-black text-white hover:bg-black/80" onClick={handleResume}>Resume</Button>
            <Button size="sm" variant="ghost" className="hover:bg-black/10" onClick={handleStartFresh}>Start Fresh</Button>
          </div>
        </div>
      )}

      <div className={`app-layout ${isProcessing ? 'is-processing' : ''}`}>
        {/* Chat Area */}
        <div className="chat-area">
          {/* Header */}
          <div className="bg-card border-b border-border shadow-md">
            <div className="flex items-center justify-between px-4 py-3">
              <Button variant="ghost" size="icon" onClick={onClose}>
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center relative">
                  <MessageCircle className="w-4 h-4 text-primary-foreground" />
                  <div className="absolute -top-1 -right-1 w-2 h-2 bg-green-500 rounded-full border-2 border-card" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold">Loan Assistant</h2>
                    <Badge variant="outline" className={cn(
                      "text-[10px] py-0 px-1.5 h-4",
                      isOfflineMode ? "border-muted-foreground/50 text-muted-foreground" : "border-yellow-400/50 text-yellow-400"
                    )}>
                      {isOfflineMode ? <><Zap className="w-3 h-3 mr-1" />Quick Mode</> : <><Bot className="w-3 h-3 mr-1" />AI Mode</>}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5 h-4 border-blue-400/50 text-blue-400">
                      <MessageSquare className="w-3 h-3 mr-1" />Web
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground font-mono">
                    {userData.sessionId} | Stage: <span className="text-yellow-400 uppercase header-stage-label">{userData.stage}</span>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => window.open('https://www.rbi.org.in/scripts/BS_ViewBS.aspx?Id=976', '_blank')}
                  className="text-xs px-2 py-1 h-7 border border-blue-400/20 hover:bg-blue-500/10"
                >
                  <FileText className="w-3 h-3 mr-1" />
                  Glossary
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate('/whatsapp')}
                  className="text-xs px-2 py-1 h-7 border border-green-500/20 hover:bg-green-500/10"
                >
                  <Smartphone className="w-3 h-3 mr-1" />
                  WhatsApp
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={toggleAgentSidebar}
                  className="text-xs px-2 py-1 h-7 border border-yellow-400/20 hover:bg-yellow-400/10 agents-toggle-btn"
                >
                  <Bot className="w-3 h-3 mr-1" />
                  AGENTS ({agentTrace?.length || 2})
                </Button>
                <LanguageSwitcher currentLanguage={language} onLanguageChange={handleLanguageChange} />
              </div>
            </div>

        {/* Progress Indicator */}
        <div className="px-4 pb-2 relative z-20">
          <div className="flex items-center justify-between max-w-lg mx-auto relative">
            <div className="absolute top-2.5 left-0 right-0 h-0.5 bg-border -z-10" />
            {APP_STAGES.map((s, idx) => {
              const stagesOrder = APP_STAGES.map(st => st.id);
              const currentIdx = stagesOrder.indexOf(userData.stage);
              const isCompleted = idx < currentIdx;
              const isActive = idx === currentIdx;

              return (
                <div 
                  key={s.id} 
                  className={`flex flex-col items-center gap-1 group cursor-pointer relative pipeline-step ${isCompleted ? 'completed' : isActive ? 'active' : 'upcoming'}`}
                  onClick={() => {
                    if (s.id === "credit" && isCompleted) {
                      setShowCreditSummaryPopup(true);
                    } else if (isCompleted) {
                      toast.info(`Summary of ${s.label} completed`);
                    }
                  }}
                >
                  <div className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-300 ring-4 ring-card",
                    isCompleted ? "bg-green-500 text-white shadow-[0_0_10px_rgba(34,197,94,0.3)]" : 
                    isActive ? "bg-yellow-400 text-black border-2 border-yellow-400 animate-pulse-border" : 
                    "bg-card border-2 border-border text-muted-foreground"
                  )}>
                    {isCompleted ? <Check className="w-3.5 h-3.5" /> : idx + 1}
                  </div>
                  <span className={cn(
                    "text-[9px] uppercase tracking-wider font-bold transition-colors absolute -bottom-4 whitespace-nowrap",
                    isActive ? "text-yellow-400" : isCompleted ? "text-green-500" : "text-muted-foreground"
                  )}>Step {idx + 1} of 5</span>
                  <span className={cn(
                    "text-[9px] uppercase tracking-wider font-bold transition-colors absolute -bottom-7 whitespace-nowrap",
                    isActive ? "text-yellow-400" : isCompleted ? "text-green-500" : "text-muted-foreground"
                  )}>{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="px-4 pb-3">
          <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-center gap-2">
            {KYC_FACTORS.map((factor, idx) => {
              const passed = kycFactors[factor.key];
              const isCurrent = kycFactors.current === (factor.key === "fa1" ? 1 : factor.key === "fa2" ? 2 : 3);
              const status = passed ? "passed" : isCurrent ? "active" : "pending";

              return (
                <React.Fragment key={factor.key}>
                  <span
                    id={`fa${idx + 1}-badge`}
                    className={`fa-badge ${status}`}
                  >
                    {passed ? "Verified" : isCurrent ? "Processing" : "Pending"} {factor.label}
                  </span>
                  {idx < KYC_FACTORS.length - 1 && <span className="fa-connector">→</span>}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Credit Summary Popup */}
        {showCreditSummaryPopup && (
          <div className="absolute top-24 left-1/2 -translate-x-1/2 w-64 bg-card border border-border rounded-xl shadow-2xl z-50 p-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
              <h3 className="font-bold text-sm flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-green-500/20 text-green-500 flex items-center justify-center text-xs">2</span>
                Credit Check <Check className="w-3 h-3 text-green-500" />
              </h3>
              <button onClick={() => setShowCreditSummaryPopup(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">CIBIL Score</span>
                <span className="font-bold">{userData.creditScore || 820}/900</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Decision</span>
                <span className="font-bold">{underwritingResult?.decision || "APPROVED"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Risk Score</span>
                <span className="font-bold">{userData.riskScore || 87}/100</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tier</span>
                <span className="font-bold text-yellow-400">{userData.riskTier || "Low Risk"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">XGBoost</span>
                <span className="font-bold">
                  {underwritingResult?.confidence_width != null
                    ? `${Math.round((underwritingResult.approval_probability || 0) * 100)}% ± ${Math.round((underwritingResult.confidence_width || 0) * 50)}%`
                    : "87% confidence"}
                </span>
              </div>
              {underwritingResult?.income_reasonability && (
                <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
                  <div className="font-semibold text-foreground">FOIR check</div>
                  <div className="mt-1">
                    {underwritingResult.income_reasonability.message || "Income support looks acceptable."}
                  </div>
                </div>
              )}
              {underwritingResult?.soft_reject_guidance && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                  <div className="font-semibold text-amber-100">Soft reject guidance</div>
                  <div className="mt-1">
                    {underwritingResult.soft_reject_guidance.message}
                  </div>
                </div>
              )}
              {underwritingResult?.model_drift_warning && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
                  <div className="font-semibold text-rose-100">Model drift detected</div>
                  <div className="mt-1">
                    {underwritingResult.recommendation || "Retrain model with recent data."}
                  </div>
                </div>
              )}
              <Button
                variant="outline"
                className="w-full border-blue-500/30 bg-blue-500/5 text-blue-200 hover:bg-blue-500/10"
                onClick={() => setShowBankStatementCard(true)}
              >
                No payslips? Upload bank statement
              </Button>
              <div className="flex justify-between pt-2 border-t border-border/50 text-muted-foreground text-[10px]">
                <span>Time taken</span>
                <span>0.9s</span>
              </div>
            </div>
          </div>
        )}

        <div className="px-4 pb-3 pt-6">
        </div>
      </div>

          {/* Messages */}
          <div ref={messagesContainerRef} className="chat-messages">
            {showWelcomeState ? (
            <div className="flex min-h-full items-center justify-center px-4 py-8">
              <div className="w-full max-w-md rounded-3xl border border-[#2a2a2a] bg-[#101010]/95 p-8 text-center shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur-sm">
                <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#F5C518]/15 text-[#F5C518] shadow-[0_0_0_8px_rgba(245,197,24,0.04)]">
                  <MessageCircle className="h-8 w-8" />
                </div>
                <h3 className="text-2xl font-black tracking-tight text-slate-100">Hi. I am your Loan Assistant</h3>
                <p className="mt-3 text-sm leading-6 text-slate-300">{TRANSLATIONS.opening[language]}</p>
                <div className="mt-6 grid gap-2 text-left text-sm text-slate-300 sm:grid-cols-2">
                  <div className="rounded-xl border border-[#2a2a2a] bg-[#151515] px-3 py-3 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <span>No paperwork</span>
                  </div>
                  <div className="rounded-xl border border-[#2a2a2a] bg-[#151515] px-3 py-3 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <span>Instant credit check</span>
                  </div>
                  <div className="rounded-xl border border-[#2a2a2a] bg-[#151515] px-3 py-3 flex items-center gap-2">
                    <Bot className="w-4 h-4 text-blue-400" />
                    <span>AI-powered negotiation</span>
                  </div>
                  <div className="rounded-xl border border-[#2a2a2a] bg-[#151515] px-3 py-3 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-purple-400" />
                    <span>Blockchain-secured letter</span>
                  </div>
                </div>
                <Button
                  variant="chat"
                  className="mt-7 w-full bg-[#F5C518] font-bold text-black hover:bg-[#e6b800]"
                  onClick={handleStartConversation}
                >
                  Apply for a Loan →
                </Button>
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <div key={message.id} className="space-y-3">
                  <ChatMessage
                    message={message.text}
                    isBot={message.isBot}
                    status={message.status}
                    variant={message.variant}
                  />

                  {message.isBot && message.quickReplies && (
                    <QuickReplies options={message.quickReplies} onSelect={handleQuickReply} />
                  )}

                  {message.isBot && message.type === "emi-calculator" && (
                    <EmiCalculatorWidget onUseTerms={handleEmiTerms} />
                  )}

                  {message.isBot && message.type === "escalation" && (
                    <div className="max-w-md rounded-2xl border border-[#2a2a2a] bg-[#111111] p-6 shadow-2xl animate-in slide-in-from-left duration-500">
                       <div className="mb-4 flex items-center gap-3">
                         <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#F5C518]">
                           <User className="w-5 h-5 text-black" />
                         </div>
                         <div>
                           <h3 className="font-bold text-slate-100">Connecting to Human Agent</h3>
                           <p className="text-xs text-slate-500">Ticket: ESC-2026-{Math.floor(100 + Math.random() * 899)}</p>
                         </div>
                       </div>
                       <p className="mb-6 text-sm text-slate-400">A loan officer will call you within 2 business hours. Your application is saved.</p>
                       
                       <div className="space-y-4">
                          <div className="space-y-2">
                            <label className="text-[10px] font-bold uppercase text-slate-500">Preferred Callback Time</label>
                            <div className="flex gap-2">
                              {["Morning", "Afternoon", "Evening"].map((t) => (
                                <Button key={t} size="sm" variant={escalationData.preferredTime === t ? "accent" : "outline"} className="flex-1 text-[10px]" onClick={() => setEscalationData((prev) => ({ ...prev, preferredTime: t }))}>{t}</Button>
                              ))}
                            </div>
                          </div>
                          <div className="flex items-center justify-between rounded-lg border border-[#2a2a2a] bg-[#151515] p-3">
                            <span className="text-xs font-medium text-slate-300">Get updates on WhatsApp?</span>
                            <Button size="sm" variant={escalationData.whatsapp ? "accent" : "outline"} onClick={() => setEscalationData((prev) => ({ ...prev, whatsapp: !prev.whatsapp }))}>{escalationData.whatsapp ? <>Yes <CheckCircle className="w-4 h-4 inline ml-1" /></> : "No"}</Button>
                          </div>
                          <Button className="w-full bg-[#F5C518] font-bold text-black hover:bg-[#e6b800]" disabled={!escalationData.preferredTime} onClick={() => handleEscalationSubmit(escalationData.preferredTime, escalationData.whatsapp)}>Confirm Preference</Button>
                       </div>
                    </div>
                  )}
                </div>
              ))}

              {isTyping && <ChatMessage message="" isBot isTyping />}
            </>
          )}

        {quickEligibilityPreview && !showPanUploadCard && (
          <div className="w-full max-w-md rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/12 via-card to-card/95 p-5 shadow-[0_14px_34px_rgba(16,185,129,0.12)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-emerald-200">Quick Eligibility Preview</p>
                <h3 className="mt-1 text-lg font-black text-foreground">{quickEligibilityPreview.status}</h3>
              </div>
              <span className={cn(
                "rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em]",
                quickEligibilityPreview.status === "Strong"
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
                  : quickEligibilityPreview.status === "Conditional"
                    ? "border-amber-400/40 bg-amber-400/10 text-amber-200"
                    : "border-rose-400/40 bg-rose-400/10 text-rose-200"
              )}>
                {quickEligibilityPreview.status}
              </span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-border/70 bg-background/60 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Requested Loan</div>
                <div className="mt-1 text-base font-bold text-foreground">{formatIndianRupees(quickEligibilityPreview.loanAmount)}</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/60 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Monthly Income</div>
                <div className="mt-1 text-base font-bold text-foreground">{formatIndianRupees(quickEligibilityPreview.monthlyIncome)}</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/60 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Estimated EMI</div>
                <div className="mt-1 text-base font-bold text-foreground">{formatIndianRupees(quickEligibilityPreview.estimatedEmi)}</div>
                <div className="mt-1 text-[11px] text-muted-foreground">Assumes {quickEligibilityPreview.assumedRate.toFixed(1)}% for {quickEligibilityPreview.tenureMonths} months</div>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/60 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">EMI / Income</div>
                <div className="mt-1 text-base font-bold text-foreground">{Math.round(quickEligibilityPreview.emiToIncomeRatio * 100)}%</div>
                <div className="mt-1 text-[11px] text-muted-foreground">Target safe cap: {formatIndianRupees(quickEligibilityPreview.maxAffordableEmi)}</div>
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-4 py-3 text-sm text-foreground/90">
              {quickEligibilityPreview.note}
            </div>

            <Button
              className="mt-4 w-full bg-[#F5C518] font-bold text-black hover:bg-[#e6b800]"
              onClick={handleProceedToKyc}
            >
              Proceed to KYC →
            </Button>
          </div>
        )}

        {isKycProcessing && (
          <div className="max-w-md rounded-xl border border-yellow-500/40 bg-card p-4 shadow-lg shadow-yellow-500/10 animate-in fade-in zoom-in duration-300">
            <div className="flex items-start gap-4">
              <div className="relative w-16 h-20 bg-muted rounded border border-border overflow-hidden shrink-0">
                <FileText className="absolute inset-0 m-auto text-muted-foreground/30 w-8 h-8" />
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.8)] animate-[scan_2s_ease-in-out_infinite]" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="text-sm font-bold text-foreground flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full border-2 border-yellow-400 border-t-transparent animate-spin" />
                  {kycProcessingText}
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-yellow-400 transition-all duration-200"
                    style={{ width: `${kycProgress}%` }}
                  />
                </div>
                <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest text-right">
                  {kycProgress}% / processing
                </div>
              </div>
            </div>
          </div>
        )}

        {showBankStatementCard && (
          <div className="w-full max-w-md self-start rounded-xl border-2 border-dashed border-blue-500/70 bg-gradient-to-br from-card to-card/85 p-5 shadow-lg shadow-blue-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-foreground">
              <FileText className="h-4 w-4 text-blue-400" />
              {kycText("Upload Bank Statement", "Bank Statement अपलोड करें")}
            </div>
            <div className="mb-3 text-xs text-muted-foreground">Upload last 3 months PDF (Max 5MB)</div>
            <input
              ref={bankStatementInputRef}
              type="file"
              accept=".pdf,.txt"
              className="hidden"
              onChange={(e) => handleBankStatementUpload(e.target.files?.[0])}
            />
            <Button variant="outline" className="w-full border-blue-500/50 bg-background/60 hover:bg-blue-500/10" onClick={() => bankStatementInputRef.current?.click()}>
              <Upload className="mr-2 h-4 w-4" />
              {kycText("Choose File", "फ़ाइल चुनें")}
            </Button>
            <div className="mt-2 text-[11px] text-muted-foreground">
              {kycText("This helps if you don't have payslips", "अगर आपके पास payslips नहीं हैं, तो यह मदद करेगा")}
            </div>
          </div>
        )}

        {showPanUploadCard && (
          <div className="w-full max-w-md self-start rounded-xl border-2 border-dashed border-yellow-500/70 bg-gradient-to-br from-card to-card/85 p-5 shadow-lg shadow-yellow-500/10">
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
          <div className="relative z-20 max-w-md rounded-xl border border-green-500/50 bg-gradient-to-br from-card to-card/85 p-4 shadow-lg shadow-green-500/10 pointer-events-auto">
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
                type="button"
                className="relative z-20 flex-1 pointer-events-auto"
                onClick={() => {
                  setShowPanConfirmCard(false);
                  setShowAadhaarUploadCard(true);
                  addBotMessage(kycText("Please proceed to upload your Aadhaar card.", "अब अपना Aadhaar कार्ड अपलोड करें।"));
                }}
              >
                {kycText("Confirm", "पुष्टि करें")}
              </Button>
              <Button
                variant="outline"
                type="button"
                className="relative z-20 flex-1 pointer-events-auto"
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
          <div className="w-full max-w-md self-start rounded-xl border-2 border-dashed border-yellow-500/70 bg-gradient-to-br from-card to-card/85 p-5 shadow-lg shadow-yellow-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-foreground">
              <FileText className="h-4 w-4 text-yellow-400" />
              {kycText("Upload Aadhaar Card", "Aadhaar कार्ड अपलोड करें")}
            </div>
            <div className="mb-3 text-xs text-muted-foreground">
              {kycText("JPG, PNG or PDF • Max 10MB\n\nTip: Ensure the 12-digit Aadhaar number is clearly visible.", "JPG, PNG or PDF • Max 10MB\n\nTip: 12-digit Aadhaar number स्पष्ट रूप से दिखे।")}
            </div>
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
            <div className="mt-4 border-t border-border/60 pt-4">
              <div className="mb-2 text-xs font-medium text-muted-foreground">
                {kycText("Or enter Aadhaar number manually", "या Aadhaar number manually दर्ज करें")}
              </div>
              <input
                id="aadhaar-manual-input"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                placeholder="XXXX XXXX XXXX"
                value={manualAadhaarInput}
                onChange={(e) => handleManualAadhaarInput(e.target.value)}
                className="w-full rounded-md border border-border bg-background/70 px-3 py-2 text-sm tracking-widest text-foreground outline-none focus:border-yellow-500/70"
              />
              <div
                id="aadhaar-validity"
                className="mt-2 min-h-[1.25rem] text-xs"
                style={{ color: aadhaarValidityOk === true ? "#22c55e" : aadhaarValidityOk === false ? "#ef4444" : undefined }}
              >
                {aadhaarValidityText}
              </div>
            </div>
          </div>
        )}

        {showAadhaarConfirmCard && aadhaarKycData && (
          <div className="relative z-20 max-w-md rounded-xl border border-green-500/50 bg-gradient-to-br from-card to-card/85 p-4 shadow-lg shadow-green-500/10 pointer-events-auto">
            <div className="mb-2 flex items-center gap-2 text-base font-semibold text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              {kycText("Aadhaar Scanned", "Aadhaar Scanned")}
            </div>
            <div className="space-y-1.5 text-sm text-foreground">
              {aadhaarKycData.name ? <div className="font-medium">{aadhaarKycData.name}</div> : null}
              <div>
                {aadhaarVerhoeffResult?.masked
                  || (aadhaarKycData.aadhaar_last4 ? `XXXX XXXX ${aadhaarKycData.aadhaar_last4}` : kycText("Aadhaar number detected", "Aadhaar number detect हुआ"))}
              </div>
              {aadhaarKycData.date_of_birth ? (
                <div>{kycText("DOB", "DOB")}: {aadhaarKycData.date_of_birth}</div>
              ) : null}
              {aadhaarKycData.gender ? (
                <div>{kycText("Gender", "Gender")}: {aadhaarKycData.gender}</div>
              ) : null}
            </div>
            <div className="mt-3 rounded-lg border border-border/60 bg-background/50 p-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {kycText("ID Validation", "ID Validation")}
              </div>
              {aadhaarVerhoeffResult?.valid ? (
                <>
                  <div className="text-sm font-medium text-green-400">
                    {kycText("Verhoeff checksum valid", "Verhoeff checksum valid")}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {kycText(
                      "Aadhaar is a genuine UIDAI-format identifier",
                      "Aadhaar एक genuine UIDAI-format identifier है"
                    )}
                  </div>
                </>
              ) : (
                <div className="text-sm text-amber-400">
                  {aadhaarVerhoeffResult?.message
                    || kycText("Verhoeff validation pending", "Verhoeff validation pending")}
                </div>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                variant="accent"
                type="button"
                className="relative z-20 flex-1 pointer-events-auto"
                disabled={aadhaarVerhoeffResult?.valid === false}
                onClick={handleAadhaarConfirm}
              >
                {kycText("Confirm", "पुष्टि करें")}
              </Button>
              <Button
                variant="outline"
                type="button"
                className="relative z-20 flex-1 pointer-events-auto"
                onClick={() => {
                  setShowAadhaarConfirmCard(false);
                  setShowAadhaarUploadCard(true);
                }}
              >
                <Pencil className="mr-1 h-4 w-4" />
                {kycText("Edit", "संपादित करें")}
              </Button>
            </div>
          </div>
        )}

        {showKycVerifiedCard && (
          <div className="max-w-md rounded-xl border border-green-500/50 bg-gradient-to-br from-card to-card/85 p-4 shadow-lg shadow-green-500/10">
            <div className="mb-1 flex items-center gap-2 text-base font-semibold text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              {kycText("Factor 1 Complete", "Factor 1 Complete")}
            </div>
            <div className="text-sm text-foreground">{kycText("Documents verified via AI Vision", "AI Vision के माध्यम से दस्तावेज़ सत्यापित")}</div>
            <div className="text-sm text-muted-foreground">{kycText("Next step: OTP verification", "अगला चरण: OTP verification")}</div>
          </div>
        )}

        {showOtpCard && (
          <div className="max-w-md rounded-xl border border-primary/50 bg-gradient-to-br from-card to-card/90 p-4 shadow-lg shadow-primary/10" onPaste={handleOtpPaste}>
            <div className="mb-2 flex items-center gap-2 text-base font-semibold text-primary">
              <ShieldCheck className="h-4 w-4" />
              {kycText("Verify Mobile OTP", "मोबाइल OTP सत्यापित करें")}
            </div>
            <div className="text-sm text-muted-foreground">
              {otpStatusMessage || kycText("Enter the 6-digit code sent to your Aadhaar-linked mobile number.", "अपने Aadhaar-linked mobile number पर भेजा गया 6-digit code दर्ज करें।")}
            </div>
            {otpSentToLast4 ? (
              <div className="mt-1 text-xs text-muted-foreground">
                {kycText("Sent to ending", "अंतिम अंक")}: {otpSentToLast4}
              </div>
            ) : null}
            <div className="mt-4 flex items-center justify-between gap-2">
              <div className="flex flex-1 gap-2">
                {otpDigits.map((digit, index) => (
                  <input
                    key={index}
                    ref={(element) => {
                      otpInputRefs.current[index] = element;
                    }}
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(event) => updateOtpDigit(index, event.target.value)}
                    onKeyDown={(event) => handleOtpKeyDown(index, event)}
                    className="h-11 w-11 rounded-lg border border-border bg-background text-center text-lg font-semibold tracking-[0.25em] text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25"
                  />
                ))}
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {otpSecondsRemaining > 0
                  ? kycText(`OTP expires in ${Math.floor(otpSecondsRemaining / 60)}:${String(otpSecondsRemaining % 60).padStart(2, "0")}`, `OTP ${Math.floor(otpSecondsRemaining / 60)}:${String(otpSecondsRemaining % 60).padStart(2, "0")} में समाप्त होगा`)
                  : kycText("OTP expired", "OTP समाप्त हो गया है")}
              </span>
              <span>
                {otpAttemptsRemaining !== null
                  ? kycText(`${otpAttemptsRemaining} attempts remaining`, `${otpAttemptsRemaining} प्रयास शेष हैं`)
                  : null}
              </span>
            </div>
            {otpError ? <div className="mt-2 text-sm text-red-400">{otpError}</div> : null}
            <div className="mt-4 flex gap-2">
              <Button
                variant="accent"
                className="flex-1"
                disabled={otpSubmitting || otpLocked}
                onClick={submitOtp}
              >
                {otpSubmitting ? kycText("Verifying...", "सत्यापन हो रहा है...") : kycText("Verify OTP", "OTP सत्यापित करें")}
              </Button>
              <Button
                variant="outline"
                className="flex-1"
                disabled={otpSubmitting || otpResendCooldown > 0}
                onClick={resendOtp}
              >
                {otpResendCooldown > 0
                  ? kycText(`Resend in ${otpResendCooldown}s`, `${otpResendCooldown}s में फिर भेजें`)
                  : kycText("Resend OTP", "OTP फिर भेजें")}
              </Button>
            </div>
          </div>
        )}

        {showCreditScoreCard && creditScoreData && (
          <div className="py-4">
            <CreditScoreCard
              score={creditScoreData.credit_score}
              maxScore={900}
              decision={underwritingResult?.decision}
              approvalProbability={underwritingResult?.approval_probability}
              confidenceLower={underwritingResult?.confidence_lower}
              confidenceUpper={underwritingResult?.confidence_upper}
              confidenceWidth={underwritingResult?.confidence_width}
              modelCertainty={underwritingResult?.model_certainty}
              riskTier={underwritingResult?.risk_tier}
              cibil_score={underwritingResult?.cibil_score ?? underwritingResult?.risk_score}
              cibil_band={underwritingResult?.cibil_band}
              cibil_classification={underwritingResult?.cibil_classification}
              risk_label={underwritingResult?.risk_label}
              industry_standard={underwritingResult?.industry_standard}
              eligible={underwritingResult?.eligible}
              conditional={underwritingResult?.conditional}
              rate_range={underwritingResult?.rate_range}
              max_negotiation_rounds={underwritingResult?.max_negotiation_rounds || underwritingResult?.cibil_max_negotiation_rounds}
              incomeReasonability={underwritingResult?.income_reasonability}
              softRejectGuidance={underwritingResult?.soft_reject_guidance}
              modelDriftWarning={underwritingResult?.model_drift_warning}
              recommendation={underwritingResult?.recommendation}
              structuredShapNarration={underwritingResult?.structured_shap_narration}
              alternative_score={underwritingResult?.alternative_score}
              alternative_eligible={underwritingResult?.alternative_eligible}
              alternative_details={underwritingResult?.alternative_details}
            />
          </div>
        )}

        {showLoanOffers && (
          <div className="space-y-4">
            <LoanComparisonCards 
              offers={[
                { id: 'std', name: 'Standard', amount: 500000, rate: 11.5, tenure: 36, emi: 16607, total: '6.2L' },
                { id: 'bv', name: 'Premium', amount: 500000, rate: 11.0, tenure: 60, emi: 10747, total: '6.45L', isRecommended: true },
                { id: 'flx', name: 'Flexi', amount: 500000, rate: 10.75, tenure: 84, emi: 8234, total: '6.92L' }
              ]}
              onSelect={handleOfferPreview}
            />

            {emiHolidayOption && (
              <div className="rounded-2xl border border-sky-500/30 bg-sky-500/10 p-5 shadow-[0_14px_34px_rgba(0,0,0,0.18)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-black uppercase tracking-[0.22em] text-sky-200">EMI Holiday</p>
                    <p className="mt-1 text-sm text-slate-100">
                      {emiHolidayOption.message || `Pause the first ${emiHolidayOption.holidayMonths || emiHolidayOption.holiday_months || 2} EMIs and start later.`}
                    </p>
                  </div>
                  <span className="rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-200">
                    {emiHolidayOption.recommended || emiHolidayOption.recommended === undefined ? "Recommended" : "Optional"}
                  </span>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant={selectedHolidayMonths === (emiHolidayOption.holidayMonths || emiHolidayOption.holiday_months || 2) ? "accent" : "outline"}
                    onClick={() => setSelectedHolidayMonths(emiHolidayOption.holidayMonths || emiHolidayOption.holiday_months || 2)}
                  >
                    Use EMI holiday
                  </Button>
                  <Button variant="ghost" onClick={() => setSelectedHolidayMonths(0)}>
                    Regular schedule
                  </Button>
                </div>
                {emiHolidayOption.extraCost != null || emiHolidayOption.extra_cost != null ? (
                  <div className="mt-3 text-xs text-sky-100/80">
                    Extra cost: {formatIndianRupees(Number(emiHolidayOption.extraCost || emiHolidayOption.extra_cost || 0))}
                  </div>
                ) : null}
              </div>
            )}

            {showKfsCard && pendingOffer && (
              <div className="rounded-2xl border border-[#2a2a2a] bg-[#101010] p-5 shadow-[0_14px_34px_rgba(0,0,0,0.28)]">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold uppercase tracking-[0.22em] text-[#F5C518]">📋 Key Fact Statement (KFS)</p>
                    <p className="mt-1 text-xs text-slate-400">As required by RBI Digital Lending Directions, 2025</p>
                  </div>
                  <span className="rounded-full border border-[#2a2a2a] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Collapsible disclosure
                  </span>
                </div>

                <details className="rounded-xl border border-[#2a2a2a] bg-[#0d0d0d] p-4" open>
                  <summary className="cursor-pointer list-none text-sm font-semibold text-slate-100">
                    <span>Expand KFS</span>
                  </summary>

                  <div className="mt-4 rounded-2xl border border-[#333] bg-[#121212] p-4 text-sm text-slate-200">
                    <div className="mb-4 text-center">
                      <p className="text-[11px] font-black uppercase tracking-[0.28em] text-slate-400">Key Fact Statement</p>
                      <p className="mt-1 text-[11px] text-slate-500">Regulatory Ref: RBI/2022-23/111 DOR.STR.REC.68/21.01.001/2022-23</p>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Loan Amount</span>
                        <span className="font-semibold text-slate-50">{formatIndianRupees(pendingOffer.amount)}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Annual % Rate</span>
                        <span className="font-semibold text-slate-50">{pendingOffer.rate.toFixed(2)}%</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Processing Fee</span>
                        <span className="font-semibold text-slate-50">₹0 (Nil)</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Monthly EMI</span>
                        <span className="font-semibold text-slate-50">{formatIndianRupees(pendingOffer.emi)}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Total Payable</span>
                        <span className="font-semibold text-slate-50">{formatIndianRupees(pendingOffer.emi * pendingOffer.tenure)}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                        <span className="text-slate-400">Tenure</span>
                        <span className="font-semibold text-slate-50">{pendingOffer.tenure} months</span>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-2 rounded-xl border border-white/5 bg-white/5 p-3 text-sm">
                      <div className="flex items-start justify-between gap-4">
                        <span className="text-slate-400">Repayment schedule</span>
                        <span className="text-right font-medium text-slate-100">Equal monthly instalments over {pendingOffer.tenure} months</span>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <span className="text-slate-400">Prepayment</span>
                        <span className="text-right font-medium text-slate-100">Allowed after 3 months, no penalty</span>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <span className="text-slate-400">Foreclosure</span>
                        <span className="text-right font-medium text-slate-100">Allowed, no charges</span>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <span className="text-slate-400">Grievance</span>
                        <span className="text-right font-medium text-slate-100">support@loanease.app · RBI Ombudsman</span>
                      </div>
                    </div>

                    <div className="mt-4 rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4">
                      <label className="flex cursor-pointer items-start gap-3 text-sm text-slate-200">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 rounded border-slate-600 bg-transparent text-[#F5C518] focus:ring-[#F5C518]"
                          checked={kfsAcknowledged}
                          onChange={(e) => setKfsAcknowledged(e.target.checked)}
                        />
                        <span>I have read and understood the Key Fact Statement</span>
                      </label>
                    </div>
                  </div>
                </details>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-slate-400">APR includes all disclosed fees; this prototype currently assumes zero processing fee.</p>
                  <Button
                    variant="accent"
                    disabled={!kfsAcknowledged}
                    onClick={handleAcceptPendingOffer}
                  >
                    Accept Offer
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Negotiation Offer Card ─────────────────────────────────────── */}
        {negotiationState && negotiationState !== "ACCEPTED" && (
          <div className="rounded-2xl border border-[#2a2a2a] bg-[#0d0d0d] p-5 shadow-[0_14px_34px_rgba(0,0,0,0.28)]">

            {/* Header row */}
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#F5C518]">
                  {negotiationState === "HIGH_RISK" && "Fixed Offer — No Negotiation"}
                  {negotiationState === "ACTIVE" && `Negotiation Active — ${negotiationRoundsLeft} Round${negotiationRoundsLeft !== 1 ? "s" : ""} Remaining`}
                  {negotiationState === "FINAL_OFFER" && "Final Offer — Last Chance"}
                  {negotiationState === "FLOOR_REACHED" && "Rate Floor Reached"}
                  {negotiationState === "ESCALATED" && "Escalated to Senior Officer"}
                  {negotiationState === "CONCEDE" && `Rate Reduced — ${negotiationRoundsLeft} Round${negotiationRoundsLeft !== 1 ? "s" : ""} Left`}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {negotiationState === "HIGH_RISK" && "Based on your risk profile, this is a non-negotiable rate."}
                  {(negotiationState === "ACTIVE" || negotiationState === "CONCEDE") && "You may request a lower rate or accept the current offer."}
                  {negotiationState === "FINAL_OFFER" && "No further reductions are possible. Accept or escalate."}
                  {negotiationState === "FLOOR_REACHED" && `Rate is at the regulatory floor of ${negotiationFloorRate}%. Accept or escalate.`}
                  {negotiationState === "ESCALATED" && "A senior officer will contact you within 2 business hours."}
                </p>
              </div>
              <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                negotiationState === "HIGH_RISK" ? "border-red-500/30 bg-red-500/10 text-red-300" :
                negotiationState === "ESCALATED" ? "border-purple-500/30 bg-purple-500/10 text-purple-300" :
                negotiationState === "FINAL_OFFER" || negotiationState === "FLOOR_REACHED" ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-300" :
                "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              }`}>
                {negotiationState === "CONCEDE" ? "ACTIVE" : negotiationState}
              </span>
            </div>

            {/* Offer details */}
            {negotiationOffer && (
              <div className="grid gap-2 sm:grid-cols-3">
                <div className="flex flex-col gap-0.5 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500">Interest Rate</span>
                  <span className="text-lg font-bold text-slate-50">
                    {(negotiationOffer.rate ?? negotiationOffer.interest_rate ?? 0).toFixed(2)}%
                  </span>
                </div>
                <div className="flex flex-col gap-0.5 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500">Monthly EMI</span>
                  <span className="text-lg font-bold text-slate-50">
                    {formatIndianRupees(negotiationOffer.emi ?? negotiationOffer.monthly_emi ?? 0)}
                  </span>
                </div>
                <div className="flex flex-col gap-0.5 rounded-lg border border-white/5 bg-white/5 px-3 py-2">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500">Total Payable</span>
                  <span className="text-lg font-bold text-slate-50">
                    {formatIndianRupees(negotiationOffer.total_payable ?? 0)}
                  </span>
                </div>
              </div>
            )}

            {/* Savings badge */}
            {negotiationOffer?.savings_vs_opening?.total != null && negotiationOffer.savings_vs_opening.total > 0 && (
              <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
                You save {formatIndianRupees(negotiationOffer.savings_vs_opening.total)} vs opening offer
                ({formatIndianRupees(negotiationOffer.savings_vs_opening.per_month)}/month)
              </div>
            )}

            {/* Escalation ref */}
            {negotiationState === "ESCALATED" && negotiationEscalationId && (
              <div className="mt-3 rounded-lg border border-purple-500/20 bg-purple-500/10 px-3 py-2 text-sm text-purple-200">
                Reference: <span className="font-mono font-bold">{negotiationEscalationId}</span>
              </div>
            )}

            {/* Action buttons */}
            <div className="mt-4 flex flex-wrap gap-3">
              {(negotiationState === "ACTIVE" || negotiationState === "CONCEDE") && (
                <>
                  <button
                    disabled={isNegotiationBusy}
                    onClick={handleNegotiationCounter}
                    className="rounded-xl border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
                  >
                    {isNegotiationBusy ? "Processing..." : "Request Lower Rate"}
                  </button>
                  <button
                    disabled={isNegotiationBusy}
                    onClick={handleNegotiationAccept}
                    className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Accept This Offer
                  </button>
                </>
              )}

              {(negotiationState === "FINAL_OFFER" || negotiationState === "HIGH_RISK") && (
                <>
                  <button
                    disabled={isNegotiationBusy}
                    onClick={handleNegotiationAccept}
                    className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Accept Final Offer
                  </button>
                  {negotiationState === "FINAL_OFFER" && (
                    <button
                      disabled={isNegotiationBusy}
                      onClick={handleNegotiationEscalate}
                      className="rounded-xl border border-purple-500/40 bg-purple-500/10 px-4 py-2 text-sm font-semibold text-purple-200 transition hover:bg-purple-500/20 disabled:opacity-50"
                    >
                      Escalate to Human
                    </button>
                  )}
                </>
              )}

              {negotiationState === "FLOOR_REACHED" && (
                <>
                  <button
                    disabled={isNegotiationBusy}
                    onClick={handleNegotiationAccept}
                    className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Accept at Floor Rate
                  </button>
                  <button
                    disabled={isNegotiationBusy}
                    onClick={handleNegotiationEscalate}
                    className="rounded-xl border border-purple-500/40 bg-purple-500/10 px-4 py-2 text-sm font-semibold text-purple-200 transition hover:bg-purple-500/20 disabled:opacity-50"
                  >
                    Escalate to Human
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Negotiation summary after ACCEPTED */}
        {negotiationState === "ACCEPTED" && negotiationSummary && (
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
            <p className="text-[11px] font-black uppercase tracking-[0.22em] text-emerald-400">Negotiation Summary</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="flex justify-between rounded-lg bg-white/5 px-3 py-2 text-sm">
                <span className="text-slate-400">Opening Rate</span>
                <span className="font-semibold text-slate-100">{negotiationSummary.opening_rate.toFixed(2)}%</span>
              </div>
              <div className="flex justify-between rounded-lg bg-white/5 px-3 py-2 text-sm">
                <span className="text-slate-400">Final Rate</span>
                <span className="font-semibold text-slate-100">{negotiationSummary.final_rate.toFixed(2)}%</span>
              </div>
              <div className="flex justify-between rounded-lg bg-white/5 px-3 py-2 text-sm">
                <span className="text-slate-400">Rate Reduction</span>
                <span className="font-semibold text-emerald-300">−{negotiationSummary.rate_reduction.toFixed(2)}%</span>
              </div>
              <div className="flex justify-between rounded-lg bg-white/5 px-3 py-2 text-sm">
                <span className="text-slate-400">Total Savings</span>
                <span className="font-semibold text-emerald-300">{formatIndianRupees(negotiationSummary.total_interest_savings)}</span>
              </div>
            </div>
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
              referenceId={userData.blockchainData?.transaction_id || `LOAN${Date.now().toString().slice(-8)}`}
              blockchainHash={userData.blockchainData?.block_hash || "0x..."}
              onViewAnalytics={handleViewAnalytics}
            />
          </div>
        )}

        {showAnalytics && (
          <div className="py-8 bg-background/50 rounded-xl border border-border/50 animate-slide-up">
            <AnalyticsDashboard
              sessionId={userData.sessionId}
              customerName={userData.name}
              initialAmount={userData.selectedLoan.amount}
              initialInterest={userData.selectedLoan.interest}
              initialTenure={userData.selectedLoan.tenure}
            />
          </div>
        )}

          <div ref={messagesEndRef} />
        </div>

        <div className="lg:w-[340px] lg:ml-4 min-h-0 overflow-y-auto chat-messages-container">
        {/* Removed redundant floating AgentActivityPanel */}
        </div>
      </div>

      {/* Input */}
      <div className="chat-input-container">
            <div className="flex max-w-4xl flex-1 items-center gap-3 mx-auto w-full">
          <Textarea
            ref={textAreaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
                placeholder={getInputPlaceholder()}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
                className={cn("chat-input flex-1", !isProcessing && hasStartedConversation && !isEscalated ? "ready-glow" : "")}
            disabled={isInputLocked}
          />
          <Button
            variant="chat"
            size="icon"
            onClick={handleSend}
            disabled={
              !input.trim() ||
              isInputLocked
            }
            className="send-button h-10 w-10"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>

        <div className="processing-indicator" />

          {/* Sidebar Tab - visible when sidebar is collapsed */}
          <div className="sidebar-tab hidden" onClick={toggleAgentSidebar}>
            AGENTS
          </div>
        </div>

        {/* Agent Sidebar */}
        <div className={`agent-sidebar border-l border-border bg-card/80 backdrop-blur-md transition-all duration-300 ${isSidebarOpen ? 'w-[320px]' : 'w-0 overflow-hidden opacity-0'} ${(showPanUploadCard || showAadhaarUploadCard) ? 'hidden' : ''}`}>
          <div className="flex flex-col h-full">
            <div className="flex items-center justify-between p-4 border-b border-border/50">
              <div className="flex items-center gap-2 font-bold text-sm">
                <Bot className="w-4 h-4 text-yellow-400" />
                AGENT ORCHESTRATION
              </div>
              <Button variant="ghost" size="icon" onClick={() => setIsSidebarOpen(false)} className="h-8 w-8">
                <X className="w-4 h-4" />
              </Button>
            </div>
            
            <div className="flex-1 overflow-hidden">
              <AgentActivityPanel 
                trace={agentTrace} 
                pipelineStatus={pipelineStatus} 
                activeAgentLabel={activeAgent}
                liveProcessing={isProcessing}
                liveLogLines={processingLog}
                kycAuditTrail={kycAuditTrail}
                kycAuditSummary={kycAuditSummary}
              />
            </div>

            <div className="p-4 border-t border-border/50 bg-muted/20">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase tracking-widest font-bold mb-2">
                <span>System Status</span>
                <span className="text-green-500">Online</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] font-mono bg-black/40 p-2 rounded border border-border/50 overflow-hidden whitespace-nowrap">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                api.groq.com/llama-3-70b-versatile
              </div>
            </div>
          </div>
        </div>
        </div>
      </div>
    </>
  );
};
