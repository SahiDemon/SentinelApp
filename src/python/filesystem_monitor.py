import os
import time
import hashlib
import logging
import psutil
import win32clipboard
import ctypes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re
from collections import defaultdict, deque
import requests
import urllib3
import json
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path

# OpenSearch configuration
OPENSEARCH_HOST = "https://localhost:9200"
OPENSEARCH_INDEX = "file_monitor"
AUTH = ("admin", "Sahi_448866")
HEADERS = {"Content-Type": "application/json"}

# Disable SSL warnings for self-signed certs
urllib3.disable_warnings()

def setup_logger(name, log_dir=None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Ensure logger doesn't have existing handlers
    logger.handlers = []
    
    # Create console handler with INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    return logger

def is_admin():
    """Check if the program is running with admin rights"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class UserFileMonitor:
    def __init__(self, log_dir=None):
        self.logger = setup_logger('user_file_monitor')
        
        # Add recycling bin paths to ignore
        self.ignore_patterns = {
            r'\$RECYCLE\.BIN',
            r'\$I[^\\]+',  # Recycle bin metadata files
            r'\$R[^\\]+',  # Recycle bin content files
            'desktop.ini'
        }
        
        # Track deleted folders
        self.deleted_folders = {}  # {folder_path: deletion_time}
        self.folder_deletion_timeout = 2  # seconds
        
        # Define sensitive paths and extensions
        self.sensitive_paths = {
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Downloads")
        }
        
        self.sensitive_extensions = {
            # Documents
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            # Source code
            '.py', '.js', '.java', '.cpp', '.h', '.cs', '.php',
            # Databases
            '.db', '.sqlite', '.mdb',
            # Configuration
            '.env', '.config', '.yml', '.json',
            # Archives
            '.zip', '.rar', '.7z', '.tar', '.gz'
        }
        
        # Paths to completely ignore
        self.ignore_paths = {
            os.path.expandvars(r'%APPDATA%'),
            os.path.expandvars(r'%LOCALAPPDATA%'),
            r'C:\Windows',
            r'C:\Program Files',
            r'C:\Program Files (x86)',
            r'C:\ProgramData',
        }
        
        # Add more paths to ignore
        self.ignore_paths.update({
            os.path.expandvars(r'%TEMP%'),
            os.path.expandvars(r'%TMP%'),
            os.path.expanduser('~/.vscode'),
            os.path.expanduser('~/.git'),
            os.path.expanduser('~/AppData'),
        })
        
        # Track bulk operations
        self.recent_operations = defaultdict(lambda: defaultdict(list))  # {dir: {type: [(time, path)]}}
        self.bulk_threshold = 3  # Lower threshold for bulk operations
        self.operation_window = 2  # Shorter time window
        self.last_bulk_alert = defaultdict(float)  # Track last alert time per directory
        self.bulk_alert_cooldown = 5  # seconds between bulk alerts

        # Add cooldown tracking
        self.recent_alerts = deque(maxlen=100)
        self.alert_cooldown = 5  # seconds

        # Add file hash tracking
        self.file_hashes = {}
        self.hash_expiry = 300  # 5 minutes
        self.min_file_size = 100  # bytes
        self.max_file_size = 100 * 1024 * 1024  # 100MB

        # Add fallback paths for non-admin mode
        self.fallback_paths = [
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Desktop")
        ]
        
        # Add debug flag
        self.debug = True
        self.log_dir = log_dir
        
        # Test logging
        self.logger.debug("FileMonitor initialized")
        self.logger.info("Monitoring system starting...")

        # Initialize OpenSearch session with retries
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.1)
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.verify = False  # Skip SSL verification
        self.session.auth = AUTH
        self.session.headers.update(HEADERS)

        # Initialize OpenSearch
        self.setup_opensearch()

        # Add throttling for frequently modified files
        self.last_modification_time = {}  # {file_path: last_time}
        self.modification_cooldown = 5  # seconds between modifications
        
        # Add patterns for files to throttle
        self.throttle_patterns = {
            '.vhdx',  # Virtual disk files
            '.vhd',
            '.vmdk',
            '.log',
            '.tmp',
            '.temp'
        }

        # Add specific patterns to completely ignore
        self.ignore_file_patterns = {
            r'.*\.vhdx$',  # Virtual disk files
            r'.*\.log$',   # Log files
            r'.*\.tmp$',   # Temp files
            r'.*\.temp$',  # Temp files
            r'.*\.cache$', # Cache files
            r'.*\.sock$',  # Socket files
            r'.*\.pid$',   # Process ID files
            r'.*docker.*', # Docker related files
            r'.*wsl.*',    # WSL related files
            r'.*\.git.*',  # Git files
        }

        # Add size threshold for modifications
        self.min_size_change = 1024 * 1024  # 1MB
        self.last_file_sizes = {}

        # Update recycle bin patterns
        self.recycle_bin_patterns = {
            r'.*\$RECYCLE\.BIN.*',
            r'.*\$R[^\\]+\..*',  # Recycle bin content files
            r'.*\$I[^\\]+\..*',  # Recycle bin metadata files
        }
        
        # Update bulk operation settings
        self.bulk_operation_cache = defaultdict(list)  # {operation_type: [(timestamp, path)]}
        self.bulk_window = 2  # seconds
        self.bulk_count_threshold = 3  # files

        # Add improved bulk operation tracking
        self.bulk_tracking = {
            'window': 5,  # seconds to track
            'threshold': 3,  # number of files to trigger bulk
            'operations': defaultdict(lambda: defaultdict(list)),  # {dir: {operation: [(time, path)]}}
            'cooldown': {}  # {dir: last_bulk_time}
        }
        
        # Enhance system paths and patterns
        self.system_paths_patterns = {
            r'.*\\AppData\\Local\\Temp\\.*',
            r'.*\\AppData\\Local\\Google\\Chrome\\.*',
            r'.*\\AppData\\Local\\Microsoft\\.*',
            r'.*\\Program Files.*\\.*\\diagnostic\.data\\.*',
            r'.*\\AppData\\Local\\.*\\Cache\\.*',
            r'.*\\AppData\\Roaming\\.*\\Cache\\.*',
            r'.*\.tmp$',
            r'.*\.TMP$',
            r'.*\.temp$',
            r'.*\.crdownload$',
            r'.*\\MongoDB\\Server\\.*\\data\\.*',
            r'.*\\ProgramData\\.*\\Logs\\.*',
            r'.*\\AppData\\Local\\.*\\logs\\.*',
            r'.*\.\~.*$',  # Temporary files with tilde
            r'.*\.part$',  # Partial downloads
            r'.*\.temporary$',
        }

        # Add known software patterns
        self.software_paths = {
            'chrome': r'.*\\Google\\Chrome\\.*',
            'mongodb': r'.*\\MongoDB\\Server\\.*',
            'vscode': r'.*\\Code\\.*',
            'edge': r'.*\\Microsoft\\Edge\\.*',
            'firefox': r'.*\\Mozilla\\Firefox\\.*',
        }
        
    def setup_opensearch(self):
        """Setup OpenSearch index with visualization-friendly mapping"""
        try:
            mapping = {
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "event_type": {
                            "type": "text",
                            "fielddata": True,
                            "fields": {
                                "raw": {"type": "keyword"}
                            }
                        },
                        "file_path": {
                            "type": "text",
                            "fielddata": True,
                            "fields": {
                                "raw": {"type": "keyword"}
                            }
                        },
                        "file_name": {
                            "type": "text",
                            "fielddata": True,
                            "fields": {
                                "raw": {"type": "keyword"}
                            }
                        },
                        "directory": {
                            "type": "text",
                            "fielddata": True,
                            "fields": {
                                "raw": {"type": "keyword"}
                            }
                        },
                        "host": {
                            "type": "keyword"
                        },
                        "operation": {
                            "type": "keyword"
                        },
                        "file_count": {
                            "type": "integer"
                        },
                        "details": {
                            "type": "object",
                            "properties": {
                                "operation": {"type": "keyword"},
                                "file_count": {"type": "integer"},
                                "file_size": {"type": "long"},
                                "is_sensitive": {"type": "boolean"},
                                "category": {"type": "keyword"}
                            }
                        }
                    }
                }
            }

            # Delete existing index if exists
            try:
                self.session.delete(f"{OPENSEARCH_HOST}/{OPENSEARCH_INDEX}")
            except:
                pass

            # Create new index with mapping
            response = self.session.put(
                f"{OPENSEARCH_HOST}/{OPENSEARCH_INDEX}",
                json=mapping
            )
            
            if response.status_code not in (200, 201):
                print(f"Failed to create index: {response.text}")
            else:
                print("OpenSearch index created successfully")
                
        except Exception as e:
            print(f"Error setting up OpenSearch: {str(e)}")

    def get_file_hash(self, path):
        """Get hash of first 8KB of file to detect changes"""
        try:
            if os.path.getsize(path) < self.min_file_size:
                return None
                
            with open(path, 'rb') as f:
                return hashlib.md5(f.read(8192)).hexdigest()
        except:
            return None
            
    def is_real_change(self, path):
        """Check if file actually changed based on content"""
        try:
            current_hash = self.get_file_hash(path)
            if not current_hash:
                return False
                
            last_hash = self.file_hashes.get(path, (None, 0))
            self.file_hashes[path] = (current_hash, time.time())
            
            # Clean old hashes
            self._clean_old_hashes()
            
            return current_hash != last_hash[0]
        except:
            return False
            
    def _clean_old_hashes(self):
        """Remove expired file hashes"""
        current_time = time.time()
        self.file_hashes = {
            path: (hash_value, timestamp)
            for path, (hash_value, timestamp) in self.file_hashes.items()
            if current_time - timestamp < self.hash_expiry
        }

    def is_sensitive_file(self, path):
        """Enhanced sensitive file detection"""
        try:
            if not os.path.exists(path):
                return False
                
            file_size = os.path.getsize(path)
            if file_size < self.min_file_size or file_size > self.max_file_size:
                return False
                
            if not self.is_real_change(path):
                return False
                
            # Check if in sensitive location
            if any(path.startswith(sensitive) for sensitive in self.sensitive_paths):
                return True
                
            # Check extension
            ext = os.path.splitext(path)[1].lower()
            return ext in self.sensitive_extensions
        except:
            return False

    def is_system_file(self, path):
        """Enhanced system file detection"""
        try:
            norm_path = os.path.normpath(path).lower()
            
            # Check against system patterns
            if any(re.match(pattern, norm_path, re.IGNORECASE) for pattern in self.system_paths_patterns):
                return True
                
            # Check if it's a known software path
            if any(re.match(pattern, norm_path, re.IGNORECASE) for pattern in self.software_paths.values()):
                return True
                
            # Check common system operations
            if any(keyword in norm_path for keyword in [
                'temp', 'tmp', 'cache', 'logs',
                'appdata', 'programdata', 'diagnostic.data',
                'cookies', 'crashpad', 'prefetch'
            ]):
                return True
                
            return False
        except:
            return True

    def should_ignore(self, path):
        """Enhanced path filtering"""
        try:
            # First check if it's a system file
            if self.is_system_file(path):
                return True
                
            # Check recycle bin
            if self.is_recycle_bin_operation(path):
                return True
                
            # First check existing ignore conditions
            if any(keyword in path.lower() for keyword in [
                'cache', 'temp', 'tmp', 'log',
                'appdata', 'windows', 'program files',
                '.git', '.vs', '__pycache__', 'node_modules'
            ]):
                return True

            # Check against regex patterns
            if any(re.search(pattern, path, re.IGNORECASE) for pattern in self.ignore_file_patterns):
                return True

            # Check if it's a system or temp file/path
            if any(path.startswith(ignore) for ignore in self.ignore_paths):
                return True

            return False
        except:
            return True

    def is_significant_change(self, path):
        """Check if file change is significant enough to report"""
        try:
            current_size = os.path.getsize(path)
            last_size = self.last_file_sizes.get(path, 0)
            self.last_file_sizes[path] = current_size

            # Clean up old entries
            if len(self.last_file_sizes) > 1000:
                self.last_file_sizes.clear()

            # Check if size change is significant
            return abs(current_size - last_size) > self.min_size_change
        except:
            return False

    def should_alert(self, path, event_type):
        """Check if we should alert about this file"""
        current_time = time.time()
        
        # Check for duplicate alerts
        for timestamp, old_path, old_type in self.recent_alerts:
            if (current_time - timestamp) < self.alert_cooldown:
                if path == old_path and event_type == old_type:
                    return False
                    
        self.recent_alerts.append((current_time, path, event_type))
        return True

    def send_to_opensearch(self, event_type, file_path, details=None):
        """Send event with visualization-friendly structure"""
        try:
            # Get file info
            file_name = os.path.basename(file_path)
            directory = os.path.dirname(file_path)
            
            # Determine file category
            category = "other"
            ext = os.path.splitext(file_name)[1].lower()
            if ext in {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}:
                category = "document"
            elif ext in {'.jpg', '.png', '.gif'}:
                category = "image"
            elif ext in {'.py', '.js', '.java', '.cpp'}:
                category = "code"
            
            # Build details dictionary properly
            details_dict = {}
            if details:
                details_dict.update(details)
                
            details_dict.update({
                "category": category,
                "is_sensitive": self.is_sensitive_file(file_path),
                "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
            })
            
            # Build event data
            event_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "file_path": file_path,
                "file_name": file_name,
                "directory": directory,
                "host": os.environ.get('COMPUTERNAME', 'unknown'),
                "operation": event_type.split('.')[0],  # 'file', 'folder', etc
                "file_count": details_dict.get('file_count', 1),
                "details": details_dict
            }
            
            # Send to OpenSearch
            response = self.session.post(
                f"{OPENSEARCH_HOST}/{OPENSEARCH_INDEX}/_doc",
                json=event_data,
                timeout=5,
                verify=False
            )
            
            # Enhanced response logging
            print("\nOpenSearch Response:")
            print("-" * 50)
            print(f"Status Code: {response.status_code}")
            try:
                resp_json = response.json()
                print(f"Index: {resp_json.get('_index')}")
                print(f"Document ID: {resp_json.get('_id')}")
                print(f"Result: {resp_json.get('result')}")
                if 'error' in resp_json:
                    print("Error Details:")
                    print(json.dumps(resp_json['error'], indent=2))
            except Exception as e:
                print(f"Raw Response: {response.text}")
            print("-" * 50)
            
            return response.status_code in (200, 201)
                
        except Exception as e:
            print(f"OpenSearch Error: {str(e)}")
            return False

    def log_bulk_operation(self, operation_type, path):
        """Improved bulk file operations logging"""
        try:
            current_time = time.time()
            parent_dir = os.path.dirname(path)
            
            # Clean old operations
            self.recent_operations[parent_dir][operation_type] = [
                (t, p) for t, p in self.recent_operations[parent_dir][operation_type]
                if current_time - t <= self.operation_window
            ]
            
            # Add new operation with path tracking
            self.recent_operations[parent_dir][operation_type].append((current_time, path))
            
            # Check if enough time has passed since last alert
            if current_time - self.last_bulk_alert[parent_dir] < self.bulk_alert_cooldown:
                return
                
            # Get unique files in the time window
            unique_files = set(p for _, p in self.recent_operations[parent_dir][operation_type])
            if len(unique_files) >= self.bulk_threshold:
                self.logger.warning(
                    f"Multiple {operation_type} operations in {parent_dir}:\n"
                    f"- Affected files ({len(unique_files)}):\n"
                    f"- {', '.join(os.path.basename(p) for p in list(unique_files)[:5])}"
                    + (" ..." if len(unique_files) > 5 else "")
                )
                details = {
                    "operation": operation_type,
                    "file_count": len(unique_files),
                    "affected_files": [os.path.basename(p) for p in list(unique_files)[:5]]
                }
                self.send_to_opensearch("bulk_operation", parent_dir, details)
                # Clear operations and update last alert time
                self.recent_operations[parent_dir][operation_type].clear()
                self.last_bulk_alert[parent_dir] = current_time
                
        except Exception as e:
            self.logger.error(f"Error in bulk operation logging: {str(e)}")

    def log_folder_deletion(self, folder_path):
        """Log folder deletion with intelligent summary"""
        try:
            if folder_path in self.deleted_folders:
                return  # Already logged
                
            file_count = 0
            total_size = 0
            important_files = []
            
            # Quick scan of deleted folder contents
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_count += 1
                    try:
                        total_size += os.path.getsize(file_path)
                        if self.is_sensitive_file(file_path):
                            important_files.append(os.path.relpath(file_path, folder_path))
                    except:
                        continue
            
            # Log summary
            self.logger.warning(
                f"Folder Deleted: {folder_path}\n"
                f"- Total Files: {file_count}\n"
                f"- Total Size: {total_size / (1024*1024):.2f} MB"
                + (f"\n- Important Files: {', '.join(important_files)}" if important_files else "")
            )
            
            self.deleted_folders[folder_path] = time.time()
            
        except Exception as e:
            self.logger.error(f"Error logging folder deletion: {str(e)}")

    def clean_deleted_folders(self):
        """Clean up old folder deletion records"""
        current_time = time.time()
        self.deleted_folders = {
            path: timestamp 
            for path, timestamp in self.deleted_folders.items()
            if current_time - timestamp < self.folder_deletion_timeout
        }

    def monitor(self):
        """Start monitoring the file system"""
        print("Starting file monitoring...")
        
        event_handler = UserFileHandler(self)
        observer = Observer()
        
        # If not admin, use fallback paths
        if not is_admin():
            self.logger.warning("Running without admin rights - monitoring user directories only")
            paths_to_monitor = self.fallback_paths
        else:
            paths_to_monitor = self._get_fixed_drives()
            
        self.logger.debug(f"Paths to monitor: {paths_to_monitor}")
        
        # Monitor available paths
        monitored = False
        for path in paths_to_monitor:
            try:
                if os.path.exists(path):
                    observer.schedule(event_handler, path, recursive=True)
                    self.logger.info(f"Successfully monitoring: {path}")
                    monitored = True
                else:
                    self.logger.warning(f"Path does not exist: {path}")
            except Exception as e:
                self.logger.error(f"Error monitoring path {path}: {str(e)}")
        
        if not monitored:
            self.logger.error("No paths could be monitored! Try running as administrator")
            return
            
        # Start the observer
        try:
            observer.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            self.logger.info("File monitoring stopped.")
        observer.join()

    def _get_fixed_drives(self):
        """Get list of fixed drives to monitor with permission check"""
        drives = []
        for partition in psutil.disk_partitions():
            if partition.fstype and 'fixed' in partition.opts:
                try:
                    # Test if we can access the drive
                    test_path = os.path.join(partition.mountpoint, '.')
                    os.listdir(test_path)
                    drives.append(partition.mountpoint)
                except PermissionError:
                    self.logger.warning(f"No permission to monitor drive: {partition.mountpoint}")
                except Exception as e:
                    self.logger.error(f"Error checking drive {partition.mountpoint}: {str(e)}")
        return drives

    def should_throttle(self, file_path):
        """Check if file modifications should be throttled"""
        try:
            # Check file extension
            ext = Path(file_path).suffix.lower()
            if ext in self.throttle_patterns:
                current_time = time.time()
                last_time = self.last_modification_time.get(file_path, 0)
                
                # Clean old entries
                self.last_modification_time = {
                    path: ts for path, ts in self.last_modification_time.items()
                    if current_time - ts < 60  # Remove entries older than 1 minute
                }
                
                # Check cooldown
                if current_time - last_time < self.modification_cooldown:
                    return True
                    
                self.last_modification_time[file_path] = current_time
                
            return False
        except:
            return False

    def is_recycle_bin_operation(self, path):
        """Check if operation is related to recycle bin"""
        return any(re.match(pattern, path, re.IGNORECASE) for pattern in self.recycle_bin_patterns)

    def handle_bulk_operation(self, operation_type, path):
        """Smart bulk operation handling"""
        current_time = time.time()
        
        # Clean old operations
        self.bulk_operation_cache[operation_type] = [
            (ts, p) for ts, p in self.bulk_operation_cache[operation_type]
            if current_time - ts <= self.bulk_window
        ]
        
        # Add new operation
        self.bulk_operation_cache[operation_type].append((current_time, path))
        
        # Check for bulk operation
        recent_ops = self.bulk_operation_cache[operation_type]
        if len(recent_ops) >= self.bulk_count_threshold:
            # Group by directory
            dir_groups = defaultdict(list)
            for _, file_path in recent_ops:
                dir_groups[os.path.dirname(file_path)].append(file_path)
            
            # Report bulk operations by directory
            for dir_path, files in dir_groups.items():
                if len(files) >= self.bulk_count_threshold:
                    details = {
                        "operation": operation_type,
                        "file_count": len(files),
                        "sample_files": [os.path.basename(p) for p in files[:5]]
                    }
                    self.send_to_opensearch(f"bulk_{operation_type}", dir_path, details)
                    
            # Clear cache after reporting
            self.bulk_operation_cache[operation_type].clear()

    def is_bulk_operation(self, operation_type, file_path):
        """Check if this is part of a bulk operation"""
        try:
            current_time = time.time()
            directory = os.path.dirname(file_path)
            
            # Clean old operations
            self.bulk_tracking['operations'][directory][operation_type] = [
                (t, p) for t, p in self.bulk_tracking['operations'][directory][operation_type]
                if current_time - t <= self.bulk_tracking['window']
            ]
            
            # Add new operation
            self.bulk_tracking['operations'][directory][operation_type].append((current_time, file_path))
            
            # Count recent operations in this directory
            recent_ops = self.bulk_tracking['operations'][directory][operation_type]
            return len(recent_ops) >= self.bulk_tracking['threshold']
        except:
            return False

    def handle_bulk_operation(self, operation_type, file_path):
        """Handle bulk operations smartly"""
        try:
            directory = os.path.dirname(file_path)
            current_time = time.time()
            
            # Check cooldown
            last_bulk_time = self.bulk_tracking['cooldown'].get(directory, 0)
            if current_time - last_bulk_time < self.bulk_tracking['window']:
                return True  # Still in bulk operation mode
            
            # Get all recent operations
            recent_ops = self.bulk_tracking['operations'][directory][operation_type]
            if len(recent_ops) >= self.bulk_tracking['threshold']:
                # Send bulk event
                details = {
                    "operation": operation_type,
                    "file_count": len(recent_ops),
                    "first_file": os.path.basename(recent_ops[0][1]),
                    "last_file": os.path.basename(recent_ops[-1][1]),
                    "sample_files": [os.path.basename(p) for _, p in recent_ops[:5]]
                }
                
                self.send_to_opensearch(f"bulk_{operation_type}", directory, details)
                self.bulk_tracking['cooldown'][directory] = current_time
                
                # Clear tracked operations
                self.bulk_tracking['operations'][directory][operation_type].clear()
                return True
                
            return False
        except:
            return False

class UserFileHandler(FileSystemEventHandler):
    def __init__(self, monitor):
        self.monitor = monitor
        self.bulk_operation_cache = defaultdict(dict)  # {directory: {operation_type: last_bulk_time}}

    def is_in_bulk_cooldown(self, directory, operation_type):
        """Check if we're in bulk operation cooldown period"""
        current_time = time.time()
        last_bulk_time = self.bulk_operation_cache.get(directory, {}).get(operation_type, 0)
        return current_time - last_bulk_time < self.monitor.bulk_tracking['window']

    def set_bulk_cooldown(self, directory, operation_type):
        """Set bulk operation cooldown"""
        if directory not in self.bulk_operation_cache:
            self.bulk_operation_cache[directory] = {}
        self.bulk_operation_cache[directory][operation_type] = time.time()

    def on_modified(self, event):
        if (event.is_directory or 
            self.monitor.is_system_file(event.src_path) or  # Check system files first
            self.monitor.should_ignore(event.src_path)):
            return

        directory = os.path.dirname(event.src_path)
        
        # Check for bulk operation or cooldown
        if self.is_in_bulk_cooldown(directory, "modified"):
            return
            
        if self.monitor.is_bulk_operation("modified", event.src_path):
            self.monitor.handle_bulk_operation("modified", event.src_path)
            self.set_bulk_cooldown(directory, "modified")
            return

        # Only send individual event if not in bulk mode
        if self.monitor.is_significant_change(event.src_path):
            print(f"\nFile modification detected: {event.src_path}")
            self.monitor.send_to_opensearch("file.modified", event.src_path)

    def on_deleted(self, event):
        if (self.monitor.is_system_file(event.src_path) or  # Check system files first
            self.monitor.should_ignore(event.src_path)):
            return
            
        directory = os.path.dirname(event.src_path)
        
        # Check for bulk operation or cooldown
        if self.is_in_bulk_cooldown(directory, "deleted"):
            return
            
        if self.monitor.is_bulk_operation("deleted", event.src_path):
            self.monitor.handle_bulk_operation("deleted", event.src_path)
            self.set_bulk_cooldown(directory, "deleted")
            return

        # Only send individual event if not in bulk mode
        if not event.is_directory:
            print(f"\nFile deletion detected: {event.src_path}")
            self.monitor.send_to_opensearch("file.deleted", event.src_path)
        else:
            print(f"\nFolder deletion detected: {event.src_path}")
            self.monitor.send_to_opensearch("folder.deleted", event.src_path)
            self.monitor.log_folder_deletion(event.src_path)

    def on_created(self, event):
        if (self.monitor.is_system_file(event.src_path) or  # Check system files first
            self.monitor.should_ignore(event.src_path)):
            return
            
        directory = os.path.dirname(event.src_path)
        
        # Check for bulk operation or cooldown
        if self.is_in_bulk_cooldown(directory, "created"):
            return
            
        if self.monitor.is_bulk_operation("created", event.src_path):
            self.monitor.handle_bulk_operation("created", event.src_path)
            self.set_bulk_cooldown(directory, "created")
            return

        # Only send individual event if not in bulk mode
        if not self.monitor.should_ignore(event.src_path):
            print(f"\n{'Folder' if event.is_directory else 'File'} creation detected: {event.src_path}")
            self.monitor.send_to_opensearch(
                "folder.created" if event.is_directory else "file.created", 
                event.src_path
            )

    def on_moved(self, event):
        if self.monitor.should_ignore(event.src_path):
            return
            
        # Always send move events
        print(f"\nFile/folder move detected: {event.src_path} -> {event.dest_path}")
        details = {"source_path": event.src_path}
        self.monitor.send_to_opensearch("file.moved", event.dest_path, details)
        
        if self.monitor.is_sensitive_file(event.dest_path):
            self.monitor.send_to_opensearch("sensitive_file.moved", event.dest_path, details)
            
        self.monitor.log_bulk_operation("moved", event.dest_path)

def main():
    print("\nIntelligent File Activity Monitor\n==========================")
    monitor = UserFileMonitor()
    
    try:
        print("Monitoring started - sending events to OpenSearch")
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping file monitor...")
    except Exception as e:
        print(f"\nError: {str(e)}")

if __name__ == "__main__":
    main()

