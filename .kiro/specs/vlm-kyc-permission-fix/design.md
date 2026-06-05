# VLM_KYC Permission Error Bugfix Design

## Overview

The VLM_KYC component fails with a Windows-specific permission error `[Errno 13] Permission denied: '\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0'` when initializing AWS Bedrock client. This error appears to be triggered by Windows Filter Manager or antivirus software intercepting file operations during AWS credential loading. The bug prevents KYC processing (PAN card extraction) from working on Windows systems.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when AWS SDK/boto3 attempts to access credentials on Windows and encounters permission denial from `nllMonFltProxy`
- **Property (P)**: The desired behavior when initializing VLM_KYC - AWS Bedrock client should initialize successfully without permission errors
- **Preservation**: Existing behavior on non-Windows systems, AWS credential loading methods, and Gemini VLM provider that must remain unchanged
- **init_vlm**: The function in `backend/services/vlm_kyc.py` that initializes the VLM provider (Bedrock or Gemini)
- **vlm_ready**: The function that returns whether the VLM provider is successfully initialized
- **nllMonFltProxy**: Windows Filter Manager proxy device that appears to be intercepting file operations

## Bug Details

### Bug Condition

The bug manifests when the `init_vlm()` function attempts to initialize AWS Bedrock client on Windows. The AWS SDK or boto3 library tries to access credentials through a file operation that gets intercepted by Windows Filter Manager (`nllMonFltProxy`), resulting in permission denied error. The `vlm_ready()` function returns False, causing PAN card extraction to fail.

**Formal Specification:**
```
FUNCTION isBugCondition(system_state)
  INPUT: system_state of type SystemState
  OUTPUT: boolean
  
  RETURN system_state.os_type = "windows"
         AND system_state.vlm_provider = "bedrock"
         AND system_state.aws_credential_loading = True
         AND file_access_blocked("\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0")
END FUNCTION
```

### Examples

- **Concrete Example 1**: Windows 10/11 with AWS CLI profile, running Loanease backend - `init_vlm()` fails with permission error
- **Concrete Example 2**: Windows Server with AWS credentials in environment variables - same permission error occurs
- **Concrete Example 3**: Development machine with antivirus software - file operations intercepted by security filter
- **Edge Case Example**: Linux or macOS with same AWS configuration - works correctly (no bug)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Non-Windows systems (Linux, macOS) must continue to work exactly as before
- AWS credential loading via environment variables must continue to work
- AWS credential loading via AWS CLI profiles must continue to work
- Gemini VLM provider initialization must remain completely unaffected
- PAN card extraction logic and validation must remain unchanged

**Scope:**
All systems that do NOT involve Windows OS with Bedrock VLM provider should be completely unaffected by this fix. This includes:
- Linux systems with AWS Bedrock
- macOS systems with AWS Bedrock  
- Windows systems using Gemini VLM provider
- Any system where VLM provider is not "bedrock"

## Hypothesized Root Cause

Based on the bug description and error message analysis, the most likely issues are:

1. **Windows Filter Manager Interception**: The `nllMonFltProxy` device appears to be a Windows Filter Manager proxy that intercepts file operations. Antivirus or security software may be blocking credential file access.

2. **AWS SDK File Access Pattern**: boto3/AWS SDK may be trying to access credential files in a way that triggers Windows security filters. The specific device path suggests direct device namespace access.

3. **Credential Loading Path Issue**: The error path `\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0` suggests the AWS SDK is attempting to access a filter driver device instead of regular filesystem paths.

4. **Permission Elevation Required**: Windows may require elevated permissions or different API calls to access certain file locations where credentials are stored.

## Correctness Properties

Property 1: Bug Condition - Windows Bedrock Initialization Permission Error

_For any_ system state where the bug condition holds (isBugCondition returns true - Windows OS, Bedrock provider, AWS credential loading), the fixed init_vlm function SHALL initialize AWS Bedrock client successfully without permission denied errors, allowing vlm_ready to return True.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Windows and Alternative Provider Behavior

_For any_ system state where the bug condition does NOT hold (non-Windows systems, Gemini provider, or no AWS credential loading), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for non-Windows systems and alternative VLM providers.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/services/vlm_kyc.py`

**Function**: `init_vlm()`

**Specific Changes**:
1. **Windows-Specific Credential Loading**: Add Windows-specific credential loading logic that avoids triggering filter driver interception
2. **Alternative Credential Sources**: Prioritize environment variables over file-based credential loading on Windows
3. **Error Handling Enhancement**: Add specific error handling for Windows permission errors with fallback mechanisms
4. **Credential Validation**: Add pre-validation of credential accessibility before attempting Bedrock client initialization
5. **Diagnostic Logging**: Enhance logging to capture Windows-specific credential loading issues for debugging

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate Windows environment and AWS Bedrock initialization. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Windows Bedrock Initialization Test**: Mock Windows OS and test init_vlm() with AWS credentials (will fail on unfixed code)
2. **Permission Error Simulation**: Simulate permission denied error from nllMonFltProxy device path (will fail on unfixed code)
3. **Credential Loading Path Test**: Test different AWS credential loading methods on Windows (may fail on unfixed code)
4. **Edge Case Test**: Test on Windows with Gemini provider (should pass on unfixed code)

**Expected Counterexamples**:
- init_vlm() fails with `[Errno 13] Permission denied: '\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0'`
- vlm_ready() returns False after initialization failure
- PAN card extraction fails due to VLM provider not being ready

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL system_state WHERE isBugCondition(system_state) DO
  result := init_vlm_fixed(system_state)
  ASSERT vlm_ready() = True
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL system_state WHERE NOT isBugCondition(system_state) DO
  ASSERT init_vlm_original(system_state) = init_vlm_fixed(system_state)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-Windows systems and Gemini provider, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Linux/MacOS Preservation**: Observe that init_vlm() works correctly on unfixed code for Linux/macOS, then write test to verify this continues after fix
2. **Gemini Provider Preservation**: Observe that Gemini initialization works on unfixed code, then write test to verify this continues after fix
3. **Environment Variable Preservation**: Observe that AWS credentials via env vars work on unfixed code, then write test to verify this continues after fix
4. **AWS CLI Profile Preservation**: Observe that AWS CLI profiles work on unfixed code, then write test to verify this continues after fix

### Unit Tests

- Test Windows-specific credential loading logic
- Test error handling for permission denied errors
- Test fallback mechanisms when primary credential loading fails
- Test that vlm_ready() returns correct status after initialization

### Property-Based Tests

- Generate random OS types and VLM provider configurations to verify preservation
- Generate random AWS credential scenarios to test Windows-specific handling
- Test that all non-Windows configurations continue to work across many scenarios

### Integration Tests

- Test full VLM_KYC initialization flow on simulated Windows environment
- Test PAN card extraction with fixed Windows initialization
- Test that startup self-test shows VLM_KYC as `✅ PASS` after fix
- Test cross-platform compatibility (Windows, Linux, macOS)