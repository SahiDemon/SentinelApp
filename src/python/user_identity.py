"""
User identity module for Sentinel App.
Handles user identification in logs and events.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

# Configure logger
logger = logging.getLogger(__name__)

class UserIdentity:
    """
    User identity manager for the Sentinel App.
    Ensures consistent user identification across logs and events.
    """
    
    def __init__(self):
        """Initialize the user identity manager."""
        # User identity information
        self.user_id = None
        self.correlation_id = None
        self.session_id = None
        self.device_info = self._get_device_info()
        
    def set_user(self, user_id: str, correlation_id: Optional[str] = None) -> None:
        """
        Set the current user identity.
        
        Args:
            user_id: The user's ID
            correlation_id: Optional correlation ID for tracking across sessions
        """
        self.user_id = user_id
        
        if correlation_id:
            self.correlation_id = correlation_id
        else:
            # Generate a simple correlation ID if none provided
            import uuid
            import time
            self.correlation_id = f"{user_id}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            
        logger.info(f"User identity set: {user_id} with correlation ID: {self.correlation_id}")
    
    def clear_user(self) -> None:
        """Clear the current user identity."""
        prev_user = self.user_id
        self.user_id = None
        self.correlation_id = None
        logger.info(f"User identity cleared for user: {prev_user}")
    
    def enrich_log(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a log entry with user identity information.
        
        Args:
            log_data: The log data to enrich
            
        Returns:
            The enriched log data
        """
        enriched_data = log_data.copy()
        
        # Add user identification fields if available
        if self.user_id:
            enriched_data["user_id"] = self.user_id
            # Include electron_user_id for backward compatibility with UBA
            enriched_data["electron_user_id"] = self.user_id
        
        if self.correlation_id:
            enriched_data["correlation_id"] = self.correlation_id
            
        if self.session_id:
            enriched_data["session_id"] = self.session_id
            
        # Add device information
        enriched_data["device_info"] = self.device_info
        
        return enriched_data
    
    def _get_device_info(self) -> Dict[str, Any]:
        """
        Get device information.
        
        Returns:
            Dictionary of device information
        """
        import platform
        import uuid
        
        # Generate a stable device ID
        try:
            # Try to get machine UUID
            if platform.system() == "Windows":
                import subprocess
                result = subprocess.check_output('wmic csproduct get uuid').decode()
                device_id = result.split('\n')[1].strip()
            elif platform.system() == "Darwin":  # macOS
                import subprocess
                result = subprocess.check_output('ioreg -rd1 -c IOPlatformExpertDevice').decode()
                from re import findall
                device_id = findall(r'IOPlatformUUID.*?\"(.*?)\"', result)[0]
            else:  # Linux
                with open('/etc/machine-id', 'r') as f:
                    device_id = f.read().strip()
        except Exception:
            # Fallback - create a device ID based on hostname and store it
            device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, platform.node()))
        
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "hostname": platform.node(),
            "device_id": device_id,
            "platform": platform.platform()
        }
    
    def start_session(self) -> str:
        """
        Start a new session and generate a session ID.
        
        Returns:
            The new session ID
        """
        import uuid
        self.session_id = str(uuid.uuid4())
        logger.info(f"New session started: {self.session_id}")
        return self.session_id
    
    def get_identity_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for identity propagation.
        
        Returns:
            Dictionary of identity headers
        """
        headers = {}
        
        if self.user_id:
            headers["X-User-ID"] = self.user_id
            
        if self.correlation_id:
            headers["X-Correlation-ID"] = self.correlation_id
            
        if self.session_id:
            headers["X-Session-ID"] = self.session_id
            
        return headers


# Create singleton instance
user_identity = UserIdentity() 