import { TrendingDown, Award, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface MarketRateComparisonProps {
  ourRate: number;
  className?: string;
}

// Static reference rates — update periodically; live rates require partnerships
const MARKET_RATES = [
  { name: "SBI Personal Loan",  min: 10.5,  max: 13.0  },
  { name: "HDFC Personal Loan", min: 10.75, max: 15.0  },
  { name: "Bajaj Finserv",      min: 11.0,  max: 17.0  },
];

function rateBar(min: number, max: number, floor = 8, ceil = 20) {
  const left  = ((min - floor) / (ceil - floor)) * 100;
  const width = ((max - min)   / (ceil - floor)) * 100;
  return { left: `${left.toFixed(1)}%`, width: `${width.toFixed(1)}%` };
}

export const MarketRateComparison = ({ ourRate, className }: MarketRateComparisonProps) => {
  const marketMidpoints = MARKET_RATES.map((r) => (r.min + r.max) / 2);
  const avgMarket      = marketMidpoints.reduce((a, b) => a + b, 0) / marketMidpoints.length;
  const isCompetitive  = ourRate <= avgMarket;

  const ourBar = rateBar(ourRate, ourRate);

  return (
    <div
      className={cn(
        "rounded-xl border border-border/50 bg-card/60 p-4 space-y-4 text-sm",
        className
      )}
      role="region"
      aria-label="Market rate comparison"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold text-foreground">
          <TrendingDown className="w-4 h-4 text-accent" aria-hidden="true" />
          Market Rate Comparison
        </div>
        <div
          className={cn(
            "flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full",
            isCompetitive
              ? "bg-green-500/20 text-green-400"
              : "bg-yellow-500/20 text-yellow-400"
          )}
          aria-label={isCompetitive ? "Competitive rate" : "Above market average"}
        >
          <Award className="w-3 h-3" aria-hidden="true" />
          {isCompetitive ? "Competitive Rate" : "Above Market Avg"}
        </div>
      </div>

      {/* Rate scale */}
      <div className="space-y-2.5">
        {/* Our offer */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="font-semibold text-accent">LoanEase (your offer)</span>
            <span className="font-bold text-accent">{ourRate.toFixed(2)}% p.a.</span>
          </div>
          <div className="relative h-2 bg-secondary/40 rounded-full overflow-hidden">
            <div
              className="absolute h-full bg-accent rounded-full"
              style={{ left: ourBar.left, width: "6px" }}
              aria-hidden="true"
            />
          </div>
        </div>

        {/* Market competitors */}
        {MARKET_RATES.map((bank) => {
          const bar = rateBar(bank.min, bank.max);
          return (
            <div key={bank.name} className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{bank.name}</span>
                <span>{bank.min}–{bank.max}% p.a.</span>
              </div>
              <div className="relative h-2 bg-secondary/40 rounded-full overflow-hidden">
                <div
                  className="absolute h-full bg-muted-foreground/50 rounded-full"
                  style={{ left: bar.left, width: bar.width }}
                  aria-hidden="true"
                />
              </div>
            </div>
          );
        })}
      </div>

      <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <Info className="w-3 h-3 mt-0.5 shrink-0" aria-hidden="true" />
        Reference rates from public disclosures. Actual offers may vary based on
        your credit profile and lender policies.
      </p>
    </div>
  );
};
