import sys
from pathlib import Path
import asyncio

# Add negotiation_backend to path
sys.path.append(str(Path(__file__).parent.parent))

from app.service import classify_applicant_tone, analyze_counter_request, calculate_concession

async def test_tone_detection():
    print("Testing Tone Detection...")
    messages = [
        ("I'll just go to HDFC", "AGGRESSIVE"),
        ("This rate is a joke", "AGGRESSIVE"),
        ("Can you do a bit better?", "MODERATE"),
        ("Okay, but just checking...", "PASSIVE"),
        ("What does p.a. mean?", "CONFUSED")
    ]
    
    for msg, expected in messages:
        # We'll likely hit the rule-based fallback in this test environment
        res = await classify_applicant_tone(msg)
        print(f"Message: '{msg}' -> Detected: {res['tone']} (Expected: {expected})")

def test_concession_logic():
    print("\nTesting Concession Logic with Tone...")
    # risk_score, current_rate, floor_rate, round_number, max_rounds, aggressiveness, requested_rate, tone
    
    # Aggressive tone in round 1 should hold firmer
    res1 = calculate_concession(80, 11.5, 10.5, 1, 3, 0.9, 10.0, "AGGRESSIVE")
    print(f"Aggressive R1: Concession={res1['concession']}, New Rate={res1['new_rate']}")
    
    # Moderate tone in round 1
    res2 = calculate_concession(80, 11.5, 10.5, 1, 3, 0.5, 11.0, "MODERATE")
    print(f"Moderate R1: Concession={res2['concession']}, New Rate={res2['new_rate']}")
    
    # Passive tone should get less
    res3 = calculate_concession(80, 11.5, 10.5, 1, 3, 0.3, 11.25, "PASSIVE")
    print(f"Passive R1: Concession={res3['concession']}, New Rate={res3['new_rate']}")

if __name__ == "__main__":
    asyncio.run(test_tone_detection())
    test_concession_logic()
