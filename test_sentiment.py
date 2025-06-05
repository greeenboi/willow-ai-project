#!/usr/bin/env python3
"""Test script to verify sentiment detection works correctly."""

from database import DatabaseManager
from knowledge_manager import KnowledgeManager

def test_sentiment_detection():
    """Test the move forward sentiment detection."""
    db_manager = DatabaseManager()
    km = KnowledgeManager(db_manager)
    
    # Test cases
    test_cases = [
        {
            "message": "This seems like a great fit!",
            "lead_info": {"company_name": "TestCorp", "domain": "technology", "demo_shown": True},
            "expected": True
        },
        {
            "message": "This looks like a good fit for our team",
            "lead_info": {"company_name": "TestCorp", "domain": "technology", "demo_shown": True},
            "expected": True
        },
        {
            "message": "But what about pricing?",
            "lead_info": {"company_name": "TestCorp", "domain": "technology", "demo_shown": True},
            "expected": False
        },
        {
            "message": "This is perfect!",
            "lead_info": {"company_name": "TestCorp", "domain": "technology", "demo_shown": False, "problem": "lead conversion", "budget": "10k"},
            "expected": True
        }
    ]
    
    print("Testing sentiment detection...")
    for i, test in enumerate(test_cases):
        result = km.detect_move_forward_sentiment(test["message"], test["lead_info"])
        status = "✅ PASS" if result == test["expected"] else "❌ FAIL"
        print(f"Test {i+1}: {status}")
        print(f"  Message: '{test['message']}'")
        print(f"  Expected: {test['expected']}, Got: {result}")
        print()

if __name__ == "__main__":
    test_sentiment_detection()
