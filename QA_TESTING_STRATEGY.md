# LoanEase QA & Testing Strategy
## Professional Test Plan & Quality Assurance Framework

---

## EXECUTIVE SUMMARY

This document outlines a comprehensive quality assurance strategy to validate LoanEase across all credit score tiers, negotiation pathways, and edge cases. The testing approach follows industry-standard software testing methodologies (ISTQB-aligned) and ensures 100% coverage of critical loan lifecycle stages.

**Current Status:**
- Team: 4 developers, 2 with working implementations
- Known Test Coverage: 2 credit buckets (592 CIBIL, <100 CIBIL)
- Unknown: 4 remaining buckets, all negotiation paths, edge cases
- Risk: Untested critical paths may fail in production

**Objective:** Define test cases that validate all 6 CIBIL tiers and ensure negotiation engine works correctly for all risk profiles.

---

## 1. TEST STRATEGY OVERVIEW

### 1.1 Testing Pyramid (by Volume)

```
        △ E2E Tests (5%)
       ╱ ╲
      ╱   ╲  Integration Tests (20%)
     ╱     ╲
    ╱       ╲ Unit Tests (75%)
   ╱_________╲
```

### 1.2 Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| **Unit** | Individual functions (CIBIL calc, Verhoeff, DTI) | pytest | 75% |
| **Integration** | Agent-to-agent communication (Orchestrator → Credit → Negotiation) | pytest + FastAPI test client | 20% |
| **E2E (API)** | Complete loan lifecycle (KYC → Credit → Offer → Sanction) | Python requests + pytest | 5% |
| **E2E (UI)** | User flows via browser (if time permits) | Selenium/Playwright | Ad-hoc |

### 1.3 Test Types

1. **Functional Testing** - Does each feature work as designed?
2. **Data Validation Testing** - Are inputs validated correctly?
3. **Boundary Testing** - Do edge cases behave correctly?
4. **Error Handling Testing** - Are errors caught and handled gracefully?
5. **Regression Testing** - Did recent changes break existing functionality?
6. **Security Testing** - Are sensitive data protected?
7. **Performance Testing** - Are response times acceptable?

---

## 2. TEST SCOPE & COVERAGE

### 2.1 Features to Test

#### A. KYC Pipeline (3FA)
- [ ] FA1: VLM document extraction (PAN, Aadhaar)
- [ ] FA1: Cross-validation (name match, DOB match)
- [ ] FA2: Verhoeff checksum validation (valid/invalid Aadhaar)
- [ ] FA3: Twilio OTP verification (send, verify, timeout, max attempts)
- [ ] Document upload validation (format, size, quality)
- [ ] Data masking (PAN masked in responses)

#### B. Credit Assessment
- [ ] CIBIL score calculation (SHA-256 hash determinism)
- [ ] LightGBM model prediction (accuracy, consistency)
- [ ] DTI calculation (formula correctness)
- [ ] EMI calculation (reducing balance formula)
- [ ] Credit tier classification (all 6 tiers)
- [ ] SHAP explanations (top features, language translation)

#### C. Negotiation Engine
- [ ] Business rules enforcement (floor rate, ceiling rate)
- [ ] Round limits per tier (0-3 negotiation rounds)
- [ ] Concession calculations (0.25% per round)
- [ ] Random Forest predictions (ML consistency)
- [ ] Rate validation (never below floor, never above ceiling)
- [ ] Human escalation (when floor reached)

#### D. Blockchain
- [ ] SHA-256 hashing (sanction letter)
- [ ] RSA-2048 signing (digital signature)
- [ ] Merkle tree construction (4-leaf tree)
- [ ] Proof-of-work mining (difficulty 2, "00" prefix)
- [ ] Blockchain persistence (JSON file survives restarts)
- [ ] Tamper detection (hash validation)

#### E. Data & Security
- [ ] Input validation (name, income, loan amount)
- [ ] PAN masking (ABCDE****F format)
- [ ] Aadhaar masking (first 4 and last 4 digits)
- [ ] Session management (in-memory + JSON persistence)
- [ ] API authentication (if applicable)
- [ ] Database injection prevention (parameterized queries)

---

## 3. TEST CASES - CREDIT SCORE TIERS

### 3.1 CIBIL Tier Classification & Expected Behavior

```
┌─────────────────────────────────────────────────────────────────┐
│ CIBIL TIER TEST MATRIX                                          │
├──────┬──────────┬──────────┬──────────┬────────┬────────────────┤
│ Tier │ Score    │ Category │ Approval │ Rounds │ Rate Band      │
├──────┼──────────┼──────────┼──────────┼────────┼────────────────┤
│ 1    │ NH/NA    │ New      │ Cond'l   │ 1      │ 14.0% - 16.0%  │
│ 2    │ 300-549  │ Poor     │ REJECT   │ 0      │ N/A            │
│ 3    │ 550-649  │ Below Avg│ Cond'l   │ 1      │ 16.0% - 20.0%  │
│ 4    │ 650-749  │ Good     │ APPROVE  │ 1      │ 13.0% - 15.0%  │
│ 5    │ 750-799  │ V.Good   │ APPROVE  │ 2      │ 11.5% - 12.5%  │
│ 6    │ 800-900  │ Excellent│ APPROVE  │ 3      │ 10.5% - 11.5%  │
└──────┴──────────┴──────────┴──────────┴────────┴────────────────┘
```

### 3.2 Test Cases per Tier

#### TEST SET 1: Tier 1 - New to Credit (NA)

**Test Case 1.1: NA Tier - Conditional Approval**
- **Input:** PAN hash generates CIBIL -1 or missing credit history
- **Expected Output:** 
  - Decision: CONDITIONAL_APPROVAL
  - Rate band: 14.0% - 16.0%
  - Negotiation rounds: 1
  - Message: "Alternative scoring available"
- **Validation:** Assert decision == CONDITIONAL_APPROVAL, rate >= 14.0 AND rate <= 16.0

**Test Case 1.2: NA Tier - Rate Negotiation**
- **Input:** NA tier applicant initiates negotiation
- **Expected Output:**
  - Initial rate: 14.5%
  - After 1 concession: 14.25%
  - Cannot exceed round limit: 1 round allowed
- **Validation:** Assert rounds_used == 1, final_rate >= 14.0

---

#### TEST SET 2: Tier 2 - Poor (300-549)

**Test Case 2.1: Poor Tier - Hard Rejection**
- **Input:** CIBIL score in range [300, 549]
- **Expected Output:**
  - Decision: REJECTED
  - Negotiation rounds: 0
  - Improvement tips provided
- **Validation:** Assert decision == REJECTED, negotiation_rounds == 0, improvement_tips_present == True

**Test Case 2.2: Poor Tier - No Negotiation Allowed**
- **Input:** Poor tier applicant attempts to negotiate
- **Expected Output:**
  - System response: "Cannot negotiate below tier 3"
  - No rate adjustment offered
- **Validation:** Assert negotiation_blocked == True

**Test Case 2.3: Poor Tier - Boundary (CIBIL = 549)**
- **Input:** CIBIL = 549 (boundary value)
- **Expected Output:** Decision = REJECTED (not approved)
- **Validation:** Assert decision == REJECTED

**Test Case 2.4: Poor Tier - Boundary (CIBIL = 550)**
- **Input:** CIBIL = 550 (just above boundary)
- **Expected Output:** Decision = CONDITIONAL_APPROVAL (tier 3)
- **Validation:** Assert decision == CONDITIONAL_APPROVAL

---

#### TEST SET 3: Tier 3 - Below Average (550-649)

**Test Case 3.1: Below Avg Tier - Conditional Approval**
- **Input:** CIBIL in range [550, 649]
- **Expected Output:**
  - Decision: CONDITIONAL_APPROVAL
  - Rate band: 16.0% - 20.0%
  - Negotiation rounds: 1
  - Requires co-applicant
- **Validation:** Assert decision == CONDITIONAL_APPROVAL, rate >= 16.0, requires_coapplicant == True

**Test Case 3.2: Below Avg Tier - Rate Negotiation (1 Round)**
- **Input:** CIBIL = 600, initial rate = 18%, apply for rate reduction
- **Expected Output:**
  - After concession: 17.75%
  - Cannot apply for 2nd concession
- **Validation:** Assert negotiation_rounds == 1, final_rate == 17.75

**Test Case 3.3: Below Avg Tier - Floor Rate Protection**
- **Input:** Multiple negotiation requests, rate = 10.6%
- **Expected Output:**
  - Cannot go below 10.5%
  - System response: "Rate floor reached, cannot offer further concessions"
- **Validation:** Assert final_rate >= 10.5

---

#### TEST SET 4: Tier 4 - Good (650-749)

**Test Case 4.1: Good Tier - Approval with Negotiation**
- **Input:** CIBIL = 700
- **Expected Output:**
  - Decision: APPROVED
  - Initial rate: 14.0%
  - Negotiation rounds: 1
- **Validation:** Assert decision == APPROVED, negotiation_rounds == 1

**Test Case 4.2: Good Tier - Rate Negotiation (1 Round)**
- **Input:** Initial rate = 14%, request concession
- **Expected Output:**
  - After concession: 13.75%
  - Rate remains within band [13.0%, 15.0%]
- **Validation:** Assert final_rate == 13.75, final_rate >= 13.0 AND final_rate <= 15.0

**Test Case 4.3: Good Tier - Single Round Exhaustion**
- **Input:** Complete 1 negotiation round, attempt 2nd round
- **Expected Output:**
  - Error: "Maximum negotiation rounds exhausted"
- **Validation:** Assert negotiation_blocked == True

---

#### TEST SET 5: Tier 5 - Very Good (750-799)

**Test Case 5.1: V.Good Tier - Approval with 2 Rounds**
- **Input:** CIBIL = 775
- **Expected Output:**
  - Decision: APPROVED
  - Initial rate: 12.0%
  - Negotiation rounds: 2
- **Validation:** Assert decision == APPROVED, max_negotiation_rounds == 2

**Test Case 5.2: V.Good Tier - Two Concessions**
- **Input:** Initial rate = 12.0%, request 2 concessions
- **Expected Output:**
  - Round 1: 11.75%
  - Round 2: 11.50%
  - Both within [11.5%, 12.5%]
- **Validation:** Assert final_rate == 11.50

**Test Case 5.3: V.Good Tier - Boundary (CIBIL = 749)**
- **Input:** CIBIL = 749
- **Expected Output:** Negotiation rounds = 1 (tier 4)
- **Validation:** Assert max_negotiation_rounds == 1

**Test Case 5.4: V.Good Tier - Boundary (CIBIL = 750)**
- **Input:** CIBIL = 750
- **Expected Output:** Negotiation rounds = 2 (tier 5)
- **Validation:** Assert max_negotiation_rounds == 2

---

#### TEST SET 6: Tier 6 - Excellent (800-900)

**Test Case 6.1: Excellent Tier - Approval with 3 Rounds**
- **Input:** CIBIL = 850
- **Expected Output:**
  - Decision: APPROVED
  - Initial rate: 10.5%
  - Negotiation rounds: 3 (maximum)
- **Validation:** Assert decision == APPROVED, max_negotiation_rounds == 3

**Test Case 6.2: Excellent Tier - Three Concessions**
- **Input:** Initial rate = 10.5%, request 3 concessions
- **Expected Output:**
  - Round 1: 10.25% → blocked (floor is 10.5%)
  - System: "Cannot offer further concessions (floor rate reached)"
- **Validation:** Assert final_rate == 10.5, no_concession_possible == True

**Test Case 6.3: Excellent Tier - Boundary (CIBIL = 800)**
- **Input:** CIBIL = 800
- **Expected Output:** Negotiation rounds = 3 (tier 6)
- **Validation:** Assert max_negotiation_rounds == 3

**Test Case 6.4: Excellent Tier - Boundary (CIBIL = 900)**
- **Input:** CIBIL = 900
- **Expected Output:** Negotiation rounds = 3, rate = 10.5% (floor)
- **Validation:** Assert max_negotiation_rounds == 3, final_rate == 10.5

---

## 4. DATA VALIDATION TEST CASES

### 4.1 Input Validation

#### Test Case DV.1: Name Validation
- **Valid Input:** "Agniv Dutta", "John Doe"
- **Invalid Inputs:** 
  - "123456" (numbers)
  - "Agniv@#$" (special characters)
  - "" (empty)
  - "A" (too short)
- **Expected:** Accept valid, reject invalid with error message

#### Test Case DV.2: Monthly Income Validation
- **Valid Range:** ₹10,000 - ₹20,00,000
- **Invalid Inputs:**
  - "₹10000" (currency symbol)
  - "10,000" (comma formatting)
  - "10000abc" (alphanumeric)
  - "5000" (below minimum)
  - "25000000" (above maximum)
- **Expected:** Accept numeric values in range, reject others

#### Test Case DV.3: Loan Amount Validation
- **Rules:** 
  - Minimum: ₹50,000
  - Maximum: 15x monthly income
- **Test Cases:**
  - Income: 50,000, Loan: 600,000 → Accept
  - Income: 50,000, Loan: 1,000,000 → Reject (exceeds 15x)
  - Income: 100,000, Loan: 25,000 → Reject (below minimum)

#### Test Case DV.4: CIBIL Score Calculation (Determinism)
- **Input:** Same PAN multiple times
- **Expected:** Always returns same CIBIL score (within session and across restarts)
- **Formula Validation:** score = 300 + (SHA256(PAN) % 601)

---

## 5. SECURITY TEST CASES

### 5.1 Data Masking

**Test Case SEC.1: PAN Masking**
- **Input:** "ABCDE1234F"
- **API Response:** Should contain "ABCDE****F", not full PAN
- **Validation:** PAN not visible in logs, API responses, UI

**Test Case SEC.2: Aadhaar Masking**
- **Input:** "123456789012"
- **Expected Display:** "1234****9012"
- **Validation:** Middle 8 digits never exposed

### 5.2 Verhoeff Validation

**Test Case SEC.3: Valid Aadhaar (Verhoeff Pass)**
- **Input:** Known valid Aadhaar (e.g., from test dataset)
- **Expected:** verhoeff_check() returns True

**Test Case SEC.4: Invalid Aadhaar (Verhoeff Fail)**
- **Input:** Random 12 digits (e.g., "111111111111")
- **Expected:** verhoeff_check() returns False, system blocks validation

**Test Case SEC.5: Single Digit Error Detection**
- **Input:** Valid Aadhaar with last digit changed
- **Expected:** Verhoeff detects error, validation fails

**Test Case SEC.6: Transposition Error Detection**
- **Input:** Valid Aadhaar with 2 adjacent digits swapped
- **Expected:** Verhoeff detects transposition, validation fails

---

## 6. PERFORMANCE TEST CASES

### 6.1 Response Time Benchmarks

| Operation | Target | Threshold |
|-----------|--------|-----------|
| CIBIL calculation | <100ms | <200ms |
| LightGBM prediction | <500ms | <1000ms |
| SHAP explanation | <1000ms | <2000ms |
| Verhoeff validation | <1ms | <10ms |
| Merkle tree construction | <500ms | <1000ms |
| End-to-end (KYC→Sanction) | <5 min | <10 min |

### 6.2 Concurrent User Testing

**Test Case PERF.1: Parallel Sessions**
- **Input:** 10 concurrent users in different pipeline stages
- **Expected:** All complete successfully without race conditions
- **Validation:** Session isolation, no data leakage between users

---

## 7. REGRESSION TEST SUITE

### 7.1 Critical Path Tests (Run Before Every Deployment)

```
✓ Test Tier 1 (NA) - Conditional Approval
✓ Test Tier 2 (Poor) - Hard Rejection
✓ Test Tier 3 (Below Avg) - Conditional with co-applicant
✓ Test Tier 4 (Good) - Approval, 1 negotiation round
✓ Test Tier 5 (V.Good) - Approval, 2 negotiation rounds
✓ Test Tier 6 (Excellent) - Approval, 3 negotiation rounds, floor rate
✓ Test Verhoeff validation (valid and invalid)
✓ Test CIBIL determinism (same PAN, same score)
✓ Test rate floor enforcement (10.5% minimum)
✓ Test Blockchain sanction letter generation
```

---

## 8. TEST EXECUTION SCHEDULE

### Phase 1: Unit Tests (Week 1)
- Test all calculation functions (CIBIL, EMI, DTI, Verhoeff)
- Test data validation
- Test error handling

### Phase 2: Integration Tests (Week 2)
- Test agent communication (Orchestrator → Credit → Negotiation)
- Test KYC pipeline (FA1, FA2, FA3)
- Test blockchain integration

### Phase 3: E2E Tests (Week 3)
- Test complete loan flows for all 6 tiers
- Test negotiation paths
- Test edge cases

### Phase 4: UAT (Week 4)
- Team member testing with real data (credit scores 592, <100)
- Test on different devices/browsers
- Load testing (if applicable)

---

## 9. BUG SEVERITY & PRIORITY

| Severity | Impact | Priority | Example |
|----------|--------|----------|---------|
| **Critical** | Data loss, security breach, no approval/rejection | P0 | Wrong CIBIL tier classification |
| **High** | Wrong rate, negotiation doesn't work | P1 | Rate below floor (10.5%) |
| **Medium** | UI issue, wrong message tone | P2 | Emoji in professional message |
| **Low** | Cosmetic, non-user-facing | P3 | Console warning |

---

## 10. TESTING BEST PRACTICES

### 10.1 Test Data Management
- Use test accounts with known credit profiles
- Maintain test dataset for all 6 CIBIL tiers
- Document test PAN and Aadhaar numbers (masked)
- Reset database between test phases

### 10.2 Test Automation
- Automate all unit and integration tests (pytest)
- Automate critical path regression tests
- Manual testing for UI/UX and new features
- Continuous integration (run tests on every commit)

### 10.3 Defect Tracking
- Log all defects with: title, reproduction steps, expected vs. actual, severity
- Track defect lifecycle: New → Assigned → In Progress → Resolved → Verified → Closed
- Generate test coverage reports

### 10.4 Sign-Off Criteria
- ✓ 100% of critical path tests pass
- ✓ No P0 or P1 defects open
- ✓ Test coverage ≥85%
- ✓ All 6 CIBIL tiers validated
- ✓ All negotiation paths tested
- ✓ Performance targets met
- ✓ Security tests pass

---

## 11. TEST METRICS & REPORTING

### Metrics to Track
- **Test Coverage:** Code coverage %, requirements coverage %
- **Defect Density:** Defects per 1000 lines of code
- **Defect Escape Rate:** Defects found in production / defects found in testing
- **Test Execution Rate:** % of planned tests executed
- **Pass Rate:** % of tests passed / total tests executed

### Weekly Status Report Template
```
Week of: [DATE]

Tests Planned:     [COUNT]
Tests Executed:    [COUNT] ([%])
Tests Passed:      [COUNT] ([%])
Tests Failed:      [COUNT] ([%])

Critical Defects:  [COUNT]
High Defects:      [COUNT]
Medium Defects:    [COUNT]

Risk Assessment:   [GREEN/YELLOW/RED]
Blockers:          [LIST]

Next Week Focus:   [AREAS TO TEST]
```

---

## SIGN-OFF

**Prepared by:** QA Lead
**Date:** [SUBMISSION DATE]
**Reviewed by:** Tech Lead, Project Manager
**Approved by:** Project Lead

This testing strategy ensures LoanEase meets production quality standards 
before conference submission and deployment to end users.

