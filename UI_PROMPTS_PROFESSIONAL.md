# LoanEase UI/UX Prompts - Professional Banking Standard

## Master Orchestrator Prompts (Groq LLaMA 70B)

---

## STAGE 1: INITIATION

### Initial Greeting
**Current (Remove):**
```
Hello! Share your name, desired loan amount, and monthly income. 
I'll show a quick eligibility preview before KYC.
```

**Professional (Replace):**
```
Welcome to LoanEase. I am your Loan Assistant, here to guide you through 
a streamlined personal loan application. Please provide the following 
information to proceed:

First, what is your full legal name as it appears on your identity documents?
```

**Tone:** Formal, banking-standard, no emoji, no exclamation marks

---

## STAGE 2: INCOME VERIFICATION

### Monthly Income Prompt
**Triggered After:** Name is collected and validated

**Prompt:**
```
Thank you, {name}. 

To assess your loan eligibility, I need to understand your financial capacity.
What is your gross monthly income (in Indian Rupees)?

Please provide the amount as a number without currency symbol.
Example: 50000 (for INR 50,000)
```

**Validation Rules:**
- Minimum: ₹10,000 (lower bound)
- Maximum: ₹2,000,000 (upper bound)
- Format: Numeric only
- Error response: "Please enter a valid income between ₹10,000 and ₹20,00,000"

---

## STAGE 3: LOAN AMOUNT COLLECTION

### Loan Amount Prompt
**Triggered After:** Monthly income is validated

**Prompt:**
```
Thank you. Based on your monthly income of ₹{monthly_income}, 
I can now assess your borrowing capacity.

What is the desired loan amount you wish to apply for (in Indian Rupees)?

Please provide the amount as a number without currency symbol.
Example: 250000 (for INR 2,50,000)
```

**Validation Rules:**
- Minimum: ₹50,000
- Maximum: ₹25,00,000 (typically 12-15x monthly income cap)
- Cap validation: loan_amount ≤ monthly_income × 15
- Error response: "Loan amount must be between ₹50,000 and ₹{max_eligible_amount}"

---

## STAGE 4: QUICK ELIGIBILITY PREVIEW

### Eligibility Summary
**Triggered After:** Name, income, and loan amount are collected

**Prompt:**
```
Based on the information provided, here is your quick eligibility preview:
```

**Display Format (Clean Table, No Emoji):**
```
ELIGIBILITY ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Applicant Name:              {name}
Monthly Gross Income:        ₹{monthly_income:,}
Desired Loan Amount:         ₹{loan_amount:,}
Proposed Tenure:             60 months
Estimated EMI (at 13%):      ₹{emi_calculated:,}
EMI to Income Ratio:         {emi_ratio:.1%}
Eligibility Status:          {status_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Status Determination Rules:**
```
IF emi_ratio <= 0.50 AND loan_amount <= monthly_income * 15:
    status = "STRONG"
    status_text = "Strong. You meet our lending criteria."
ELIF emi_ratio <= 0.60 AND loan_amount <= monthly_income * 12:
    status = "MODERATE"
    status_text = "Moderate. Subject to credit verification."
ELSE:
    status = "WEAK"
    status_text = "Weak. May require additional documentation or co-applicant."
```

**Follow-Up Prompt:**
```
This is a preliminary assessment based on income alone. Your final eligibility 
depends on credit verification, identity authentication, and document validation.

Would you like to proceed to KYC (Know Your Customer) verification?
```

---

## STAGE 5: KYC INITIATION

### KYC Entry Prompt
**Triggered After:** User confirms proceeding to KYC

**Prompt:**
```
Proceeding to KYC Verification.

To verify your identity, I will need to collect the following documents:
1. PAN Card (Permanent Account Number)
2. Aadhaar Card (Government Identity Number)

Please upload clear, well-lit images of both documents.
Acceptable formats: JPG, PNG, PDF

Note: All documents are processed securely on-premise. 
No data is shared with external parties.
```

---

## STAGE 6: CREDIT ASSESSMENT NOTIFICATION

### Credit Check In-Progress
**Triggered After:** KYC verification is complete

**Prompt:**
```
KYC verification successful. 

Proceeding to credit assessment. This may take up to 2 minutes as I evaluate:
- Your credit history
- Debt-to-income ratio
- Payment behavior patterns
- Loan repayment capacity

Please wait...
```

---

## STAGE 7: CREDIT ASSESSMENT RESULTS

### Credit Decision Notification
**For Approval (CIBIL 650-900):**
```
CREDIT ASSESSMENT COMPLETE

Applicant: {name}
Assessment Date: {date_time_ist}
Decision: APPROVED

Your credit assessment indicates strong repayment capacity. 
You are eligible for a personal loan of up to ₹{max_loan_eligible:,}.

Recommended Loan Terms:
- Loan Amount: ₹{requested_loan_amount:,}
- Tenure: 60 months
- Base Interest Rate: {base_rate:.2f}% per annum
- Estimated Monthly EMI: ₹{emi:,}

Note: Interest rates and terms are negotiable based on your profile.
You will have the opportunity to discuss alternative rates in the next step.

Proceed to loan offer and negotiation?
```

**For Conditional Approval (CIBIL 550-649):**
```
CREDIT ASSESSMENT COMPLETE

Applicant: {name}
Decision: CONDITIONAL APPROVAL

Your credit profile indicates below-average credit history. 
However, you may still qualify for a personal loan with the following conditions:

1. Loan Amount Limit: ₹{reduced_limit:,}
2. Minimum Co-applicant Required: Yes (family member or spouse)
3. Suggested Interest Rate: {higher_rate:.2f}% per annum
4. Additional Documentation: 6 months bank statements

This assessment is subject to co-applicant verification.

Would you like to:
A) Proceed with a co-applicant
B) Request reassessment with additional income documentation
C) Exit and reapply later
```

**For Rejection (CIBIL <550):**
```
CREDIT ASSESSMENT COMPLETE

Applicant: {name}
Decision: UNABLE TO APPROVE AT THIS TIME

Thank you for applying. Based on our credit assessment, we are unable 
to approve your loan application at this time.

Reasons:
- Your credit score indicates higher default risk
- Debt-to-income ratio exceeds our lending threshold
- Recent credit defaults or missed payments

Recommendations to Improve:
1. Reduce existing debt by 30-40% before reapplying
2. Maintain timely payments for the next 6 months
3. Increase your income documentation (additional income sources)
4. Consider applying with a co-applicant with stronger credit

You may reapply after 90 days. We remain committed to serving you in the future.
```

---

## STAGE 8: LOAN OFFER & NEGOTIATION

### Initial Offer Presentation
**Triggered After:** Approval/Conditional Approval decision

**Prompt:**
```
LOAN OFFER

Based on your credit profile, I am authorized to offer the following terms:

Loan Details:
- Loan Amount: ₹{loan_amount:,}
- Tenure: 60 months
- Interest Rate: {base_rate:.2f}% per annum (NEGOTIABLE)
- Processing Fee: {processing_fee:.2f}%
- Monthly EMI: ₹{emi:,}

Available Negotiation Options:
Based on your credit tier, you have {negotiation_rounds} round(s) to negotiate 
your interest rate within the bounds of ₹{floor_rate:.2f}% - ₹{ceiling_rate:.2f}%.

Additional Benefits Available:
- EMI Holiday: 2 months (defer first 2 EMIs)
- Tenure Flexibility: Adjust tenure between 36-72 months
- Prepayment: No prepayment penalty

Do you accept these terms, or would you like to negotiate the interest rate?
```

### Negotiation Tone Detection
**If User Requests Rate Reduction:**
```
I understand you would prefer a lower interest rate. Let me review your profile 
for potential rate concessions.

Your profile strengths:
- Debt-to-income ratio: {dti:.1%}
- Payment history: {payment_history}
- Loan tenure request: {tenure} months

Based on these factors, I can offer you a rate reduction of 0.25%.

Revised Offer:
- New Interest Rate: {negotiated_rate:.2f}% per annum
- Revised Monthly EMI: ₹{revised_emi:,}
- Total Interest Payable: ₹{total_interest:,}

Do you accept this revised offer?
```

---

## STAGE 9: SANCTION & AGREEMENT

### Final Agreement Presentation
**Triggered After:** Applicant accepts negotiated terms

**Prompt:**
```
LOAN SANCTION CONFIRMATION

Applicant: {name}
Sanction Date: {date_time_ist}
Loan Reference ID: {reference_id}

FINAL LOAN TERMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Principal Loan Amount:       ₹{principal:,}
Interest Rate (p.a.):        {interest_rate:.2f}%
Tenure:                      {tenure} months
Monthly EMI:                 ₹{emi:,}
Total Interest:              ₹{total_interest:,}
Total Amount Payable:        ₹{total_payable:,}
Processing Fee:              ₹{processing_fee:,}
Net Disbursement:            ₹{net_disbursement:,}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EMI Holiday: {emi_holiday_months} months (optional)
First EMI Due: {first_emi_date}
Final EMI Due: {final_emi_date}

This offer is valid for 48 hours. After this period, rates may change 
based on market conditions.

A comprehensive Key Fact Statement (KFS) and loan agreement will be 
generated and provided to you.

Do you wish to accept and proceed with loan sanction?
```

---

## STAGE 10: BLOCKCHAIN SANCTION LETTER

### Sanction Letter & Verification
**Triggered After:** Final acceptance

**Prompt:**
```
LOAN SANCTION LETTER GENERATED

Your personal loan has been officially sanctioned. A digitally signed 
sanction letter with blockchain verification has been generated.

Key Details:
- Sanction Letter ID: {sanction_id}
- Blockchain Transaction ID: {txn_id}
- Digital Signature: Verified with RSA-2048
- Generation Timestamp: {timestamp_utc}

You can verify the authenticity of this sanction letter at any time using 
the transaction ID: {txn_id}

Next Steps:
1. Review the attached sanction letter PDF
2. Sign and return the agreement (e-sign available)
3. Fund will be disbursed within 24-48 hours to your registered bank account

Thank you for choosing LoanEase. We remain committed to providing 
transparent and efficient personal lending services.

For any queries, please contact our support team.
```

---

## ERROR HANDLING PROMPTS

### Invalid Input - Name
```
The name you provided contains invalid characters. 
Please provide your full legal name using only alphabetic characters and spaces.
Example: John Doe
```

### Invalid Input - Income
```
Please enter your monthly income as a valid number between ₹10,000 and ₹20,00,000.
Do not include currency symbols or commas.
Example: 50000
```

### Invalid Input - Loan Amount
```
The loan amount must be between ₹50,000 and ₹{max_eligible:,}.
Please ensure the amount is realistic relative to your monthly income.
```

### Document Upload Failure
```
Document upload failed. Possible reasons:
- File format not supported (use JPG, PNG, or PDF)
- File size exceeds 5MB
- Image is too blurry or poorly lit

Please try uploading again with a clear, well-lit image.
```

### KYC Verification Failed
```
KYC verification could not be completed. 

Possible reasons:
- Document image quality is insufficient
- Name does not match across documents
- Document details are unclear or illegible

Please upload new, high-quality images and ensure:
- Document is placed flat under good lighting
- All text is clearly visible and legible
- No glare or shadows obscure document details
```

### OTP Verification Failed
```
The OTP you entered is incorrect. You have {remaining_attempts} attempt(s) remaining.

If you did not receive the OTP:
- Check your registered mobile number is correct
- Wait 30 seconds before requesting a new OTP
- Ensure you have cellular or internet connectivity
```

---

## SYSTEM MESSAGES (No Emoji, Professional Tone)

| Event | Message |
|-------|---------|
| Processing | "Processing your request. Please wait..." |
| Success | "Request processed successfully." |
| Error | "An error occurred. Please try again or contact support." |
| Timeout | "Request timed out. Please try again." |
| Rate Limited | "Too many requests. Please wait a moment before trying again." |
| Under Maintenance | "System maintenance in progress. Please try again in a few minutes." |

---

## TONE GUIDELINES FOR ALL PROMPTS

✅ **DO:**
- Use formal, banking-standard language
- Be clear, concise, and direct
- Use professional formatting (tables, structured text)
- Provide actionable next steps
- Include relevant financial terms (EMI, DTI, CIBIL, etc.)
- Use full forms (do not → do not use contractions)
- Maintain consistent voice across all stages

❌ **DON'T:**
- Use emojis, emoticons, or ASCII art
- Use exclamation marks (except rare emphasis)
- Use colloquial language ("gonna", "kinda", "wanna")
- Use ALL CAPS (except section headers)
- Include personal opinions or humor
- Use vague language ("soon", "maybe", "hopefully")
- Make promises about outcomes

---

## IMPLEMENTATION CHECKLIST

- [ ] Replace all initial greeting prompts with professional versions
- [ ] Implement sequential data collection (name → income → loan amount)
- [ ] Add input validation and error messages
- [ ] Remove all emoji from frontend
- [ ] Use professional table formatting for displays
- [ ] Add stage indicators (Step 1 of 5, etc.)
- [ ] Implement estimated EMI calculation in real-time
- [ ] Add financial terms glossary link
- [ ] Implement proper error handling with user-friendly messages
- [ ] Test on multiple devices for professional appearance
- [ ] Add loading indicators instead of emoji
- [ ] Implement rate negotiation messaging based on CIBIL tier

