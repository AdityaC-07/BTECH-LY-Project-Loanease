import { Button } from "./ui/button";
import { formatIndianCurrency } from "@/lib/languageUtils";
import { Check } from "lucide-react";

interface Offer {
  id: string;
  name: string;
  amount: number;
  rate: number;
  tenure: number;
  emi: number;
  total: string;
  isRecommended?: boolean;
}

interface LoanComparisonCardsProps {
  offers: Offer[];
  onSelect: (offer: Offer) => void;
}

export const LoanComparisonCards = ({ offers, onSelect }: LoanComparisonCardsProps) => {
  return (
    <div className="flex flex-col md:flex-row gap-4 my-6 overflow-x-auto pb-4 px-1 snap-x scrollbar-hide">
      {offers.map((offer) => (
        <div
          key={offer.id}
          className={`min-w-[280px] flex-1 snap-center p-6 rounded-2xl border transition-all duration-300 relative bg-card ${
            offer.isRecommended
              ? "border-yellow-400 border-2 shadow-[0_0_20px_rgba(250,204,21,0.2)] -translate-y-1 scale-105 z-10"
              : "border-border hover:border-border/80"
          }`}
        >
          {offer.isRecommended && (
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-yellow-400 text-black text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-widest shadow-lg">
              ★ Best Value
            </div>
          )}

          <div className="space-y-4">
            <div className="text-center">
              <h4 className="text-lg font-bold mb-1">{offer.name}</h4>
              <p className="text-2xl font-black text-yellow-400">{formatIndianCurrency(offer.amount)}</p>
            </div>

            <div className="space-y-2 text-sm border-y border-border/50 py-4">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Interest Rate</span>
                <span className="font-semibold">{offer.rate}% p.a.</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tenure</span>
                <span className="font-semibold">{offer.tenure} months</span>
              </div>
              <div className="flex justify-between items-baseline pt-2">
                <span className="text-muted-foreground">EMI</span>
                <span className="text-lg font-bold text-yellow-400">{formatIndianCurrency(offer.emi)}</span>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Total Repayment</span>
                <span>{offer.total}</span>
              </div>
            </div>

            <Button
              onClick={() => onSelect(offer)}
              className={`w-full font-bold group ${
                offer.isRecommended
                  ? "bg-yellow-400 hover:bg-yellow-500 text-black"
                  : "variant-outline border-yellow-400/50 text-yellow-400 hover:bg-yellow-400/10"
              }`}
            >
              Select {offer.isRecommended && <Check className="ml-2 w-4 h-4" />}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
};
