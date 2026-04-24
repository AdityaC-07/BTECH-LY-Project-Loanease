#!/usr/bin/env python3
"""
Test credit agent functionality
"""

import requests
import json

def test_credit_agent():
    print("🧪 Testing Credit Agent Functionality")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test 1: Credit scoring with PAN
    try:
        response = requests.post(f"{base_url}/credit/credit-score", 
                               json={"pan_number": "ABCDE1234F"})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Credit Score Test:")
            print(f"   - CIBIL Score: {data['cibil_score']}")
            print(f"   - Final Score: {data['credit_score']}")
            print(f"   - Risk Category: {data['risk_category']}")
            print(f"   - Risk Score: {data['risk_score']}")
        else:
            print(f"❌ Credit Score Test failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Credit Score Test error: {e}")
    
    # Test 2: Full credit assessment
    try:
        response = requests.post(f"{base_url}/credit/assess",
                               json={
                                   "session_id": "TEST123",
                                   "loan_amount": 500000,
                                   "tenure_years": 5
                               })
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Credit Assessment Test:")
            print(f"   - Application ID: {data['application_id']}")
            print(f"   - Decision: {data['decision']}")
            print(f"   - Credit Score: {data['credit_score']}")
            print(f"   - Interest Rate: {data['interest_rate']}%")
            print(f"   - Max Loan: ₹{data['max_loan_amount']:,.2f}")
        else:
            print(f"❌ Credit Assessment Test failed: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Credit Assessment Test error: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Credit Agent Test Complete!")

if __name__ == "__main__":
    test_credit_agent()
