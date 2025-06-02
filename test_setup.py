#!/usr/bin/env python3
"""
Test script to verify Turso database connection and basic functionality.
Run this after installing dependencies to ensure everything works.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_environment():
    """Test if all required environment variables are set."""
    print("🔍 Testing Environment Variables...")
    
    required_vars = ['GROQ_API_KEY', 'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
        else:
            print(f"  ✅ {var}: Set")
    
    if missing_vars:
        print(f"  ❌ Missing variables: {', '.join(missing_vars)}")
        return False
    
    print("  ✅ All environment variables are set!\n")
    return True

def test_imports():
    """Test if all required packages can be imported."""
    print("📦 Testing Package Imports...")
    
    packages = [
        ('fastapi', 'FastAPI'),
        ('uvicorn', 'Uvicorn ASGI Server'),
        ('groq', 'Groq AI'),
        ('pydantic', 'Pydantic'),
        ('requests', 'Requests'),
        ('aiofiles', 'Async File Operations'),
        ('libsql_experimental', 'Turso libSQL'),
    ]
    
    failed_imports = []
    
    for package, description in packages:
        try:
            __import__(package)
            print(f"  ✅ {description}: OK")
        except ImportError as e:
            print(f"  ❌ {description}: Failed - {e}")
            failed_imports.append(package)
    
    if failed_imports:
        print(f"\n❌ Failed to import: {', '.join(failed_imports)}")
        print("Run: pip install fastapi uvicorn groq python-dotenv aiofiles pydantic requests libsql-experimental==0.0.54")
        return False
    
    print("  ✅ All packages imported successfully!\n")
    return True

def test_database_connection():
    """Test Turso database connection."""
    print("🗄️  Testing Database Connection...")
    
    try:
        from database import DatabaseManager
        
        # Test database initialization
        db = DatabaseManager()
        print("  ✅ Database manager initialized")
        
        # Test creating a test session
        test_session_id = "test_session_123"
        success = db.create_session(test_session_id, {
            "company_name": "Test Company",
            "domain": "Technology",
            "problem": "Testing database connection",
            "budget": "$1000"
        })
        
        if success:
            print("  ✅ Test session created")
            
            # Test retrieving the session
            session = db.get_session(test_session_id)
            if session:
                print("  ✅ Test session retrieved")
                
                # Test adding a message
                db.add_message(test_session_id, "user", "Hello, this is a test message")
                print("  ✅ Test message added")
                
                # Clean up - close the test session
                db.close_session(test_session_id)
                print("  ✅ Test session closed")
                
                print("  ✅ Database connection test successful!\n")
                return True
            else:
                print("  ❌ Failed to retrieve test session")
                return False
        else:
            print("  ❌ Failed to create test session")
            return False
            
    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 AI Voice Agent - System Test\n")
    
    all_tests_passed = True
    
    # Test environment variables
    if not test_environment():
        all_tests_passed = False
    
    # Test package imports
    if not test_imports():
        all_tests_passed = False
    
    # Test database connection
    if not test_database_connection():
        all_tests_passed = False
    
    # Final result
    if all_tests_passed:
        print("🎉 All tests passed! Your AI Voice Agent is ready to run.")
        print("Execute: python main.py")
    else:
        print("❌ Some tests failed. Please fix the issues above before running the agent.")
        sys.exit(1)

if __name__ == "__main__":
    main()
