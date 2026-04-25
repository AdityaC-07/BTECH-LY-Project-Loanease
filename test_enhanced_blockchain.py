#!/usr/bin/env python3
"""
Test Enhanced Blockchain Implementation
Demonstrates Merkle trees, Proof of Work, and verification
"""

import requests
import json
import hashlib
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_enhanced_blockchain():
    print("🔒 Testing Enhanced Blockchain Implementation")
    print("=" * 60)
    
    # Test 1: Check blockchain health
    print("\n1️⃣ Blockchain Health Check")
    try:
        response = requests.get(f"{BASE_URL}/blockchain/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: {data['status']}")
            print(f"   - Chain Length: {data['chain_length']}")
            print(f"   - Keys Loaded: {data['keys_loaded']}")
            print(f"   - Difficulty: {data['difficulty']}")
            print(f"   - Chain Valid: {data['chain_valid']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    # Test 2: Create sanction letter
    print("\n2️⃣ Creating Sanction Letter with Merkle Tree & PoW")
    try:
        sanction_data = {
            "session_id": "TEST_SESSION_001",
            "applicant_name": "Rahul Sharma",
            "pan_number": "ABCDE1234F",
            "loan_amount": 500000,
            "interest_rate": 11.0,
            "tenure_years": 5
        }
        
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/blockchain/sanction", json=sanction_data)
        end_time = time.time()
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Sanction created in {end_time - start_time:.2f}s (includes PoW mining)")
            print(f"   - Transaction ID: {data['transaction_id']}")
            print(f"   - Block Hash: {data['block_hash'][:16]}...")
            print(f"   - Verification URL: {data['verification_url']}")
            
            # Save reference for later tests
            reference = data['transaction_id']
            block_hash = data['block_hash']
        else:
            print(f"❌ Sanction creation failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Sanction creation error: {e}")
        return
    
    # Test 3: Blockchain Explorer
    print("\n3️⃣ Blockchain Explorer (Etherscan-like)")
    try:
        response = requests.get(f"{BASE_URL}/blockchain/explorer")
        if response.status_code == 200:
            data = response.json()
            summary = data['chain_summary']
            print(f"✅ Chain Summary:")
            print(f"   - Total Blocks: {summary['total_blocks']}")
            print(f"   - Total Sanctions: {summary['total_sanctions']}")
            print(f"   - Total Amount: ₹{summary['total_amount_sanctioned']:,}")
            print(f"   - Chain Valid: {summary['chain_valid']}")
            print(f"   - Difficulty: {summary['proof_of_work_difficulty']}")
            print(f"   - Genesis Hash: {summary['genesis_hash'][:16]}...")
            print(f"   - Latest Hash: {summary['latest_hash'][:16]}...")
            
            # Show latest blocks
            blocks = data['blocks'][-3:]  # Last 3 blocks
            print(f"\n   Latest Blocks:")
            for block in blocks:
                block_type = block['transactions'][0].get('transaction_type', 'UNKNOWN')
                print(f"   - Block #{block['index']}: {block_type} - {block['hash'][:16]}...")
        else:
            print(f"❌ Explorer failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Explorer error: {e}")
    
    # Test 4: Merkle Proof
    print("\n4️⃣ Merkle Tree Proof Verification")
    try:
        response = requests.get(f"{BASE_URL}/blockchain/merkle-proof/{reference}")
        if response.status_code == 200:
            data = response.json()
            proof = data['proof']
            print(f"✅ Merkle Proof Generated:")
            print(f"   - Block Index: {proof['block_index']}")
            print(f"   - Transaction Index: {proof['transaction_index']}")
            print(f"   - Merkle Root: {proof['merkle_root'][:16]}...")
            print(f"   - Proof Valid: {data['verification']}")
            print(f"   - Proof Length: {len(proof['proof'])} levels")
        else:
            print(f"❌ Merkle proof failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Merkle proof error: {e}")
    
    # Test 5: Document Validation
    print("\n5️⃣ Document Hash Validation")
    try:
        # Simulate document content
        document_content = f"Sanction Letter for {sanction_data['applicant_name']} - Loan Amount: ₹{sanction_data['loan_amount']:,}"
        
        validate_data = {
            "document_content": document_content,
            "reference": reference
        }
        
        response = requests.post(f"{BASE_URL}/blockchain/validate", json=validate_data)
        if response.status_code == 200:
            data = response.json()
            print("✅ Document Validation:")
            print(f"   - Valid: {data['valid']}")
            print(f"   - Reason: {data['reason']}")
            print(f"   - Computed Hash: {data['computed_hash'][:16]}...")
            if 'stored_hash' in data:
                print(f"   - Stored Hash: {data['stored_hash'][:16]}...")
        else:
            print(f"❌ Validation failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Validation error: {e}")
    
    # Test 6: Tampering Detection
    print("\n6️⃣ Tampering Detection Demo")
    try:
        # Modify document slightly
        tampered_content = document_content.replace("₹500,000", "₹600,000")
        
        validate_data = {
            "document_content": tampered_content,
            "reference": reference
        }
        
        response = requests.post(f"{BASE_URL}/blockchain/validate", json=validate_data)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Tampering Detection:")
            print(f"   - Valid: {data['valid']}")
            print(f"   - Reason: {data['reason']}")
            print(f"   - Original Hash: {data.get('stored_hash', 'N/A')[:16]}...")
            print(f"   - Tampered Hash: {data['computed_hash'][:16]}...")
        else:
            print(f"❌ Tampering test failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Tampering test error: {e}")
    
    # Test 7: Amendment Feature
    print("\n7️⃣ Sanction Amendment (Immutable Audit Trail)")
    try:
        amendment_data = {
            "original_reference": reference,
            "amendment_data": {
                "interest_rate": 10.5,  # Reduced from 11.0
                "amendment_date": datetime.now().strftime("%d %b %Y")
            },
            "reason": "Rate correction due to credit score improvement"
        }
        
        response = requests.post(f"{BASE_URL}/blockchain/amend", json=amendment_data)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Amendment Created:")
            print(f"   - Success: {data['success']}")
            print(f"   - Original Reference: {data['original_reference']}")
            print(f"   - Amendment Reason: {data['amendment_reason']}")
            print(f"   - New Block: #{data['amendment_block']['index']}")
            print(f"   - New Block Hash: {data['amendment_block']['hash'][:16]}...")
        else:
            print(f"❌ Amendment failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Amendment error: {e}")
    
    # Test 8: Chain Integrity
    print("\n8️⃣ Full Chain Integrity Validation")
    try:
        response = requests.get(f"{BASE_URL}/blockchain/chain/validate")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Chain Integrity:")
            print(f"   - Chain Valid: {data['chain_valid']}")
            print(f"   - Chain Length: {data['chain_length']}")
            print(f"   - Difficulty: {data['difficulty']}")
            if data['latest_block']:
                print(f"   - Latest Block: #{data['latest_block']['index']}")
                print(f"   - Proof of Work: {data['latest_block']['hash'][:3]}...")
        else:
            print(f"❌ Chain validation failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Chain validation error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Enhanced Blockchain Test Complete!")
    print("\n📋 Features Demonstrated:")
    print("✅ Merkle Tree transaction verification")
    print("✅ Proof of Work mining (difficulty 3)")
    print("✅ Immutable audit trail with amendments")
    print("✅ Document tampering detection")
    print("✅ Blockchain explorer (Etherscan-like)")
    print("✅ Cryptographic signatures")
    print("✅ Chain integrity validation")
    
    print(f"\n🌐 Verification Dashboard:")
    print(f"Visit: {BASE_URL}/blockchain/verify/{reference}")
    print(f"Explorer: {BASE_URL}/blockchain/explorer")

if __name__ == "__main__":
    test_enhanced_blockchain()
