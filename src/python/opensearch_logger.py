import os
import socket
import getpass
import datetime
import json
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
import warnings

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

        self.client = OpenSearch(
            hosts=[{'host': host, 'port': port}],
            http_auth=auth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            ssl_assert_hostname=ssl_assert_hostname,
            ssl_show_warn=False, # Suppress general SSL warnings if verify_certs=False
            connection_class=RequestsHttpConnection,
            timeout=30, # Increase timeout
            max_retries=3, # Retry up to 3 times
            retry_on_timeout=True 
        )
        
        # Check connection and create index if it doesn't exist
        try:
            if not self.client.ping():
                print("Warning: Could not ping OpenSearch cluster.")
            # self.create_index_if_not_exists() # Optional: Create index on init
        except exceptions.ConnectionError as e:
            print(f"Error connecting to OpenSearch: {e}")
            self.client = None # Disable client if connection fails initially
        except Exception as e:
            print(f"An unexpected error occurred during OpenSearch initialization: {e}")
            self.client = None


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
                        "event_details": {
                            "type": "object", 
                            "enabled": False # Avoid mapping explosion for nested/dynamic details
                        }
                    }
                }
                self.client.indices.create(index=self.index_name, body={'mappings': mapping})
                print(f"Index '{self.index_name}' created.")
            else:
                print(f"Index '{self.index_name}' already exists.")
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

        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hostname": self.hostname,
            "user_identifier": self.user_identifier, # OS User
            "electron_user_id": self.electron_user_id if hasattr(self, 'electron_user_id') else None, # Electron User
            "monitor_type": monitor_type,
            "event_type": event_type,
            "pid": self.pid,
            "event_details": event_details 
        }
        
        # Remove electron_user_id if it's None to keep logs cleaner
        if log_entry["electron_user_id"] is None:
            del log_entry["electron_user_id"]

        try:
            response = self.client.index(
                index=self.index_name,
                body=log_entry,
                request_timeout=30 # Timeout for the index operation
            )
            # print(f"Log sent: {response['result']}") # Optional: print confirmation
        except exceptions.ConnectionTimeout as e:
             print(f"Error sending log to OpenSearch (Timeout): {e}")
        except exceptions.ConnectionError as e:
             print(f"Error sending log to OpenSearch (Connection Error): {e}")
        except exceptions.TransportError as e:
             print(f"Error sending log to OpenSearch (Transport Error): Status {e.status_code}, Info: {e.info}")
        except Exception as e:
             print(f"An unexpected error occurred sending log: {e}")

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