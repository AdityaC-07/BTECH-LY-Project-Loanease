import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface CreditScoreCardProps {
  score: number;
  maxScore?: number;
}

export const CreditScoreCard = ({ score, maxScore = 900 }: CreditScoreCardProps) => {
  const [step, setStep] = useState(1);
  const [displayScore, setDisplayScore] = useState(300);

  useEffect(() => {
    // Step 1: 0-0.5s Show "Checking your CIBIL score..."
    const t1 = setTimeout(() => setStep(2), 500);

    // Step 2: 0.5-2.5s Score counter animates from 300 to actual_score
    let interval: NodeJS.Timeout;
    const t2 = setTimeout(() => {
      interval = setInterval(() => {
        setDisplayScore((prev) => {
          if (prev >= score) {
            clearInterval(interval);
            return score;
          }
          return Math.min(prev + 5, score);
        });
      }, (2000 / ((score - 300) / 5))); // Complete in 2s
    }, 500);

    // Step 3: 2.5s Bar fills
    const t3 = setTimeout(() => setStep(3), 2500);
    
    // Step 4: 3.0s Tier badge drops in
    const t4 = setTimeout(() => setStep(4), 3000);

    // Step 5: 3.3s SHAP explanation bullets appear
    const t5 = setTimeout(() => setStep(5), 3300);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearInterval(interval);
      clearTimeout(t3);
      clearTimeout(t4);
      clearTimeout(t5);
    };
  }, [score]);

  const percentage = (displayScore / maxScore) * 100;
  const isEligible = score >= 700;
  
  const getScoreColor = () => {
    if (score >= 750) return "text-green-500";
    if (score >= 700) return "text-yellow-400";
    if (score >= 650) return "text-orange-400";
    return "text-red-500";
  };

  const getStrokeColor = () => {
    if (score >= 750) return "#22c55e";
    if (score >= 700) return "#facc15";
    if (score >= 650) return "#fb923c";
    return "#ef4444";
  };

  const getScoreLabel = () => {
    if (score >= 750) return "Excellent";
    if (score >= 700) return "Good";
    if (score >= 650) return "Fair";
    return "Poor";
  };

  const getShapBullets = () => {
    if (score >= 700) {
      return [
        { text: "Consistent repayment history", positive: true },
        { text: "Low credit utilization (12%)", positive: true },
        { text: "Multiple active accounts", positive: true },
      ];
    }
    return [
      { text: "Recent missed payments", positive: false },
      { text: "High credit utilization (85%)", positive: false },
      { text: "Short credit history length", positive: false },
    ];
  };

  if (step === 1) {
    return (
      <div className="bg-gradient-card rounded-2xl p-6 shadow-lg border border-border animate-slide-up flex flex-col items-center justify-center min-h-[300px]">
        <Loader2 className="w-12 h-12 animate-spin text-yellow-400 mb-4" />
        <p className="text-lg font-medium text-muted-foreground animate-pulse">Checking your CIBIL score...</p>
      </div>
    );
  }

  return (
    <div className="bg-gradient-card rounded-2xl p-6 shadow-lg border border-border animate-slide-up relative overflow-hidden">
      <div className="text-center mb-6">
        <p className="text-sm text-muted-foreground mb-2 font-medium tracking-wide uppercase">Your Credit Score</p>
        <div className="relative inline-flex items-center justify-center">
          <svg className="w-40 h-40 transform -rotate-90">
            <circle
              cx="80"
              cy="80"
              r="70"
              stroke="currentColor"
              strokeWidth="12"
              fill="none"
              className="text-muted/30"
            />
            <circle
              cx="80"
              cy="80"
              r="70"
              stroke={getStrokeColor()}
              strokeWidth="12"
              fill="none"
              strokeLinecap="round"
              strokeDasharray={step >= 3 ? `${percentage * 4.4} 440` : "0 440"}
              style={{
                transition: "stroke-dasharray 0.8s ease-out",
              }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn("text-5xl font-black font-display tracking-tighter", getScoreColor())}>
              {displayScore}
            </span>
            <span className="text-xs text-muted-foreground font-bold mt-1">/ {maxScore}</span>
          </div>
        </div>
      </div>
      
      <div className="text-center space-y-4">
        <div className={cn(
          "transition-all duration-500 transform",
          step >= 4 ? "scale-100 opacity-100" : "scale-0 opacity-0"
        )}>
          <span className={cn(
            "inline-block px-4 py-1.5 rounded-full text-sm font-bold tracking-wider uppercase border-2",
            score >= 750 ? "bg-green-500/10 text-green-500 border-green-500/20" :
            score >= 700 ? "bg-yellow-400/10 text-yellow-400 border-yellow-400/20" :
            score >= 650 ? "bg-orange-400/10 text-orange-400 border-orange-400/20" :
            "bg-red-500/10 text-red-500 border-red-500/20"
          )}>
            {getScoreLabel()} Risk Tier
          </span>
        </div>

        {step >= 5 && (
          <div className="pt-4 border-t border-border/50 text-left space-y-2">
            <p className="text-xs text-muted-foreground font-semibold mb-3 uppercase tracking-wider">AI Assessment Factors</p>
            {getShapBullets().map((bullet, i) => (
              <div 
                key={i} 
                className="flex items-start gap-2 text-sm animate-in slide-in-from-right-4 fade-in duration-300 fill-mode-both"
                style={{ animationDelay: `${i * 200}ms` }}
              >
                {bullet.positive ? (
                  <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-orange-400 shrink-0 mt-0.5" />
                )}
                <span className="text-muted-foreground">{bullet.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
