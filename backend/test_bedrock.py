#!/usr/bin/env python3
"""Test Bedrock VLM access and permissions."""
import boto3
import os
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv("backend/.env")

def test_bedrock_access():
    """Test if we can connect to Bedrock and invoke models."""
    print("\n🔍 Testing Bedrock VLM Access...\n")
    
    try:
        # Load config
        region = os.getenv("AWS_REGION", "us-east-1")
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        
        print(f"Region: {region}")
        print(f"Access Key: {access_key[:10]}..." if access_key else "Access Key: (from AWS CLI/instance role)")
        
        # Create Bedrock client
        if access_key and secret_key:
            client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
        else:
            session = boto3.Session(region_name=region)
            client = session.client("bedrock-runtime")
        
        print("\n✅ Bedrock client created")
        
        # Verify who we are
        sts = boto3.client("sts", region_name=region)
        identity = sts.get_caller_identity()
        print(f"✅ Authenticated as: {identity['Arn']}")
        print(f"   Account: {identity['Account']}")
        
        # Test inference (simple prompt without image)
        print("\n🧪 Testing model inference...")
        model_id = "us.meta.llama3-2-11b-instruct-v1:0"
        
        response = client.converse(
            modelId=model_id,
            messages=[{
                "role": "user",
                "content": [{"text": "Say 'test passed' and nothing else."}]
            }],
            inferenceConfig={
                "maxTokens": 100,
                "temperature": 0.1
            }
        )
        
        result = response["output"]["message"]["content"][0]["text"]
        print(f"✅ Inference successful!")
        print(f"   Response: {result.strip()}")
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nYour Bedrock access is working! The IAM permissions are correct.")
        print("If VLM extraction is still failing, check:")
        print("  1. AWS credentials are correctly set in backend/.env")
        print("  2. VLM_PROVIDER=bedrock in .env")
        print("  3. Restart the backend server after updating .env")
        
        return True
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        
        print(f"\n❌ Error: {error_type}")
        print(f"   Message: {error_msg}\n")
        
        if "AccessDenied" in error_type or "not authorized" in error_msg.lower():
            print("⚠️  IAM PERMISSION ERROR")
            print("   The loanease-bedrock user is missing Bedrock permissions.")
            print("\n   Add this inline policy to the user in AWS IAM Console:")
            print("""
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["bedrock:Converse", "bedrock:ConverseStream"],
         "Resource": "*"
       }
     ]
   }
            """)
        
        elif "InvalidParameterException" in error_type:
            print("⚠️  MODEL ID OR REGION ERROR")
            print("   Check that VLM_PRIMARY in .env has the correct model ID")
            print("   and AWS_REGION is correct.")
        
        else:
            print("⚠️  UNEXPECTED ERROR")
            print("   Check AWS credentials and network connectivity")
        
        return False

if __name__ == "__main__":
    success = test_bedrock_access()
    sys.exit(0 if success else 1)
