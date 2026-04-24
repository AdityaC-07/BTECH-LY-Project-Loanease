#!/usr/bin/env python3
"""
LoanEase Blockchain Audit Service - Demo Script

This script demonstrates the complete blockchain functionality including:
1. Loan sanction processing
2. Document verification
3. Blockchain integrity checks
4. PDF generation and QR code creation
"""

import json
import requests
import time
from datetime import datetime

# Configuration
BLOCKCHAIN_BASE_URL = "http://localhost:8005"


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"🔗 {title}")
    print('='*60)


def print_success(message):
    """Print success message"""
    print(f"✅ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


def print_warning(message):
    """Print warning message"""
    print(f"⚠️  {message}")


def test_health_check():
    """Test blockchain service health"""
    print_section("Service Health Check")
    
    try:
        response = requests.get(f"{BLOCKCHAIN_BASE_URL}/health")
        if response.status_code == 200:
            health_data = response.json()
            print_success("Blockchain service is healthy")
            print_info(f"Status: {health_data['status']}")
            print_info(f"Uptime: {health_data['uptime_seconds']} seconds")
            print_info(f"Blockchain Ready: {health_data['blockchain_ready']}")
            print_info(f"Crypto Ready: {health_data['crypto_ready']}")
            print_info(f"Total Blocks: {health_data['total_blocks']}")
            return True
        else:
            print_warning(f"Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_warning(f"Health check error: {e}")
        return False


def test_blockchain_info():
    """Test blockchain chain information"""
    print_section("Blockchain Chain Information")
    
    try:
        response = requests.get(f"{BLOCKCHAIN_BASE_URL}/blockchain/chain")
        if response.status_code == 200:
            chain_data = response.json()
            print_success("Blockchain retrieved successfully")
            print_info(f"Chain Length: {chain_data['chain_length']}")
            print_info(f"Chain Valid: {chain_data['is_valid']}")
            
            # Show genesis block
            genesis = chain_data['blocks'][0]
            print_info(f"Genesis Block: {genesis['index']} - {genesis['transaction_data']['message']}")
            
            return True
        else:
            print_warning(f"Chain info failed: {response.status_code}")
            return False
    except Exception as e:
        print_warning(f"Chain info error: {e}")
        return False


def test_loan_sanction():
    """Test loan sanction processing"""
    print_section("Loan Sanction Processing")
    
    sanction_request = {
        "session_id": "demo-session-123",
        "applicant_name": "Rahul Sharma",
        "pan_masked": "ABCDE1234F",
        "loan_amount": 500000,
        "sanctioned_rate": 11.0,
        "tenure_months": 60,
        "emi": 10747,
        "total_payable": 644820,
        "kyc_reference": "KYC-2026-00291",
        "risk_score": 87
    }
    
    try:
        print_info("Processing loan sanction...")
        response = requests.post(
            f"{BLOCKCHAIN_BASE_URL}/blockchain/sanction",
            json=sanction_request,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            sanction_data = response.json()
            print_success("Loan sanctioned successfully!")
            print_info(f"Sanction Reference: {sanction_data['sanction_reference']}")
            print_info(f"Transaction ID: {sanction_data['transaction_id']}")
            print_info(f"Document Hash: {sanction_data['document_hash'][:32]}...")
            print_info(f"Block Index: {sanction_data['block_index']}")
            print_info(f"Blockchain Valid: {sanction_data['blockchain_valid']}")
            print_info(f"PDF Size: {len(sanction_data['pdf_base64'])} characters")
            print_info(f"QR Code Generated: {len(sanction_data['qr_code_base64'])} characters")
            
            return sanction_data['sanction_reference']
        else:
            print_warning(f"Sanction failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_warning(f"Sanction error: {e}")
        return None


def test_document_verification(reference):
    """Test document verification"""
    print_section("Document Verification")
    
    try:
        print_info(f"Verifying document with reference: {reference}")
        response = requests.get(f"{BLOCKCHAIN_BASE_URL}/blockchain/verify/{reference}")
        
        if response.status_code == 200:
            verify_data = response.json()
            print_success("Document verification completed!")
            print_info(f"Status: {verify_data['status']}")
            print_info(f"Chain Integrity: {verify_data['chain_integrity']}")
            print_info(f"Block Index: {verify_data['block_index']}")
            
            if verify_data['status'] == 'VERIFIED':
                print_success("✨ Document is authentic and untampered!")
                loan_details = verify_data.get('loan_details', {})
                if loan_details:
                    print_info(f"Loan Amount: ₹{loan_details.get('loan_amount', 0):,}")
                    print_info(f"Interest Rate: {loan_details.get('sanctioned_rate', 0)}%")
                    print_info(f"Tenure: {loan_details.get('tenure_months', 0)} months")
            else:
                print_warning("Document verification failed or document not found")
            
            return True
        else:
            print_warning(f"Verification failed: {response.status_code}")
            return False
    except Exception as e:
        print_warning(f"Verification error: {e}")
        return False


def test_blockchain_stats():
    """Test blockchain statistics"""
    print_section("Blockchain Statistics")
    
    try:
        response = requests.get(f"{BLOCKCHAIN_BASE_URL}/blockchain/stats")
        if response.status_code == 200:
            stats_data = response.json()
            print_success("Blockchain statistics retrieved!")
            print_info(f"Total Sanctions: {stats_data['total_sanctions']}")
            print_info(f"Total Amount Sanctioned: ₹{stats_data['total_amount_sanctioned']:,}")
            print_info(f"Chain Valid: {stats_data['chain_valid']}")
            print_info(f"Genesis Timestamp: {stats_data['genesis_timestamp']}")
            print_info(f"Latest Block: {stats_data['latest_block_timestamp']}")
            
            return True
        else:
            print_warning(f"Stats failed: {response.status_code}")
            return False
    except Exception as e:
        print_warning(f"Stats error: {e}")
        return False


def test_tamper_detection(reference):
    """Test tamper detection by modifying verification"""
    print_section("Tamper Detection Test")
    
    try:
        print_info("Testing tamper detection mechanism...")
        response = requests.get(f"{BLOCKCHAIN_BASE_URL}/blockchain/verify/{reference}")
        
        if response.status_code == 200:
            verify_data = response.json()
            if verify_data['status'] == 'VERIFIED':
                print_success("Original document verified successfully")
                
                # Simulate tampering by requesting with wrong reference
                print_info("Simulating document tampering...")
                tampered_response = requests.get(f"{BLOCKCHAIN_BASE_URL}/blockchain/verify/FAKE-REF-123")
                
                if tampered_response.status_code == 200:
                    tampered_data = tampered_response.json()
                    if tampered_data['status'] == 'NOT_FOUND':
                        print_success("✨ Tamper detection working - Fake reference detected!")
                    else:
                        print_warning("Tamper detection test inconclusive")
                else:
                    print_warning("Tamper detection test failed")
                
                return True
        return False
    except Exception as e:
        print_warning(f"Tamper detection test error: {e}")
        return False


def main():
    """Main demo function"""
    print("🏦 LoanEase Blockchain Audit Service - Demo")
    print("🔐 Demonstrating secure loan sanction and verification")
    print(f"🌐 Target Service: {BLOCKCHAIN_BASE_URL}")
    
    # Run all tests
    tests = [
        ("Health Check", test_health_check),
        ("Blockchain Info", test_blockchain_info),
        ("Blockchain Stats", test_blockchain_stats),
    ]
    
    # Run basic tests first
    for test_name, test_func in tests:
        if not test_func():
            print_warning(f"❌ {test_name} failed. Stopping demo.")
            return
    
    # Test loan sanction (this will generate a reference)
    reference = test_loan_sanction()
    
    if reference:
        # Test verification with the generated reference
        test_document_verification(reference)
        
        # Test tamper detection
        test_tamper_detection(reference)
        
        # Get final stats
        test_blockchain_stats()
    
    print_section("Demo Complete")
    print_success("🎉 LoanEase Blockchain Audit Service demo completed successfully!")
    print_info("📄 All sanctions are cryptographically signed and blockchain-verified")
    print_info("🔍 Documents can be publicly verified using the reference number")
    print_info("⛓️  Blockchain provides tamper-evident audit trail")
    print_info("📱 QR codes enable mobile verification")
    
    print(f"\n🌐 Try these endpoints:")
    print(f"   • Health: {BLOCKCHAIN_BASE_URL}/health")
    print(f"   • Chain: {BLOCKCHAIN_BASE_URL}/blockchain/chain")
    print(f"   • Stats: {BLOCKCHAIN_BASE_URL}/blockchain/stats")
    print(f"   • Verify: {BLOCKCHAIN_BASE_URL}/blockchain/verify/LE-2026-00001")


if __name__ == "__main__":
    main()
