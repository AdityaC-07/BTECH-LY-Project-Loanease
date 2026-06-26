import { useState, useEffect, useRef } from 'react';
import { ENDPOINTS } from '@/config';

interface FormData {
  name: string;
  monthly_income: number | null;
  loan_amount: number | null;
}

interface EligibilityResult {
  eligibility_status: 'STRONG' | 'MODERATE' | 'CONDITIONAL' | 'INELIGIBLE';
  estimated_emi: number;
  estimated_tenure_months: number;
  dti_ratio: number;
  safe_loan_cap: number;
  reason: string;
  next_action: 'PROCEED_TO_KYC' | 'ADJUST_AMOUNT' | 'CONSULT_AGENT';
}

export default function SequentialEligibilityForm() {
  const [stage, setStage] = useState<1 | 2 | 3 | 'results'>(1);
  const [formData, setFormData] = useState<FormData>({
    name: '',
    monthly_income: null,
    loan_amount: null
  });
  const [eligibilityResult, setEligibilityResult] = useState<EligibilityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [validationFeedback, setValidationFeedback] = useState<Record<string, string>>({});
  
  const nameInputRef = useRef<HTMLInputElement>(null);
  const incomeInputRef = useRef<HTMLInputElement>(null);
  const loanInputRef = useRef<HTMLInputElement>(null);

  // Auto-focus on name input when component mounts
  useEffect(() => {
    if (stage === 1 && nameInputRef.current) {
      nameInputRef.current.focus();
    }
  }, [stage]);

  // Format currency for display
  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount);
  };

  // Stage 1: Validate name
  const validateName = (name: string): { isValid: boolean; message: string } => {
    if (name.length < 3) {
      return { isValid: false, message: 'Name must be at least 3 characters' };
    }
    if (name.length > 100) {
      return { isValid: false, message: 'Name must not exceed 100 characters' };
    }
    if (!/^[a-zA-Z\s]+$/.test(name)) {
      return { isValid: false, message: 'Invalid characters detected' };
    }
    return { isValid: true, message: 'Name validated' };
  };

  // Stage 2: Validate income
  const validateIncome = (income: number): { isValid: boolean; message: string } => {
    if (income < 10000) {
      return { isValid: false, message: 'Below minimum required' };
    }
    if (income > 50000000) {
      return { isValid: false, message: 'Exceeds maximum limit' };
    }
    return { isValid: true, message: 'Income verified' };
  };

  // Stage 3: Validate loan amount against DTI
  const validateLoanAmount = (amount: number, income: number): { isValid: boolean; message: string; maxLoan?: number } => {
    if (amount < 50000) {
      return { isValid: false, message: 'Minimum loan amount is ₹50,000' };
    }
    
    const maxDTILoan = (60 * income) / 2; // 60 months × monthly income / 2 (50% DTI)
    
    if (amount > maxDTILoan) {
      return { 
        isValid: false, 
        message: 'Exceeds DTI limit of 50%',
        maxLoan: maxDTILoan
      };
    }
    
    return { isValid: true, message: 'Amount acceptable' };
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setFormData(prev => ({ ...prev, name: value }));
    
    const validation = validateName(value);
    setValidationFeedback(prev => ({ ...prev, name: validation.message }));
    setErrors(prev => ({ ...prev, name: validation.isValid ? '' : 'Name must contain only alphabetic characters and spaces (3-100 characters)' }));
  };

  const handleIncomeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/[^0-9]/g, '');
    const numericValue = value ? parseInt(value, 10) : null;
    setFormData(prev => ({ ...prev, monthly_income: numericValue }));
    
    if (numericValue) {
      const validation = validateIncome(numericValue);
      setValidationFeedback(prev => ({ ...prev, income: validation.message }));
      setErrors(prev => ({ 
        ...prev, 
        income: validation.isValid ? '' : 'Monthly income must be between Rs. 10,000 and Rs. 5,00,00,000'
      }));
    }
  };

  const handleLoanAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/[^0-9]/g, '');
    const numericValue = value ? parseInt(value, 10) : null;
    setFormData(prev => ({ ...prev, loan_amount: numericValue }));
    
    if (numericValue && formData.monthly_income) {
      const validation = validateLoanAmount(numericValue, formData.monthly_income);
      setValidationFeedback(prev => ({ ...prev, loan: validation.message }));
      setErrors(prev => ({ 
        ...prev, 
        loan: validation.isValid ? '' : `Based on your income, maximum loan: ${formatCurrency(validation.maxLoan || 0)}. You can borrow up to this amount.`
      }));
    }
  };

  const handleStage1Submit = () => {
    const validation = validateName(formData.name);
    if (!validation.isValid) {
      setErrors(prev => ({ ...prev, name: 'Name must contain only alphabetic characters and spaces (3-100 characters)' }));
      return;
    }
    setStage(2);
    setTimeout(() => incomeInputRef.current?.focus(), 100);
  };

  const handleStage2Submit = () => {
    if (!formData.monthly_income) {
      setErrors(prev => ({ ...prev, income: 'Monthly income is required' }));
      return;
    }
    const validation = validateIncome(formData.monthly_income);
    if (!validation.isValid) {
      setErrors(prev => ({ ...prev, income: 'Monthly income must be between Rs. 10,000 and Rs. 5,00,00,000' }));
      return;
    }
    setStage(3);
    setTimeout(() => loanInputRef.current?.focus(), 100);
  };

  const handleStage3Submit = async () => {
    if (!formData.loan_amount) {
      setErrors(prev => ({ ...prev, loan: 'Loan amount is required' }));
      return;
    }
    if (!formData.monthly_income) {
      setErrors(prev => ({ ...prev, loan: 'Income information is missing' }));
      return;
    }
    
    const validation = validateLoanAmount(formData.loan_amount, formData.monthly_income);
    if (!validation.isValid) {
      setErrors(prev => ({ 
        ...prev, 
        loan: `Based on your income, maximum loan: ${formatCurrency(validation.maxLoan || 0)}. You can borrow up to this amount.`
      }));
      return;
    }

    // Submit to backend
    setLoading(true);
    try {
      const response = await fetch(ENDPOINTS.quick_eligibility, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'QUICK_ELIGIBILITY_CHECK',
          customer_name: formData.name,
          monthly_income: formData.monthly_income,
          desired_loan_amount: formData.loan_amount,
          stage: 'INITIATED'
        })
      });

      if (!response.ok) {
        throw new Error('Failed to check eligibility');
      }

      const result: EligibilityResult = await response.json();
      setEligibilityResult(result);
      setStage('results');
    } catch (error) {
      console.error('Error checking eligibility:', error);
      setErrors(prev => ({ 
        ...prev, 
        submit: 'Failed to check eligibility. Please try again.' 
      }));
    } finally {
      setLoading(false);
    }
  };

  const handleAdjustAmount = () => {
    setStage(3);
    setTimeout(() => loanInputRef.current?.focus(), 100);
  };

  const handleProceedToKYC = () => {
    // This will be handled by the parent component
    window.dispatchEvent(new CustomEvent('proceedToKYC', { 
      detail: { 
        formData, 
        eligibilityResult 
      } 
    }));
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'STRONG':
        return '#51CF66';
      case 'MODERATE':
        return '#F5C518';
      case 'CONDITIONAL':
        return '#FFA500';
      case 'INELIGIBLE':
        return '#FF6B6B';
      default:
        return '#666';
    }
  };

  return (
    <div className="w-full max-w-[500px] mx-auto p-6" style={{ backgroundColor: '#141414' }}>
      {/* Stage 1: Personal Identification */}
      {stage === 1 && (
        <div className="space-y-4">
          <div>
            <label 
              className="block mb-2 font-bold" 
              style={{ fontSize: '16px', color: '#F5C518' }}
            >
              Enter your full name (as per government ID)
            </label>
            <input
              ref={nameInputRef}
              type="text"
              value={formData.name}
              onChange={handleNameChange}
              placeholder="e.g., Rahul Kumar"
              className="w-full px-4 py-3 rounded focus:outline-none transition-all"
              style={{
                backgroundColor: '#2A2A2A',
                color: '#FFFFFF',
                fontSize: '16px',
                fontFamily: 'DM Sans, sans-serif',
                border: errors.name ? '2px solid #FF6B6B' : '1px solid #666'
              }}
              onFocus={(e) => e.target.style.borderColor = '#F5C518'}
              onBlur={(e) => e.target.style.borderColor = errors.name ? '#FF6B6B' : '#666'}
            />
            {validationFeedback.name && (
              <div 
                className="mt-2 text-sm"
                style={{ color: errors.name ? '#FF6B6B' : '#51CF66', fontFamily: 'sans-serif' }}
              >
                {validationFeedback.name}
              </div>
            )}
            {errors.name && (
              <div className="mt-2 text-sm" style={{ color: '#FF6B6B', fontFamily: 'sans-serif' }}>
                {errors.name}
              </div>
            )}
          </div>
          <button
            onClick={handleStage1Submit}
            disabled={!formData.name || !!errors.name}
            className="w-full py-3 px-6 rounded font-bold transition-all"
            style={{
              backgroundColor: '#F5C518',
              color: '#000000',
              fontSize: '16px',
              opacity: (!formData.name || !!errors.name) ? 0.5 : 1,
              cursor: (!formData.name || !!errors.name) ? 'not-allowed' : 'pointer'
            }}
            onMouseEnter={(e) => {
              if (formData.name && !errors.name) {
                e.currentTarget.style.filter = 'brightness(110%)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'brightness(100%)';
            }}
          >
            Continue
          </button>
        </div>
      )}

      {/* Stage 2: Monthly Income Declaration */}
      {stage === 2 && (
        <div className="space-y-4">
          <div>
            <label 
              className="block mb-2 font-bold" 
              style={{ fontSize: '16px', color: '#F5C518' }}
            >
              Enter your verified monthly income (in INR)
            </label>
            <input
              ref={incomeInputRef}
              type="text"
              value={formData.monthly_income ? formData.monthly_income.toString() : ''}
              onChange={handleIncomeChange}
              placeholder="e.g., 50,000"
              className="w-full px-4 py-3 rounded focus:outline-none transition-all"
              style={{
                backgroundColor: '#2A2A2A',
                color: '#FFFFFF',
                fontSize: '16px',
                fontFamily: 'DM Sans, sans-serif',
                border: errors.income ? '2px solid #FF6B6B' : '1px solid #666'
              }}
              onFocus={(e) => e.target.style.borderColor = '#F5C518'}
              onBlur={(e) => e.target.style.borderColor = errors.income ? '#FF6B6B' : '#666'}
            />
            {validationFeedback.income && (
              <div 
                className="mt-2 text-sm"
                style={{ color: errors.income ? '#FF6B6B' : '#51CF66', fontFamily: 'sans-serif' }}
              >
                {validationFeedback.income}
              </div>
            )}
            {errors.income && (
              <div className="mt-2 text-sm" style={{ color: '#FF6B6B', fontFamily: 'sans-serif' }}>
                {errors.income}
              </div>
            )}
          </div>
          <button
            onClick={handleStage2Submit}
            disabled={!formData.monthly_income || !!errors.income}
            className="w-full py-3 px-6 rounded font-bold transition-all"
            style={{
              backgroundColor: '#F5C518',
              color: '#000000',
              fontSize: '16px',
              opacity: (!formData.monthly_income || !!errors.income) ? 0.5 : 1,
              cursor: (!formData.monthly_income || !!errors.income) ? 'not-allowed' : 'pointer'
            }}
            onMouseEnter={(e) => {
              if (formData.monthly_income && !errors.income) {
                e.currentTarget.style.filter = 'brightness(110%)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'brightness(100%)';
            }}
          >
            Next
          </button>
        </div>
      )}

      {/* Stage 3: Desired Loan Amount */}
      {stage === 3 && (
        <div className="space-y-4">
          <div>
            <label 
              className="block mb-2 font-bold" 
              style={{ fontSize: '16px', color: '#F5C518' }}
            >
              How much would you like to borrow? (in INR)
            </label>
            <input
              ref={loanInputRef}
              type="text"
              value={formData.loan_amount ? formData.loan_amount.toString() : ''}
              onChange={handleLoanAmountChange}
              placeholder="e.g., 2,50,000"
              className="w-full px-4 py-3 rounded focus:outline-none transition-all"
              style={{
                backgroundColor: '#2A2A2A',
                color: '#FFFFFF',
                fontSize: '16px',
                fontFamily: 'DM Sans, sans-serif',
                border: errors.loan ? '2px solid #FF6B6B' : '1px solid #666'
              }}
              onFocus={(e) => e.target.style.borderColor = '#F5C518'}
              onBlur={(e) => e.target.style.borderColor = errors.loan ? '#FF6B6B' : '#666'}
            />
            {validationFeedback.loan && (
              <div 
                className="mt-2 text-sm"
                style={{ color: errors.loan ? '#FF6B6B' : '#51CF66', fontFamily: 'sans-serif' }}
              >
                {validationFeedback.loan}
              </div>
            )}
            {errors.loan && (
              <div className="mt-2 text-sm" style={{ color: '#FF6B6B', fontFamily: 'sans-serif' }}>
                {errors.loan}
              </div>
            )}
          </div>
          <button
            onClick={handleStage3Submit}
            disabled={!formData.loan_amount || !!errors.loan}
            className="w-full py-3 px-6 rounded font-bold transition-all"
            style={{
              backgroundColor: '#F5C518',
              color: '#000000',
              fontSize: '16px',
              opacity: (!formData.loan_amount || !!errors.loan) ? 0.5 : 1,
              cursor: (!formData.loan_amount || !!errors.loan) ? 'not-allowed' : 'pointer'
            }}
            onMouseEnter={(e) => {
              if (formData.loan_amount && !errors.loan) {
                e.currentTarget.style.filter = 'brightness(110%)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'brightness(100%)';
            }}
          >
            Check Eligibility
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-12 space-y-4">
          <div className="w-12 h-12 border-4 border-t-4 rounded-full animate-spin" 
               style={{ borderColor: '#F5C518', borderTopColor: 'transparent' }} />
          <p className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
            Calculating quick eligibility preview...
          </p>
        </div>
      )}

      {/* Results Display */}
      {stage === 'results' && eligibilityResult && (
        <div className="space-y-6">
          <div 
            className="p-6 rounded-lg"
            style={{ 
              backgroundColor: '#2A2A2A',
              border: '1px solid #333'
            }}
          >
            <h3 
              className="text-xl font-bold mb-4"
              style={{ color: '#F5C518', fontFamily: 'DM Sans, sans-serif' }}
            >
              Eligibility Assessment
            </h3>
            
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  Eligibility Status:
                </span>
                <span 
                  className="font-bold"
                  style={{ 
                    color: getStatusColor(eligibilityResult.eligibility_status),
                    fontFamily: 'DM Sans, sans-serif'
                  }}
                >
                  {eligibilityResult.eligibility_status}
                </span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  Requested Loan:
                </span>
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  {formatCurrency(formData.loan_amount || 0)}
                </span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  Monthly Income:
                </span>
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  {formatCurrency(formData.monthly_income || 0)}
                </span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  Estimated EMI:
                </span>
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  {formatCurrency(eligibilityResult.estimated_emi)}
                </span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  EMI-to-Income Ratio:
                </span>
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  {(eligibilityResult.dti_ratio * 100).toFixed(2)}%
                </span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  Safe Cap:
                </span>
                <span className="text-white" style={{ fontFamily: 'DM Sans, sans-serif' }}>
                  {formatCurrency(eligibilityResult.safe_loan_cap)}
                </span>
              </div>
            </div>
            
            {eligibilityResult.reason && (
              <div className="mt-4 pt-4 border-t" style={{ borderColor: '#333' }}>
                <p className="text-sm" style={{ color: '#999', fontFamily: 'DM Sans, sans-serif' }}>
                  {eligibilityResult.reason}
                </p>
              </div>
            )}
          </div>
          
          <div className="flex gap-4">
            <button
              onClick={handleProceedToKYC}
              className="flex-1 py-3 px-6 rounded font-bold transition-all"
              style={{
                backgroundColor: '#F5C518',
                color: '#000000',
                fontSize: '16px',
                fontFamily: 'DM Sans, sans-serif'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.filter = 'brightness(110%)';
                e.currentTarget.style.boxShadow = '0 0 16px rgba(245, 197, 24, 0.4)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.filter = 'brightness(100%)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              Proceed to KYC
            </button>
            
            <button
              onClick={handleAdjustAmount}
              className="flex-1 py-3 px-6 rounded font-bold transition-all"
              style={{
                backgroundColor: '#333',
                color: '#FFFFFF',
                fontSize: '16px',
                fontFamily: 'DM Sans, sans-serif',
                border: '1px solid #666'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#444';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = '#333';
              }}
            >
              Adjust Loan Amount
            </button>
          </div>
        </div>
      )}

      {errors.submit && (
        <div className="mt-4 text-sm text-center" style={{ color: '#FF6B6B', fontFamily: 'sans-serif' }}>
          {errors.submit}
        </div>
      )}
    </div>
  );
}
