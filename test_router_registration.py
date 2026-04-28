#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

def test_router_registration():
    try:
        # Test importing main app
        from main import app
        print("✅ Main app imported successfully")
        
        # Check if blockchain routes are registered
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        print(f"\n📋 Registered routes ({len(routes)}):")
        for route in sorted(routes):
            if 'blockchain' in route:
                print(f"  ✅ {route}")
            else:
                print(f"  📄 {route}")
        
        # Check for blockchain routes specifically
        blockchain_routes = [r for r in routes if 'blockchain' in r]
        print(f"\n🔗 Blockchain routes found: {len(blockchain_routes)}")
        
        if len(blockchain_routes) == 0:
            print("❌ No blockchain routes found!")
            print("\n🔍 Debugging blockchain router import...")
            
            try:
                from agents.blockchain_agent.main import router
                print("✅ Blockchain router imported")
                print(f"   Routes in router: {len(router.routes)}")
                for route in router.routes:
                    print(f"   - {route.path}")
            except Exception as e:
                print(f"❌ Error importing blockchain router: {e}")
        else:
            print("✅ Blockchain routes are registered!")
            
    except Exception as e:
        print(f"❌ Error testing router registration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_router_registration()
