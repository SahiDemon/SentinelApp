import os
import logging
from pathlib import Path
from dotenv import load_dotenv

def load_environment():
    """
    Load environment variables from cred.env file (preferred) or .env file.
    Returns True if successfully loaded from either file, False otherwise.
    """
    logger = logging.getLogger('sentinel.env')
    
    # Get the app root directory (3 levels up from this file)
    app_root = Path(__file__).parent.parent.parent.absolute()
    
    # Try loading from cred.env first
    cred_env_path = app_root / 'cred.env'
    if cred_env_path.exists():
        logger.info(f"Loading environment from {cred_env_path}")
        load_dotenv(cred_env_path)
        return True
    
    # Fall back to .env if cred.env doesn't exist
    env_path = app_root / '.env'
    if env_path.exists():
        logger.info(f"Loading environment from {env_path}")
        load_dotenv(env_path)
        return True
    
    logger.warning("No environment file (cred.env or .env) found")
    return False

# Auto-load environment when module is imported
load_environment() 