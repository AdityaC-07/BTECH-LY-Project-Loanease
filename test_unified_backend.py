#!/usr/bin/env python3
"""
Test unified backend functionality
"""

import requests
import json

def test_backend():
    print("🧪 Testing Unified Backend Functionality")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test 1: Root endpoint
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Root endpoint: {data['service']} v{data['version']}")
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Root endpoint error: {e}")
    
    # Test 2: Health check
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check: {data['status']}")
            agents = data['agents']
            for agent, status in agents.items():
                print(f"   - {agent}: {status}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    # Test 3: KYC agent health
    try:
        response = requests.get(f"{base_url}/kyc/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ KYC Agent: {data['status']}")
        else:
            print(f"❌ KYC Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ KYC Agent error: {e}")
    
    # Test 4: Credit agent health
    try:
        response = requests.get(f"{base_url}/credit/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Credit Agent: {data['status']}")
        else:
            print(f"❌ Credit Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Credit Agent error: {e}")
    
    # Test 5: Negotiation agent health
    try:
        response = requests.get(f"{base_url}/negotiate/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Negotiation Agent: {data['status']}")
        else:
            print(f"❌ Negotiation Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Negotiation Agent error: {e}")
    
    # Test 6: Blockchain agent health
    try:
        response = requests.get(f"{base_url}/blockchain/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Blockchain Agent: {data['status']}")
        else:
            print(f"❌ Blockchain Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Blockchain Agent error: {e}")
    
    # Test 7: Pipeline agent health
    try:
        response = requests.get(f"{base_url}/pipeline/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Pipeline Agent: {data['status']}")
        else:
            print(f"❌ Pipeline Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Pipeline Agent error: {e}")
    
    # Test 8: AI/Translation agent health
    try:
        response = requests.get(f"{base_url}/ai/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ AI/Translation Agent: Connected={data.get('connected', False)}")
        else:
            print(f"❌ AI/Translation Agent failed: {response.status_code}")
    except Exception as e:
        print(f"❌ AI/Translation Agent error: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Backend Functionality Test Complete!")

if __name__ == "__main__":
    test_backend()
