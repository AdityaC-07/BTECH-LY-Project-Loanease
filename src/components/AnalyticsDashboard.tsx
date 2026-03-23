import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Download, Info, TrendingUp, AlertCircle, CheckCircle2 } from "lucide-react";

interface AnalyticsDashboardProps {
  customerName: string;
  initialAmount?: number;
  initialInterest?: number;
  initialTenure?: number;
  riskScore?: number;
  shapData?: { factor: string; value: number }[];
}

declare global {
  interface Window {
    Chart: any;
    html2canvas: any;
    jspdf: any;
  }
}

export const AnalyticsDashboard = ({
  customerName,
  initialAmount = 500000,
  initialInterest = 10.5,
  initialTenure = 60,
  riskScore = 87,
  shapData = [
    { factor: "Credit History", value: 0.42 },
    { factor: "Income Level", value: 0.28 },
    { factor: "Loan Amount", value: -0.15 },
    { factor: "Employment Type", value: 0.12 },
    { factor: "Existing EMIs", value: -0.09 },
    { factor: "Co-applicant Income", value: 0.07 },
  ],
}: AnalyticsDashboardProps) => {
  const [loanAmount, setLoanAmount] = useState(initialAmount);
  const [interestRate, setInterestRate] = useState(initialInterest);
  const [tenure, setTenure] = useState(initialTenure);
  const dashboardRef = useRef<HTMLDivElement>(null);

  // Refs for Chart instances
  const chartRefs = {
    risk: useRef<HTMLCanvasElement>(null),
    shap: useRef<HTMLCanvasElement>(null),
    emi: useRef<HTMLCanvasElement>(null),
    repayment: useRef<HTMLCanvasElement>(null),
    radar: useRef<HTMLCanvasElement>(null),
  };

  const chartInstances = useRef<{ [key: string]: any }>({});

  // Calculation logic
  const calculateEMI = (p: number, r: number, n: number) => {
    const monthlyRate = r / 12 / 100;
    return Math.round((p * monthlyRate * Math.pow(1 + monthlyRate, n)) / (Math.pow(1 + monthlyRate, n) - 1));
  };

  const emi = calculateEMI(loanAmount, interestRate, tenure);
  const totalPayable = emi * tenure;
  const totalInterest = totalPayable - loanAmount;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(val);
  };

  // Amortization Schedule
  const getAmortizationData = () => {
    const data: { year: number; principal: number; interest: number }[] = [];
    let outstanding = loanAmount;
    const monthlyRate = interestRate / 12 / 100;

    for (let year = 1; year <= Math.ceil(tenure / 12); year++) {
      let yearlyPrincipal = 0;
      let yearlyInterest = 0;
      for (let month = 1; month <= 12 && (year - 1) * 12 + month <= tenure; month++) {
        const interestComp = outstanding * monthlyRate;
        const principalComp = emi - interestComp;
        yearlyPrincipal += principalComp;
        yearlyInterest += interestComp;
        outstanding -= principalComp;
      }
      data.push({ year, principal: Math.round(yearlyPrincipal), interest: Math.round(yearlyInterest) });
    }
    return data;
  };

  // Initialize and Update Charts
  useEffect(() => {
    if (!window.Chart) return;

    const Chart = window.Chart;

    // Destroy existing instances to prevent memory leaks
    Object.values(chartInstances.current).forEach((chart) => chart?.destroy());

    // 1. Risk Score Gauge
    if (chartRefs.risk.current) {
      chartInstances.current.risk = new Chart(chartRefs.risk.current, {
        type: 'doughnut',
        data: {
          datasets: [{
            data: [riskScore, 100 - riskScore],
            backgroundColor: [
              riskScore < 50 ? '#ef4444' : riskScore < 75 ? '#F5C518' : '#22c55e',
              '#3a3a3a'
            ],
            borderWidth: 0,
            circumference: 180,
            rotation: 270,
          }]
        },
        options: {
          cutout: '80%',
          plugins: { tooltip: { enabled: false }, legend: { display: false } },
          responsive: true,
          maintainAspectRatio: false,
        }
      });
    }

    // 2. SHAP Factors (Horizontal Bar)
    if (chartRefs.shap.current) {
      chartInstances.current.shap = new Chart(chartRefs.shap.current, {
        type: 'bar',
        data: {
          labels: shapData.map(d => d.factor),
          datasets: [{
            label: 'Impact Score',
            data: shapData.map(d => d.value),
            backgroundColor: shapData.map(d => d.value >= 0 ? '#F5C518' : '#ef4444'),
            borderRadius: 4,
          }]
        },
        options: {
          indexAxis: 'y',
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: '#3a3a3a' }, ticks: { color: '#9ca3af' } },
            y: { grid: { display: false }, ticks: { color: '#9ca3af' } }
          },
          responsive: true,
          maintainAspectRatio: false,
        }
      });
    }

    // 3. EMI Breakdown (Doughnut)
    if (chartRefs.emi.current) {
      chartInstances.current.emi = new Chart(chartRefs.emi.current, {
        type: 'doughnut',
        data: {
          labels: ['Principal Amount', 'Total Interest'],
          datasets: [{
            data: [loanAmount, totalInterest],
            backgroundColor: ['#F5C518', '#3a3a3a'],
            borderWidth: 0,
          }]
        },
        options: {
          cutout: '75%',
          plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af' } } },
          responsive: true,
          maintainAspectRatio: false,
        }
      });
    }

    // 4. Yearly Repayment (Grouped Bar)
    const amortData = getAmortizationData();
    if (chartRefs.repayment.current) {
      chartInstances.current.repayment = new Chart(chartRefs.repayment.current, {
        type: 'bar',
        data: {
          labels: amortData.map(d => `Year ${d.year}`),
          datasets: [
            { label: 'Principal Paid', data: amortData.map(d => d.principal), backgroundColor: '#F5C518' },
            { label: 'Interest Paid', data: amortData.map(d => d.interest), backgroundColor: '#4a4a4a' }
          ]
        },
        options: {
          scales: {
            x: { stacked: false, grid: { display: false }, ticks: { color: '#9ca3af' } },
            y: { stacked: false, grid: { color: '#3a3a3a' }, ticks: { color: '#9ca3af' } }
          },
          plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af' } } },
          responsive: true,
          maintainAspectRatio: false,
        }
      });
    }

    // 5. Radar Chart
    if (chartRefs.radar.current) {
      chartInstances.current.radar = new Chart(chartRefs.radar.current, {
        type: 'radar',
        data: {
          labels: ['Monthly Income', 'Credit Score', 'Employment Stability', 'LTI Ratio', 'Repayment History', 'Co-applicant Support'],
          datasets: [
            {
              label: 'You',
              data: [72, 87, 80, 65, 90, 60],
              borderColor: '#F5C518',
              backgroundColor: 'rgba(245, 197, 24, 0.3)',
              fill: true,
            },
            {
              label: 'Avg Approved Borrower',
              data: [70, 75, 75, 70, 80, 65],
              borderColor: '#6b7280',
              backgroundColor: 'rgba(107, 114, 128, 0.2)',
              fill: true,
            }
          ]
        },
        options: {
          scales: {
            r: {
              angleLines: { color: '#3a3a3a' },
              grid: { color: '#3a3a3a' },
              pointLabels: { color: '#9ca3af', font: { size: 10 } },
              ticks: { display: false },
              suggestedMin: 0,
              suggestedMax: 100
            }
          },
          plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af' } } },
          responsive: true,
          maintainAspectRatio: false,
        }
      });
    }

    return () => {
      Object.values(chartInstances.current).forEach((chart) => chart?.destroy());
    };
  }, [loanAmount, interestRate, tenure, riskScore]);

  const handleDownloadPDF = async () => {
    if (!dashboardRef.current || !window.html2canvas || !window.jspdf) return;

    const canvas = await window.html2canvas(dashboardRef.current, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#1a1a1a',
    });
    
    const imgData = canvas.toDataURL('image/png');
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF('p', 'mm', 'a4');
    
    const imgProps = pdf.getImageProperties(imgData);
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = (imgProps.height * pdfWidth) / imgProps.width;
    
    pdf.setFillColor(26, 26, 26);
    pdf.rect(0, 0, pdfWidth, pdf.internal.pageSize.getHeight(), 'F');
    
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(18);
    pdf.text("LoanEase Analytics Report", 20, 20);
    pdf.setFontSize(10);
    pdf.text(`Applicant: ${customerName}`, 20, 28);
    pdf.text(`Date: ${new Date().toLocaleDateString('en-IN')}`, 20, 33);
    
    pdf.addImage(imgData, 'PNG', 0, 40, pdfWidth, pdfHeight);
    pdf.save("LoanEase_Report.pdf");
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-4 space-y-8 animate-slide-up" id="analytics-section">
      <div className="text-center space-y-2">
        <h2 className="text-3xl font-bold font-display text-white">Your Loan Insights</h2>
        <p className="text-muted-foreground">A complete breakdown of your loan profile and repayment plan.</p>
      </div>

      {/* Live EMI Calculator */}
      <Card className="bg-card border-none shadow-lg overflow-hidden">
        <div className="bg-gradient-primary h-1" />
        <CardHeader>
          <CardTitle className="text-xl">Adjust Your Loan Parameters</CardTitle>
          <CardDescription>See how changing your loan amount, rate, or tenure affects your repayment.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          <div className="text-center py-4 bg-secondary/30 rounded-lg border border-border/50">
            <p className="text-sm text-muted-foreground mb-1 uppercase tracking-wider">Your Monthly EMI</p>
            <p className="text-4xl font-bold text-accent">{formatCurrency(emi)}</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium">Loan Amount</label>
                <span className="text-accent font-bold">{formatCurrency(loanAmount)}</span>
              </div>
              <Slider
                value={[loanAmount]}
                min={100000}
                max={5000000}
                step={50000}
                onValueChange={(val) => setLoanAmount(val[0])}
                className="py-4"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>₹1L</span>
                <span>₹50L</span>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium">Interest Rate</label>
                <span className="text-accent font-bold">{interestRate}% p.a.</span>
              </div>
              <Slider
                value={[interestRate]}
                min={8}
                max={24}
                step={0.25}
                onValueChange={(val) => setInterestRate(val[0])}
                className="py-4"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>8%</span>
                <span>24%</span>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium">Tenure</label>
                <span className="text-accent font-bold">{tenure} Months</span>
              </div>
              <Slider
                value={[tenure]}
                min={12}
                max={84}
                step={6}
                onValueChange={(val) => setTenure(val[0])}
                className="py-4"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>12m</span>
                <span>84m</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div ref={dashboardRef} className="space-y-6">
        {/* Row 1: Gauge & SHAP */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="bg-[#1e1e1e] border-[#2e2e2e] p-6 h-[400px] flex flex-col">
            <CardTitle className="text-lg mb-2 flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-accent" />
              Your Credit Risk Score
            </CardTitle>
            <div className="relative flex-1 flex flex-col items-center justify-center">
              <div className="h-[200px] w-full">
                <canvas ref={chartRefs.risk}></canvas>
              </div>
              <div className="absolute top-[65%] text-center">
                <p className="text-5xl font-bold text-white mb-1">{riskScore}</p>
                <p className={`text-sm font-semibold uppercase tracking-widest ${riskScore >= 75 ? 'text-green-500' : riskScore >= 50 ? 'text-yellow-500' : 'text-red-500'}`}>
                  {riskScore >= 75 ? 'Low Risk' : riskScore >= 50 ? 'Medium Risk' : 'High Risk'}
                </p>
              </div>
            </div>
          </Card>

          <Card className="bg-[#1e1e1e] border-[#2e2e2e] p-6 h-[400px] flex flex-col">
            <CardTitle className="text-lg">What Influenced Your Approval</CardTitle>
            <div className="flex-1 mt-4">
              <canvas ref={chartRefs.shap}></canvas>
            </div>
            <p className="text-[10px] text-muted-foreground mt-4 text-center">
              Powered by SHAP explainability — the same technique used in enterprise credit systems
            </p>
          </Card>
        </div>

        {/* Row 2: EMI & Repayment */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="bg-[#1e1e1e] border-[#2e2e2e] p-6 h-[400px] flex flex-col relative">
            <CardTitle className="text-lg text-center">EMI Breakdown</CardTitle>
            <div className="flex-1 mt-4">
              <canvas ref={chartRefs.emi}></canvas>
            </div>
            {/* Center Text Overlay */}
            <div className="absolute inset-x-0 top-[45%] pointer-events-none flex flex-col items-center justify-center">
              <p className="text-[10px] text-muted-foreground uppercase opacity-80">Total Payable</p>
              <p className="text-xl font-bold text-white">{formatCurrency(totalPayable)}</p>
              <p className="text-xs text-accent mt-1">EMI: {formatCurrency(emi)}/mo</p>
            </div>
          </Card>

          <Card className="bg-[#1e1e1e] border-[#2e2e2e] p-6 h-[400px] flex flex-col">
            <CardTitle className="text-lg">Year-wise Repayment Breakdown</CardTitle>
            <div className="flex-1 mt-4">
              <canvas ref={chartRefs.repayment}></canvas>
            </div>
            <p className="text-[10px] text-muted-foreground mt-4 flex items-center gap-1 justify-center">
              <Info className="w-3 h-3" />
              Notice how interest reduces and principal increases each year as your loan matures.
            </p>
          </Card>
        </div>

        {/* Row 3: Radar Chart */}
        <Card className="bg-[#1e1e1e] border-[#2e2e2e] p-6 h-[450px] flex flex-col md:max-w-[70%] md:mx-auto">
          <CardTitle className="text-lg text-center">Your Profile vs Approved Borrowers</CardTitle>
          <CardDescription className="text-center">You meet or exceed the benchmark on most parameters</CardDescription>
          <div className="flex-1 mt-4">
            <canvas ref={chartRefs.radar}></canvas>
          </div>
        </Card>
      </div>

      <div className="flex justify-center pb-12">
        <Button 
          variant="accent" 
          size="lg" 
          className="px-8 shadow-glow hover:scale-105 transition-all"
          onClick={handleDownloadPDF}
        >
          <Download className="mr-2 h-5 w-5" />
          Download Loan Report (PDF)
        </Button>
      </div>
    </div>
  );
};
