import { useState } from "react";
import { Button } from "./ui/button";
import { formatIndianCurrency } from "@/lib/languageUtils";
import { Check, Star } from "lucide-react";
import { cn } from "@/lib/utils";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const handleSelect = (offer: Offer) => {
    setSelectedId(offer.id);
    setTimeout(() => {
      onSelect(offer);
    }, 1500); // Wait 1.5s to show the "Proceeding..." state before closing
  };

  return (
    <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row gap-4 my-6 overflow-x-visible pb-4 px-1">
        {offers.map((offer, index) => {
          const isSelected = selectedId === offer.id;
          const isFaded = selectedId !== null && !isSelected;
          
          return (
            <div
              key={offer.id}
              className={cn(
                "min-w-[280px] flex-1 p-6 rounded-2xl border transition-all duration-300 relative bg-card flex flex-col group animate-slide-up fill-mode-both hover:scale-[1.02]",
                offer.isRecommended ? "order-first md:order-none" : "", // Recommended first on mobile
                offer.isRecommended && !selectedId
                  ? "border-yellow-400 border-2 shadow-[0_0_20px_rgba(250,204,21,0.2)] md:-translate-y-2 z-10 hover:border-yellow-300 hover:shadow-[0_0_25px_rgba(250,204,21,0.3)]"
                  : "border-border hover:border-muted-foreground/30",
                isSelected && "border-green-500 border-2 bg-green-500/5 shadow-[0_0_20px_rgba(34,197,94,0.2)] scale-[1.02]",
                isFaded && "opacity-40 scale-95 pointer-events-none"
              )}
              style={{ animationDelay: `${index * 150}ms` }}
            >
              {offer.isRecommended && !isSelected && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-yellow-400 text-black text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest shadow-lg flex items-center gap-1">
                  <Star className="w-3 h-3 fill-black" /> Recommended
                </div>
              )}
              
              {isSelected && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-green-500 text-white text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest shadow-lg flex items-center gap-1">
                  <Check className="w-3 h-3" /> Selected
                </div>
              )}

              <div className="space-y-4 flex-1 flex flex-col">
                <div className="text-center">
                  <h4 className="text-lg font-bold mb-1 tracking-wide uppercase">{offer.name}</h4>
                  <p className="text-2xl font-black text-yellow-400">{formatIndianCurrency(offer.amount)}</p>
                </div>

                <div className="space-y-2 text-sm border-y border-border/50 py-4 flex-1">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Interest Rate</span>
                    <span className="font-semibold text-foreground">{offer.rate}% p.a.</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Tenure</span>
                    <span className="font-semibold text-foreground">{offer.tenure} months</span>
                  </div>
                  <div className="flex justify-between items-baseline pt-2 border-t border-border/30 mt-2">
                    <span className="text-muted-foreground">EMI</span>
                    <span className="text-xl font-bold text-yellow-400">{formatIndianCurrency(offer.emi)}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs text-muted-foreground pt-1">
                    <span>Total Interest</span>
                    <span>{formatIndianCurrency(parseInt(offer.total.replace(/,/g, "")) || (offer.emi * offer.tenure - offer.amount))}</span>
                  </div>
                </div>

                <Button
                  onClick={() => handleSelect(offer)}
                  disabled={selectedId !== null}
                  className={cn(
                    "w-full font-bold transition-all mt-auto",
                    isSelected ? "bg-green-500 text-white hover:bg-green-600" :
                    offer.isRecommended
                      ? "bg-yellow-400 hover:bg-yellow-500 text-black shadow-lg shadow-yellow-400/20"
                      : "variant-outline border-border text-foreground hover:bg-muted"
                  )}
                >
                  {isSelected ? "Selected" : "Select"} {offer.isRecommended && !isSelected && <Star className="ml-2 w-4 h-4 fill-black" />}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
      
      {selectedId && (
        <div className="text-center animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-green-500/10 border border-green-500/20 text-green-500 text-sm font-medium">
            <Loader2 className="w-4 h-4 animate-spin" />
            Proceeding with this offer...
          </div>
        </div>
      )}
    </div>
  );
};
