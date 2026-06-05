import sys
sys.path.insert(0, '.')
from unittest.mock import patch, MagicMock

# Mock settings
with patch('core.config.settings') as mock_settings:
    mock_settings.VLM_PROVIDER = 'bedrock'
    mock_settings.AWS_ACCESS_KEY_ID = ''
    mock_settings.AWS_SECRET_ACCESS_KEY = ''
    mock_settings.AWS_REGION = 'us-east-1'
    mock_settings.VLM_PRIMARY = 'test'
    mock_settings.VLM_FALLBACK = 'test'
    
    # Mock boto3.Session
    with patch('boto3.Session') as mock_session_class:
        print('Testing WindowsPermissionError class:')
        class WindowsPermissionError(PermissionError):
            def __init__(self):
                super().__init__(
                    '[Errno 13] Permission denied: \\\\\\\\\\\\.\\\\\\\\nllMonFltProxy\\\\\\\\FFFFBD872A2E51C0'
                )
        
        try:
            mock_session_class.side_effect = WindowsPermissionError()
            from services import vlm_kyc
            vlm_kyc._bedrock_client = None
            vlm_kyc._vlm_provider = 'bedrock'
            vlm_kyc.init_vlm()
        except PermissionError as e:
            print(f'  Caught PermissionError: {repr(e)}')
            print(f'  Error message: {str(e)}')
            contains_permission = "Permission denied" in str(e)
            contains_nll = "nllMonFltProxy" in str(e)
            print(f'  Contains Permission denied?: {contains_permission}')
            print(f'  Contains nllMonFltProxy?: {contains_nll}')
            
        print()
        print('Testing with simpler error:')
        try:
            mock_session_class.side_effect = PermissionError(13, 'Permission denied: test path')
            from services import vlm_kyc
            vlm_kyc._bedrock_client = None
            vlm_kyc._vlm_provider = 'bedrock'
            vlm_kyc.init_vlm()
        except PermissionError as e:
            print(f'  Caught PermissionError: {repr(e)}')
            print(f'  Error message: {str(e)}')
            print(f'  errno: {e.errno if hasattr(e, "errno") else "no errno"}')
            print(f'  strerror: {e.strerror if hasattr(e, "strerror") else "no strerror"}')
            
        print()
        print('Testing actual PermissionError constructor:')
        # Test how PermissionError formats messages
        e1 = PermissionError('[Errno 13] Permission denied: test')
        print(f'  e1 = PermissionError(\"[Errno 13] Permission denied: test\")')
        print(f'  str(e1): {str(e1)}')
        
        e2 = PermissionError(13, 'Permission denied: test')
        print(f'  e2 = PermissionError(13, \"Permission denied: test\")')
        print(f'  str(e2): {str(e2)}')
        
        e3 = PermissionError(13, 'Permission denied')
        print(f'  e3 = PermissionError(13, \"Permission denied\")')
        print(f'  str(e3): {str(e3)}')