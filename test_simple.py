#!/usr/bin/env python3
"""Simple test script to verify sentiment detection works correctly."""

def test_sentiment_keywords():
    """Test the keywords for sentiment detection."""
    
    # Test message that triggered the issue
    test_message = "This seems like a great fit!"
    
    move_forward_keywords = [
        "yes", "sure", "okay", "alright", "sounds good", "let's do it",
        "good fit", "great fit", "perfect fit", "exactly what we need",
        "this could work", "this would work", "let's proceed", 
        "next step", "move forward", "schedule", "book", "meeting",
        "when can we start", "how do we proceed", "what's next",
        "sign me up", "i'm interested", "very interested",
        "looks good", "sounds perfect", "i like it", "impressive",
        "this is helpful", "exactly right", "perfect solution",
        "let's talk", "call me", "schedule a call", "book a demo",
        # Added more specific phrases to catch user's exact words
        "seems like a great fit", "seems like a good fit", "looks like a great fit",
        "looks like a good fit", "this seems great", "this looks great",
        "this is great", "this is perfect", "love this", "love it",
        "want this", "need this", "this works", "this will work"
    ]
    
    text_lower = test_message.lower()
    print(f"Testing message: '{test_message}'")
    print(f"Message (lowercase): '{text_lower}'")
    print()
    
    matches = []
    for keyword in move_forward_keywords:
        if keyword in text_lower:
            matches.append(keyword)
    
    print(f"Matching keywords: {matches}")
    print(f"Should detect positive sentiment: {len(matches) > 0}")
    
    # Test specific phrases
    specific_tests = [
        "This seems like a great fit!",
        "This looks like a good fit",
        "This is perfect for us",
        "I love this solution",
        "Great fit for our team"
    ]
    
    print("\nTesting multiple phrases:")
    for phrase in specific_tests:
        phrase_lower = phrase.lower()
        matched = any(keyword in phrase_lower for keyword in move_forward_keywords)
        print(f"'{phrase}' -> {matched}")

if __name__ == "__main__":
    test_sentiment_keywords()
