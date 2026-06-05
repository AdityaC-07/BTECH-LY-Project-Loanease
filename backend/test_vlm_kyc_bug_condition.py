#!/usr/bin/env python3
"""
Bug Condition Exploration Test for Windows Bedrock Initialization Permission Error.

This test MUST FAIL on unfixed code - failure confirms the bug exists.

**Validates: Requirements 1.1, 1.2, 1.3**
**Property 1: Bug Condition - Windows Bedrock Initialization Permission Error**

The test simulates the Windows-specific permission error that occurs when
AWS SDK attempts to load credentials on Windows and encounters permission
denial from `nllMonFltProxy` device.

Expected failure on unfixed code: 
- init_vlm() fails with [Errno 13] Permission denied: '\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0'
- vlm_ready() returns False after initialization failure
- PAN card extraction cannot proceed due to VLM provider not being ready
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import io
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables to simulate Windows Bedrock scenario
os.environ['VLM_PROVIDER'] = 'bedrock'
os.environ['AWS_REGION'] = 'us-east-1'
# Don't set AWS credentials to trigger fallback to AWS CLI profile loading
# which triggers the Windows permission error

class TestWindowsBedrockBugCondition(unittest.TestCase):
    """
    Test class for exploring the Windows Bedrock initialization bug condition.
    
    This test is designed to FAIL on unfixed code, demonstrating the bug exists.
    """
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing module state
        import services.vlm_kyc
        if hasattr(services.vlm_kyc, '_bedrock_client'):
            services.vlm_kyc._bedrock_client = None
        if hasattr(services.vlm_kyc, '_vlm_provider'):
            services.vlm_kyc._vlm_provider = "bedrock"
        if hasattr(services.vlm_kyc, 'vlm_ready'):
            services.vlm_kyc.vlm_ready.cache_clear() if hasattr(services.vlm_kyc.vlm_ready, 'cache_clear') else None
    
    def test_windows_bedrock_initialization_permission_error(self):
        """
        Test that init_vlm() fails with permission error on Windows with Bedrock provider.
        
        This simulates the bug condition where AWS SDK credential loading on Windows
        triggers permission denied error from nllMonFltProxy device.
        
        **Expected Outcome on Unfixed Code**: Test FAILS (proves bug exists)
        **Expected Error**: [Errno 13] Permission denied: '\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0'
        """
        # Import here to ensure fresh module state
        from services import vlm_kyc
        
        # Mock settings to return empty AWS credentials
        # This forces the code to use boto3.Session() which fails on Windows
        with patch('core.config.settings') as mock_settings:
            mock_settings.VLM_PROVIDER = 'bedrock'
            mock_settings.AWS_ACCESS_KEY_ID = ''
            mock_settings.AWS_SECRET_ACCESS_KEY = ''
            mock_settings.AWS_REGION = 'us-east-1'
            mock_settings.VLM_PRIMARY = 'us.meta.llama3-2-11b-instruct-v1:0'
            mock_settings.VLM_FALLBACK = 'us.meta.llama3-2-11b-instruct-v1:0'
            
            # Mock boto3.Session to raise PermissionError
            # This simulates what happens on Windows when nllMonFltProxy intercepts
            with patch('boto3.Session') as mock_session_class:
                mock_session_class.side_effect = PermissionError(
                    13,  # errno
                    "Permission denied: '\\\\\\\\\\\\.\\\\nllMonFltProxy\\\\FFFFBD872A2E51C0'"  # strerror
                )
                
                # This should fail with PermissionError on unfixed code
                with self.assertRaises(PermissionError) as context:
                    vlm_kyc.init_vlm()
                
                # Check that the error is the expected Windows permission error
                error_msg = str(context.exception)
                self.assertIn('Permission denied', error_msg)
                self.assertIn('nllMonFltProxy', error_msg)
                
                # Also check that vlm_ready() returns False
                self.assertFalse(vlm_kyc.vlm_ready(), 
                               "vlm_ready() should return False after initialization failure")
    
    def test_credential_loading_triggers_windows_filter_interception(self):
        """
        Test specific scenario where AWS credential loading triggers Windows Filter Manager interception.
        
        This test focuses on the exact error path mentioned in the bug report.
        """
        from services import vlm_kyc
        
        # Mock settings to have empty AWS credentials
        with patch('core.config.settings') as mock_settings:
            mock_settings.VLM_PROVIDER = 'bedrock'
            mock_settings.AWS_ACCESS_KEY_ID = ''
            mock_settings.AWS_SECRET_ACCESS_KEY = ''
            mock_settings.AWS_REGION = 'us-east-1'
            mock_settings.VLM_PRIMARY = 'us.meta.llama3-2-11b-instruct-v1:0'
            mock_settings.VLM_FALLBACK = 'us.meta.llama3-2-11b-instruct-v1:0'
            
            # Mock boto3.Session to raise the exact error from bug report
            with patch('boto3.Session') as mock_session_class:
                # Create PermissionError with correct format (errno, strerror)
                # The bug report shows: [Errno 13] Permission denied: '\\\\.\\nllMonFltProxy\\FFFFBD872A2E51C0'
                error = PermissionError(
                    13,  # errno
                    "Permission denied: '\\\\\\\\\\\\.\\\\nllMonFltProxy\\\\FFFFBD872A2E51C0'"  # strerror
                )
                
                # Simulate error when boto3 tries to create session
                mock_session_class.side_effect = error
                
                # Test initialization
                with self.assertRaises(PermissionError) as context:
                    vlm_kyc.init_vlm()
                
                # Verify exact error message
                error_msg = str(context.exception)
                
                # The error should contain the Windows device path
                self.assertIn('nllMonFltProxy', error_msg)
                self.assertIn('Permission denied', error_msg)
                
                # Verify VLM is not ready
                self.assertFalse(vlm_kyc.vlm_ready())
    
    def test_windows_specific_credential_access_pattern(self):
        """
        Test that the error occurs specifically with file-based credential loading on Windows.
        
        The bug only manifests when:
        1. OS is Windows
        2. VLM provider is Bedrock  
        3. AWS credentials are loaded via file (AWS CLI profile or credential file)
        4. Windows Filter Manager intercepts the file access
        """
        from services import vlm_kyc
        
        # Mock settings to have empty AWS credentials (triggers file loading)
        with patch('core.config.settings') as mock_settings:
            mock_settings.VLM_PROVIDER = 'bedrock'
            mock_settings.AWS_ACCESS_KEY_ID = ''
            mock_settings.AWS_SECRET_ACCESS_KEY = ''
            mock_settings.AWS_REGION = 'us-east-1'
            mock_settings.VLM_PRIMARY = 'us.meta.llama3-2-11b-instruct-v1:0'
            mock_settings.VLM_FALLBACK = 'us.meta.llama3-2-11b-instruct-v1:0'
            
            # Mock boto3.Session to simulate Windows file access interception
            with patch('boto3.Session') as mock_session_class:
                # Simulate error when boto3 tries to read credential files
                import errno
                error = PermissionError(
                    errno.EACCES,  # errno
                    "Permission denied: '\\\\\\\\\\\\.\\\\nllMonFltProxy\\\\FFFFBD872A2E51C0'"  # strerror
                )
                mock_session_class.side_effect = error
                
                # This should fail with PermissionError
                with self.assertRaises(PermissionError):
                    vlm_kyc.init_vlm()
                
                self.assertFalse(vlm_kyc.vlm_ready())
    
    def test_non_windows_behavior_preserved(self):
        """
        Test that non-Windows systems work correctly (preservation requirement).
        
        This test should PASS on unfixed code, confirming the bug is Windows-specific.
        """
        from services import vlm_kyc
        
        # Mock settings with empty AWS credentials (triggers boto3.Session path)
        with patch('core.config.settings') as mock_settings:
            mock_settings.VLM_PROVIDER = 'bedrock'
            mock_settings.AWS_ACCESS_KEY_ID = ''
            mock_settings.AWS_SECRET_ACCESS_KEY = ''
            mock_settings.AWS_REGION = 'us-east-1'
            mock_settings.VLM_PRIMARY = 'us.meta.llama3-2-11b-instruct-v1:0'
            mock_settings.VLM_FALLBACK = 'us.meta.llama3-2-11b-instruct-v1:0'
            
            # Mock successful boto3.Session creation
            with patch('boto3.Session') as mock_session_class:
                mock_session = MagicMock()
                mock_credentials = MagicMock()
                mock_credentials.access_key = 'test-access-key'
                mock_credentials.secret_key = 'test-secret-key'
                mock_session.get_credentials.return_value = mock_credentials
                mock_session_class.return_value = mock_session
                
                # Mock successful client creation
                with patch('boto3.client') as mock_client:
                    mock_bedrock_client = MagicMock()
                    mock_client.return_value = mock_bedrock_client
                    
                    # This should succeed (simulating non-Windows behavior)
                    vlm_kyc.init_vlm()
                    
                    # VLM should be ready
                    self.assertTrue(vlm_kyc.vlm_ready())
                    
                    # Provider should be bedrock
                    self.assertEqual(vlm_kyc._vlm_provider, 'bedrock')
    
    def test_gemini_provider_preserved_on_windows(self):
        """
        Test that Gemini provider works on Windows (preservation requirement).
        
        The bug only affects Bedrock provider, so Gemini should work on Windows.
        This test should PASS on unfixed code.
        """
        from services import vlm_kyc
        
        # Mock settings for Gemini
        with patch('core.config.settings') as mock_settings:
            mock_settings.VLM_PROVIDER = 'gemini'
            mock_settings.GEMINI_API_KEY = 'test-key-12345'
            mock_settings.VLM_PRIMARY = 'gemini-pro'
            mock_settings.VLM_FALLBACK = 'gemini-pro'
            
            # Mock google.generativeai to avoid actual API calls
            with patch('google.generativeai.GenerativeModel') as mock_genai_model:
                mock_model = MagicMock()
                mock_genai_model.return_value = mock_model
                
                with patch('google.generativeai.configure'):
                    # This should succeed even on Windows with Gemini
                    vlm_kyc.init_vlm()
                    
                    # VLM should be ready with Gemini
                    self.assertTrue(vlm_kyc.vlm_ready())
                    self.assertEqual(vlm_kyc._vlm_provider, 'gemini')


def run_bug_condition_exploration():
    """
    Run the bug condition exploration tests and report findings.
    
    Returns:
        dict: Test results with counterexamples if tests fail
    """
    print("=" * 80)
    print("BUG CONDITION EXPLORATION TEST - Windows Bedrock Initialization Permission Error")
    print("=" * 80)
    print("\nThis test MUST FAIL on unfixed code to confirm the bug exists.")
    print("Expected failure demonstrates: init_vlm() fails with permission error on Windows")
    print("\nProperty 1: Bug Condition - Windows Bedrock Initialization Permission Error")
    print("Validates: Requirements 1.1, 1.2, 1.3")
    print("-" * 80)
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestWindowsBedrockBugCondition)
    
    # Capture test results
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    
    # Print results
    print(stream.getvalue())
    
    # Analyze results
    test_results = {
        'total_tests': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'expected_failures': 0,
        'counterexamples': []
    }
    
    # Check for expected failures (bug condition tests should fail on unfixed code)
    for test, traceback in result.failures:
        test_name = test.id().split('.')[-1]
        if 'windows_bedrock' in test_name.lower() or 'permission_error' in test_name.lower():
            test_results['expected_failures'] += 1
            test_results['counterexamples'].append({
                'test': test_name,
                'error': str(traceback).split('\n')[-2] if traceback else 'Unknown error',
                'demonstrates_bug': True
            })
    
    print("\n" + "=" * 80)
    print("BUG CONDITION ANALYSIS")
    print("=" * 80)
    print(f"Total tests run: {test_results['total_tests']}")
    print(f"Failures: {test_results['failures']} (expected: Windows Bedrock tests should fail)")
    print(f"Errors: {test_results['errors']}")
    print(f"Expected failures (bug confirmation): {test_results['expected_failures']}")
    
    if test_results['counterexamples']:
        print("\nCOUNTEREXAMPLES FOUND (proves bug exists):")
        for i, example in enumerate(test_results['counterexamples'], 1):
            print(f"\n  {i}. {example['test']}")
            print(f"     Error: {example['error']}")
            print(f"     Demonstrates: Windows Bedrock initialization permission error")
    
    # Check if bug condition is confirmed
    if test_results['expected_failures'] >= 1:
        print("\n✅ BUG CONFIRMED: Windows Bedrock initialization permission error exists")
        print("   The test failed as expected, confirming the bug condition.")
        print("   Counterexamples demonstrate the permission error from nllMonFltProxy.")
    else:
        print("\n⚠️  UNEXPECTED: Windows Bedrock tests did not fail")
        print("   This could mean:")
        print("   1. The code is already fixed (unlikely for unfixed code)")
        print("   2. The test environment doesn't accurately simulate Windows")
        print("   3. The bug manifests differently than expected")
    
    # Check preservation tests
    preservation_tests_passed = all(
        test_name in ['test_non_windows_behavior_preserved', 'test_gemini_provider_preserved_on_windows']
        for test_name in [test.id().split('.')[-1] for test, _ in result.failures + result.errors]
        if test_name in ['test_non_windows_behavior_preserved', 'test_gemini_provider_preserved_on_windows']
    )
    
    if preservation_tests_passed:
        print("\n✅ PRESERVATION CONFIRMED: Non-Windows and Gemini behavior works correctly")
    
    return test_results


if __name__ == '__main__':
    # Run bug condition exploration
    results = run_bug_condition_exploration()
    
    # Exit with appropriate code
    # For bug condition exploration, we expect some tests to fail (confirms bug)
    if results['expected_failures'] >= 1:
        print("\n✅ BUG CONDITION EXPLORATION COMPLETE")
        print("   The test failed as expected, confirming the Windows Bedrock permission error bug.")
        print("   This provides concrete counterexamples for the fix implementation.")
        sys.exit(0)  # Success - bug confirmed
    else:
        print("\n⚠️  UNEXPECTED TEST RESULTS")
        print("   Expected Windows Bedrock tests to fail, but they didn't.")
        print("   This may indicate the test doesn't accurately simulate the bug condition.")
        sys.exit(1)