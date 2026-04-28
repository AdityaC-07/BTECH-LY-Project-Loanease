import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Download, Info, TrendingUp, AlertCircle, CheckCircle2, BarChart3 } from "lucide-react";
import { API_BASE_URL } from "@/config";
import { toast } from "sonner";

interface AnalyticsDashboardProps {
  sessionId: string;
  customerName: string;
}

declare global {
  interface Window {
    Chart: any;
    html2canvas: any;
    jspdf: any;
  }
}

export const AnalyticsDashboard = ({ sessionId, customerName }: AnalyticsDashboardProps) => {
  const [analyticsData, setAnalyticsData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loanAmount, setLoanAmount] = useState(500000);
  const [interestRate, setInterestRate] = useState(11.0);
  const [tenure, setTenure] = useState(60);
  const dashboardRef = useRef<HTMLDivElement>(null);

  // Fetch analytics data from backend
  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/analytics/${sessionId}`);
        if (response.ok) {
          const data = await response.json();
          setAnalyticsData(data);
          
          // Set initial values from backend data
          setLoanAmount(data.loan_data.amount);
          setInterestRate(data.loan_data.rate);
          setTenure(data.loan_data.tenure_months);
        }
      } catch (error) {
        console.error('Failed to fetch analytics:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, [sessionId]);

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
    if (!window.Chart || !analyticsData) return;

    const Chart = window.Chart;

    // Destroy existing instances to prevent memory leaks
    Object.values(chartInstances.current).forEach((chart) => chart?.destroy());

    const riskScore = analyticsData.credit_data.risk_score;
    const shapFactors = analyticsData.credit_data.shap_factors;

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
          labels: shapFactors.map(d => d.feature),
          datasets: [{
            label: 'Impact Score',
            data: shapFactors.map(d => d.value),
            backgroundColor: shapFactors.map(d => d.value >= 0 ? '#F5C518' : '#ef4444'),
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
    if (chartRefs.radar.current && analyticsData.benchmark) {
      const benchmark = analyticsData.benchmark;
      const applicantData = [
        analyticsData.credit_data.credit_score, // Credit Score
        75, // Monthly Income (normalized)
        80, // Loan-to-Income (normalized)
        85, // Employment Stability
        90, // Repayment History
        60  // Co-applicant Support
      ];
      
      const benchmarkData = [
        benchmark.avg_credit_score,
        benchmark.avg_income_normalized,
        benchmark.avg_loan_to_income,
        benchmark.avg_employment,
        benchmark.avg_repayment,
        benchmark.avg_coapplicant
      ];

      chartInstances.current.radar = new Chart(chartRefs.radar.current, {
        type: 'radar',
        data: {
          labels: ['Credit Score', 'Monthly Income', 'Loan-to-Income', 'Employment Stability', 'Repayment History', 'Co-applicant Support'],
          datasets: [
            {
              label: 'You',
              data: applicantData,
              borderColor: '#F5C518',
              backgroundColor: 'rgba(245, 197, 24, 0.3)',
              fill: true,
            },
            {
              label: 'Avg Approved Borrower',
              data: benchmarkData,
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
  }, [loanAmount, interestRate, tenure, analyticsData]);

  const handleDownloadPDF = async () => {
    try {
      // Check if libraries are loaded
      if (!window.html2canvas) {
        toast.error("HTML2Canvas library not loaded");
        return;
      }
      
      if (!window.jspdf) {
        toast.error("jsPDF library not loaded");
        return;
      }
      
      if (!dashboardRef.current) {
        toast.error("Dashboard content not available");
        return;
      }

      // Show loading state
      toast.loading("Generating PDF...");

      const canvas = await window.html2canvas(dashboardRef.current, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#1a1a1a',
        logging: false,
      });
      
      const imgData = canvas.toDataURL('image/png');
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF('p', 'mm', 'a4');
      
      const imgProps = pdf.getImageProperties(imgData);
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = (imgProps.height * pdfWidth) / imgProps.width;
      
      // Set dark background
      pdf.setFillColor(26, 26, 26);
      pdf.rect(0, 0, pdfWidth, pdf.internal.pageSize.getHeight(), 'F');
      
      // Add header text
      pdf.setTextColor(255, 255, 255);
      pdf.setFontSize(18);
      pdf.text("LoanEase Analytics Report", 20, 20);
      pdf.setFontSize(10);
      pdf.text(`Applicant: ${customerName || 'N/A'}`, 20, 28);
      pdf.text(`Date: ${new Date().toLocaleDateString('en-IN')}`, 20, 33);
      pdf.text(`Session ID: ${sessionId || 'N/A'}`, 20, 38);
      
      // Add the dashboard image
      pdf.addImage(imgData, 'PNG', 0, 45, pdfWidth, pdfHeight);
      
      // Save the PDF
      const fileName = `LoanEase_Report_${customerName?.replace(/\s+/g, '_') || 'Unknown'}_${new Date().toISOString().split('T')[0]}.pdf`;
      pdf.save(fileName);
      
      toast.success("PDF downloaded successfully!");
    } catch (error) {
      console.error('PDF generation error:', error);
      toast.error("Failed to generate PDF. Please try again.");
    }
  };

  if (loading) {
    return (
      <div className="w-full max-w-6xl mx-auto p-4 space-y-8 animate-slide-up" id="analytics-section">
        <div className="text-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent mx-auto"></div>
          <p className="text-muted-foreground">Loading your analytics...</p>
        </div>
      </div>
    );
  }

  if (!analyticsData) {
    return (
      <div className="w-full max-w-6xl mx-auto p-4 space-y-8 animate-slide-up" id="analytics-section">
        <div className="text-center space-y-4">
          <p className="text-muted-foreground">Unable to load analytics data.</p>
        </div>
      </div>
    );
  }

  const riskScore = analyticsData.credit_data.risk_score;

  return (
    <div className="w-full max-w-6xl mx-auto p-4 space-y-8 animate-slide-up" id="analytics-section">
      <div className="text-center space-y-2">
        <h2 className="text-3xl font-bold font-display text-white flex items-center justify-center gap-2">
        <BarChart3 className="w-8 h-8" />
        Your Loan Insights
      </h2>
        <p className="text-muted-foreground">Complete breakdown of your loan and approval profile</p>
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
            <p className="text-sm text-muted-foreground mb-1 uppercase tracking-wider">YOUR EMI</p>
            <p className="text-4xl font-bold text-accent">{formatCurrency(emi)}</p>
            <p className="text-xs text-muted-foreground">per month</p>
          </div>

          {/* Info Boxes */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-4 bg-card rounded-lg border border-border/50">
              <p className="text-sm text-muted-foreground mb-1">Total Payable</p>
              <p className="text-xl font-bold text-white">{formatCurrency(totalPayable)}</p>
            </div>
            <div className="text-center p-4 bg-card rounded-lg border border-border/50">
              <p className="text-sm text-muted-foreground mb-1">Total Interest</p>
              <p className="text-xl font-bold text-accent">{formatCurrency(totalInterest)}</p>
            </div>
            <div className="text-center p-4 bg-card rounded-lg border border-border/50">
              <p className="text-sm text-muted-foreground mb-1">Interest %</p>
              <p className="text-xl font-bold text-white">{((totalInterest / totalPayable) * 100).toFixed(1)}%</p>
              <p className="text-xs text-muted-foreground">of total</p>
            </div>
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
        {/* Row 1: EMI Calculator (full width) - Already above */}
        
        {/* Row 2: Doughnut | Gauge */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="bg-[#1a1a1a] border-[#2a2a2a] rounded-2xl p-5">
            <CardTitle className="text-lg mb-4 text-center">EMI Breakdown</CardTitle>
            <div className="relative h-64">
              <canvas ref={chartRefs.emi}></canvas>
              {/* Center Text Overlay */}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <p className="text-[10px] text-[#9ca3af] uppercase">Total Payable</p>
                <p className="text-lg font-bold text-white">{formatCurrency(totalPayable)}</p>
                <p className="text-xs text-[#F5C518] mt-1">{formatCurrency(emi)}/mo</p>
              </div>
            </div>
            {/* Legend */}
            <div className="flex justify-center gap-6 mt-4 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-[#F5C518] rounded"></div>
                <span className="text-[#9ca3af]">Principal {formatCurrency(loanAmount)} ({((loanAmount/totalPayable)*100).toFixed(1)}%)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-[#2a2a2a] rounded"></div>
                <span className="text-[#9ca3af]">Interest {formatCurrency(totalInterest)} ({((totalInterest/totalPayable)*100).toFixed(1)}%)</span>
              </div>
            </div>
          </Card>

          <Card className="bg-[#1a1a1a] border-[#2a2a2a] rounded-2xl p-5">
            <CardTitle className="text-lg mb-4 text-center">Risk Score Gauge</CardTitle>
            <div className="relative h-64">
              <canvas ref={chartRefs.risk}></canvas>
              {/* Needle and Score */}
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <p className="text-5xl font-bold text-white">{riskScore}</p>
                <p className={`text-sm font-semibold uppercase tracking-widest ${
                  riskScore >= 75 ? 'text-green-500' : 
                  riskScore >= 50 ? 'text-yellow-500' : 'text-red-500'
                }`}>
                  {analyticsData.credit_data.risk_tier}
                </p>
              </div>
            </div>
          </Card>
        </div>

        {/* Row 3: Yearly Bar (full width) */}
        <Card className="bg-[#1a1a1a] border-[#2a2a2a] rounded-2xl p-5">
          <CardTitle className="text-lg mb-4 text-center">Yearly Amortization Breakdown</CardTitle>
          <div className="h-64">
            <canvas ref={chartRefs.repayment}></canvas>
          </div>
          <p className="text-[10px] text-[#9ca3af] mt-4 text-center">
            Interest dominates early years — this is why prepayment saves money.
          </p>
        </Card>

        {/* Row 4: SHAP bars | Radar */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="bg-[#1a1a1a] border-[#2a2a2a] rounded-2xl p-5">
            <CardTitle className="text-lg mb-2">What Influenced Your Approval</CardTitle>
            <CardDescription className="text-sm text-[#9ca3af] mb-4">Powered by SHAP Explainability</CardDescription>
            <div className="h-64">
              <canvas ref={chartRefs.shap}></canvas>
            </div>
          </Card>

          <Card className="bg-[#1a1a1a] border-[#2a2a2a] rounded-2xl p-5">
            <CardTitle className="text-lg mb-2">Applicant Benchmark Radar</CardTitle>
            <CardDescription className="text-sm text-[#9ca3af] mb-4">You vs Avg Approved Borrower</CardDescription>
            <div className="h-64">
              <canvas ref={chartRefs.radar}></canvas>
            </div>
          </Card>
        </div>
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
