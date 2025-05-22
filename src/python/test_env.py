import os
import sys

# Add parent directory to path to fix imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import our environment loader
from src.python.load_env import load_environment

def test_environment():
    """Test that environment variables can be loaded from cred.env or .env"""
    print("Testing environment variable loading...")
    
    # Try to load environment variables
    result = load_environment()
    print(f"Load environment result: {result}")
    
    # Check if essential variables are set
    variables = [
        # Supabase variables
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_KEY",
        
        # Sentinel API variables
        "SENTINEL_PRIME_API_URL",
        "SENTINEL_PRIME_API_KEY",
        
        # OpenSearch variables
        "OPENSEARCH_TIMEOUT",
        "OPENSEARCH_RETRY",
        "OPENSEARCH_HOST",
        "OPENSEARCH_PORT",
        "OPENSEARCH_USERNAME",
        "OPENSEARCH_PASSWORD",
        "OPENSEARCH_INDEX",
        
        # System variables
        "SENTINEL_INTEGRATED",
        "PORT"
    ]
    
    print("\nEnvironment variables:")
    for var in variables:
        value = os.environ.get(var)
        masked_value = "***" if value and (var.endswith("KEY") or var.endswith("ANON_KEY") or var.endswith("PASSWORD")) else value
        print(f"  {var}: {masked_value}")
    
    # Check if all essential variables are set
    all_set = all(os.environ.get(var) for var in variables)
    print(f"\nAll essential variables set: {all_set}")
    
if __name__ == "__main__":
    test_environment() 