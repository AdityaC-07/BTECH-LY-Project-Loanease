#!/usr/bin/env python3

import requests
import json

def test_blockchain_endpoints():
    base_url = "http://localhost:8000"
    
    endpoints = [
        "/",
        "/health",
        "/blockchain/health",
        "/blockchain/chain",
        "/blockchain/explorer-data",
        "/blockchain/verify-chain"
    ]
    
    print("Testing Blockchain Endpoints...")
    print("=" * 50)
    
    for endpoint in endpoints:
        try:
            url = f"{base_url}{endpoint}"
            print(f"\nTesting: {url}")
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ {endpoint} - OK")
                if endpoint == "/blockchain/explorer-data":
                    data = response.json()
                    print(f"   Blocks: {len(data.get('blocks', []))}")
                    print(f"   Chain valid: {data.get('chain_valid', 'Unknown')}")
            else:
                print(f"❌ {endpoint} - Status: {response.status_code}")
                print(f"   Response: {response.text[:100]}...")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ {endpoint} - Error: {str(e)}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    test_blockchain_endpoints()
