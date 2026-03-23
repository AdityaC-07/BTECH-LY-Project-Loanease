import { cn } from "@/lib/utils";

interface CreditScoreCardProps {
  score: number;
  maxScore?: number;
}

export const CreditScoreCard = ({ score, maxScore = 900 }: CreditScoreCardProps) => {
  const percentage = (score / maxScore) * 100;
  const isEligible = score >= 700;
  
  const getScoreColor = () => {
    if (score >= 750) return "text-success";
    if (score >= 700) return "text-accent";
    if (score >= 650) return "text-warning";
    return "text-destructive";
  };

  const getScoreLabel = () => {
    if (score >= 750) return "Excellent";
    if (score >= 700) return "Good";
    if (score >= 650) return "Fair";
    return "Poor";
  };

  return (
    <div className="bg-gradient-card rounded-2xl p-6 shadow-lg border border-border animate-slide-up">
      <div className="text-center mb-6">
        <p className="text-sm text-muted-foreground mb-2">Your Credit Score</p>
        <div className="relative inline-flex items-center justify-center">
          <svg className="w-40 h-40 transform -rotate-90">
            <circle
              cx="80"
              cy="80"
              r="70"
              stroke="currentColor"
              strokeWidth="12"
              fill="none"
              className="text-muted"
            />
            <circle
              cx="80"
              cy="80"
              r="70"
              stroke="currentColor"
              strokeWidth="12"
              fill="none"
              strokeLinecap="round"
              className={getScoreColor()}
              strokeDasharray={`${percentage * 4.4} 440`}
              style={{
                transition: "stroke-dasharray 1s ease-out",
              }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn("text-4xl font-bold font-display", getScoreColor())}>
              {score}
            </span>
            <span className="text-xs text-muted-foreground">/ {maxScore}</span>
          </div>
        </div>
      </div>
      
      <div className="text-center space-y-2">
        <p className={cn("text-lg font-semibold", getScoreColor())}>
          {getScoreLabel()}
        </p>
        <p className="text-sm text-muted-foreground">
          {isEligible
            ? "You're eligible for our best loan offers!"
            : "We're sorry, you don't meet our minimum credit requirements."}
        </p>
      </div>
    </div>
  );
};
