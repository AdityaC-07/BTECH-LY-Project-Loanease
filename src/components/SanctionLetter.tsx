import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Download, Shield, FileCheck } from "lucide-react";

interface SanctionLetterProps {
  customerName: string;
  loanAmount: number;
  interestRate: number;
  tenure: number;
  emi: number;
  sanctionDate: string;
  referenceId: string;
  blockchainHash: string;
}

export const SanctionLetter = ({
  customerName,
  loanAmount,
  interestRate,
  tenure,
  emi,
  sanctionDate,
  referenceId,
  blockchainHash,
}: SanctionLetterProps) => {
  return (
    <Card className="max-w-2xl mx-auto animate-slide-up overflow-hidden">
      <div className="bg-gradient-primary p-6 text-primary-foreground">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileCheck className="w-8 h-8" />
            <div>
              <h2 className="text-xl font-bold font-display">Loan Sanction Letter</h2>
              <p className="text-sm opacity-90">Digital Document</p>
            </div>
          </div>
          <Badge variant="secondary" className="bg-accent text-accent-foreground">
            <Shield className="w-3 h-3 mr-1" />
            Verified
          </Badge>
        </div>
      </div>
      
      <CardContent className="p-6 space-y-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Reference ID</p>
            <p className="font-mono text-sm font-medium">{referenceId}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Sanction Date</p>
            <p className="font-medium text-sm">{sanctionDate}</p>
          </div>
        </div>

        <div className="border-t border-b border-border py-4 space-y-4">
          <div>
            <p className="text-xs text-muted-foreground">Customer Name</p>
            <p className="font-semibold text-lg">{customerName}</p>
          </div>
          
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Loan Amount</p>
              <p className="font-bold text-accent">₹{loanAmount.toLocaleString('en-IN')}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Interest Rate</p>
              <p className="font-semibold">{interestRate}% p.a.</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Tenure</p>
              <p className="font-semibold">{tenure} months</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Monthly EMI</p>
              <p className="font-bold text-accent">₹{emi.toLocaleString('en-IN')}</p>
            </div>
          </div>
        </div>

        <div className="bg-secondary/50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-4 h-4 text-accent" />
            <p className="text-xs font-semibold text-accent">Blockchain Verified</p>
          </div>
          <p className="font-mono text-xs text-muted-foreground break-all">
            {blockchainHash}
          </p>
        </div>

        <Button variant="accent" className="w-full" size="lg">
          <Download className="w-4 h-4 mr-2" />
          Download Sanction Letter
        </Button>
      </CardContent>
    </Card>
  );
};
