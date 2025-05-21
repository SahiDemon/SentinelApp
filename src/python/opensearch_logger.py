import os
import socket
import getpass
import datetime
import json
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
import warnings
import sys
import time

# Add parent directory to path to fix imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Use absolute import to work with module execution
from src.python.user_identity import user_identity

# Suppress specific InsecureRequestWarning from urllib3
from urllib3.exceptions import InsecureRequestWarning
warnings.filterwarnings(
    "ignore",
    category=InsecureRequestWarning
)

class OpenSearchLogger:
    """Handles formatting and sending logs to an OpenSearch cluster."""

    def __init__(self, host='search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws', 
                 port=443, 
                 auth=('SahiDemon', 'Sahi@448866'), 
                 index_name='sentinel_raw_logs',
                 use_ssl=True, 
                 verify_certs=False, # Set to False for self-signed certs or AWS OS domains without custom endpoint
                 ssl_assert_hostname=False,
                 electron_user_id=None): # Add electron_user_id parameter
        
        self.index_name = index_name
        self.hostname = socket.gethostname()
        try:
            self.user_identifier = getpass.getuser() # This is the OS user
        except Exception:
            self.user_identifier = "unknown_user" # Fallback if getuser fails
            
        self.electron_user_id = electron_user_id # Store the Electron user ID
        self.pid = os.getpid()
        
        # Add Supabase configuration
        self.supabase_url = os.environ.get('SUPABASE_URL', 'https://qackdhpbvfbeyhxovlqj.supabase.co')
        self.supabase_key = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhY2tkaHBidmZiZXloeG92bHFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzc5NTUzNzIsImV4cCI6MjA1MzUzMTM3Mn0.JZbYaTngJy3lGFqtvI3efcmxdosdmD48Nv2zgTeaHY0')

        # Get timeout and retry settings from environment variables or use defaults
        timeout = int(os.environ.get('OPENSEARCH_TIMEOUT', 30))
        max_retries = int(os.environ.get('OPENSEARCH_RETRY', 3))
        
        # Clear any proxy settings that might interfere with the connection
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ['NO_PROXY'] = ','.join(['localhost', '127.0.0.1', host])
        
        print(f"Initializing OpenSearch connection to {host}:{port} with timeout={timeout}s, retries={max_retries}")

        self.client = OpenSearch(
            hosts=[{'host': host, 'port': port}],
            http_auth=auth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            ssl_assert_hostname=ssl_assert_hostname,
            ssl_show_warn=False, # Suppress general SSL warnings if verify_certs=False
            connection_class=RequestsHttpConnection,
            timeout=timeout, 
            max_retries=max_retries,
            retry_on_timeout=True 
        )
        
        # Check connection and create index if it doesn't exist
        max_connection_attempts = 3
        for attempt in range(max_connection_attempts):
            try:
                if self.client.ping():
                    print(f"Successfully connected to OpenSearch cluster at {host}")
                    self.create_index_if_not_exists()
                    return
                else:
                    print(f"Warning: Could not ping OpenSearch cluster (attempt {attempt+1}/{max_connection_attempts})")
            except exceptions.ConnectionError as e:
                print(f"Error connecting to OpenSearch (attempt {attempt+1}/{max_connection_attempts}): {e}")
                if attempt < max_connection_attempts - 1:
                    time.sleep(2)  # Wait before retry
            except Exception as e:
                print(f"An unexpected error occurred during OpenSearch initialization: {e}")
                
        # If we get here, all connection attempts failed
        print("Failed to connect to OpenSearch after multiple attempts. Logging will fall back to console.")
        self.client = None  # Disable client if connection fails


    def create_index_if_not_exists(self):
        """Creates the index with a predefined mapping if it doesn't exist."""
        if not self.client:
            print("Cannot create index, OpenSearch client is not initialized.")
            return

        try:
            if not self.client.indices.exists(index=self.index_name):
                mapping = {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "hostname": {"type": "keyword"},
                        "user_identifier": {"type": "keyword"},
                        "monitor_type": {"type": "keyword"},
                        "event_type": {"type": "keyword"},
                        "pid": {"type": "integer"},
                        # Add optimized mappings for user identity fields
                        "user_id": {"type": "keyword"},
                        "electron_user_id": {"type": "keyword"},
                        "correlation_id": {"type": "keyword"},
                        "session_id": {"type": "keyword"},
                        "event_details": {
                            "type": "object", 
                            "enabled": True  # Changed to true for better searchability
                        }
                    }
                }
                self.client.indices.create(index=self.index_name, body={'mappings': mapping})
                print(f"Index '{self.index_name}' created with improved mappings.")
                
                # Force index refresh to ensure immediate availability
                self.client.indices.refresh(index=self.index_name)
            else:
                print(f"Index '{self.index_name}' already exists.")
                
                # Force index refresh to ensure immediate availability of logs
                self.client.indices.refresh(index=self.index_name)
        except exceptions.RequestError as e:
            # Handle potential race conditions if index created between check and create
            if e.error == 'resource_already_exists_exception':
                print(f"Index '{self.index_name}' already exists (detected race condition).")
            else:
                 print(f"Error creating index '{self.index_name}': {e}")
        except exceptions.ConnectionError as e:
            print(f"Connection error during index creation: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during index creation: {e}")


    def log(self, monitor_type: str, event_type: str, event_details: dict):
        """Formats and sends a log entry to OpenSearch."""
        if not self.client:
            # Fallback print if client failed or hasn't initialized
            fallback_details = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "hostname": self.hostname,
                "os_user": self.user_identifier,
                "electron_user": self.electron_user_id if hasattr(self, 'electron_user_id') else 'N/A',
                "monitor": monitor_type,
                "event": event_type,
                "details": event_details
            }
            print(f"OS_LOG_FALLBACK: {json.dumps(fallback_details)}")
            return

        # Create base log entry
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": self.hostname,
            "user_identifier": self.user_identifier, # OS User
            "monitor_type": monitor_type,
            "event_type": event_type,
            "pid": self.pid,
            "event_details": event_details 
        }
        
        # Use the Electron user ID from constructor if set
        if hasattr(self, 'electron_user_id') and self.electron_user_id:
            log_entry["electron_user_id"] = self.electron_user_id
        
        # Enrich log with user identity information
        log_entry = user_identity.enrich_log(log_entry)

        # Add log timestamp as epoch milliseconds to improve searchability
        log_entry["log_timestamp_ms"] = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)

        try:
            response = self.client.index(
                index=self.index_name,
                body=log_entry,
                request_timeout=30 # Timeout for the index operation
            )
            
            # Force refresh the index every few log entries to ensure logs are searchable immediately
            # This can impact performance but improves visibility of recent logs
            if hasattr(self, '_log_count'):
                self._log_count += 1
            else:
                self._log_count = 1
                
            if self._log_count % 5 == 0:  # Refresh every 5 logs
                try:
                    self.client.indices.refresh(index=self.index_name)
                except Exception as refresh_error:
                    print(f"Error refreshing index: {refresh_error}")
                    
            # print(f"Log sent: {response['result']}") # Optional: print confirmation
        except exceptions.ConnectionTimeout as e:
             print(f"Error sending log to OpenSearch (Timeout): {e}")
        except exceptions.ConnectionError as e:
             print(f"Error sending log to OpenSearch (Connection Error): {e}")
        except exceptions.TransportError as e:
             print(f"Error sending log to OpenSearch (Transport Error): Status {e.status_code}, Info: {e.info}")
        except Exception as e:
             print(f"An unexpected error occurred sending log: {e}")

    def set_user(self, user_id: str, correlation_id: str = None):
        """
        Set the current user for all subsequent logs.
        
        Args:
            user_id: User ID to include in logs
            correlation_id: Optional correlation ID for tracking across sessions
        """
        # Store in instance for backward compatibility
        self.electron_user_id = user_id
        
        # Set in the user identity module for consistent identification
        user_identity.set_user(user_id, correlation_id)
        
    def clear_user(self):
        """Clear the current user identification."""
        self.electron_user_id = None
        user_identity.clear_user()

# --- Usage Example (can be removed or commented out later) ---
# if __name__ == "__main__":
#     print("Initializing OpenSearch Logger...")
#     # Uses default credentials and host from class definition
#     logger = OpenSearchLogger() 
    
#     # Optional: Explicitly create index if needed (e.g., for first run)
#     # print("Creating index...")
#     # logger.create_index_if_not_exists()
    
#     print("Sending test log...")
#     logger.log(
#         monitor_type="test_monitor",
#         event_type="test_event",
#         event_details={"message": "This is a test log entry", "value": 123}
#     )
#     print("Test log sent (check OpenSearch/Kibana).")
#     print("If you see errors, check OpenSearch status, credentials, and network connectivity.")
#     # Keep alive briefly for async operations if needed, though index() is usually synchronous
#     # import time
#     # time.sleep(2) 