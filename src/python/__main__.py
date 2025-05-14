"""
Main entry point for running the SentinelApp Python module
"""

import sys
import os

# Add the parent directory to sys.path to handle imports properly
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import and run the sentinel module
from src.python.sentinel import main

if __name__ == "__main__":
    # Run the main function
    main() 