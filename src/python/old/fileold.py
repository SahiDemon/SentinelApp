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
from datetime import datetime

# Add OpenSearch configuration
OPENSEARCH_URL = "https://localhost:9200/file_monitor/_doc"
AUTH = ("admin", "Sahi_448866")
HEADERS = {"Content-Type": "application/json"}

# Disable SSL warnings for self-signed certs
urllib3.disable_warnings()

def setup_logger(name, log_dir="logs"):
    # Make log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger with DEBUG level
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Changed from INFO to DEBUG
    
    # Ensure logger doesn't have existing handlers
    logger.handlers = []
    
    # Create file handler with DEBUG level
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Create console handler with INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')
    
    # Add formatter to handlers
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Test logging
    logger.info(f"Logger initialized. Log file: {log_file}")
    return logger

def is_admin():
    """Check if the program is running with admin rights"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class UserFileMonitor:
    def __init__(self, log_dir="logs"):
        self.logger = setup_logger('user_file_monitor', log_dir)
        
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

        # Initialize OpenSearch session
        self.session = requests.Session()
        self.session.verify = False  # Skip SSL verification
        self.session.auth = AUTH
        self.session.headers.update(HEADERS)
        
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

    def should_ignore(self, path):
        """Enhanced path filtering"""
        try:
            # Ignore system and temp paths
            if any(keyword in path.lower() for keyword in [
                'cache', 'temp', 'tmp', 'log', 
                'appdata', 'windows', 'program files',
                '.git', '.vs', '__pycache__', 'node_modules'
            ]):
                return True
                
            # Ignore temporary files
            if path.endswith('.tmp') or path.endswith('.temp'):
                return True
                
            # Ignore cache directories
            if 'cache' in path.lower() or '.git' in path:
                return True
                
            # Check recycle bin patterns
            if any(re.search(pattern, path, re.IGNORECASE) for pattern in self.ignore_patterns):
                return True
                
            # Check standard ignore paths
            if any(path.startswith(ignore) for ignore in self.ignore_paths):
                return True
                
            return False
        except:
            return True

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
        """Send event to OpenSearch"""
        try:
            event_data = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "file_path": file_path,
                "file_name": os.path.basename(file_path),
                "directory": os.path.dirname(file_path),
                "details": details or {},
                "host": os.environ.get('COMPUTERNAME', 'unknown')
            }
            
            response = self.session.post(OPENSEARCH_URL, json=event_data)
            if response.status_code not in (200, 201):
                self.logger.error(f"Failed to send to OpenSearch: {response.text}")
                
        except Exception as e:
            self.logger.error(f"Error sending to OpenSearch: {str(e)}")

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
        """Start monitoring the file system with fallback"""
        self.logger.info("Starting file monitoring...")
        
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

class UserFileHandler(FileSystemEventHandler):
    def __init__(self, monitor):
        self.monitor = monitor

    def on_modified(self, event):
        if event.is_directory or self.monitor.should_ignore(event.src_path):
            return
            
        self.monitor.logger.debug(f"File modified: {event.src_path}")
            
        if (self.monitor.is_sensitive_file(event.src_path) and 
            self.monitor.is_real_change(event.src_path) and
            self.monitor.should_alert(event.src_path, "modified")):
            self.monitor.logger.warning(
                f"Sensitive file modified: {event.src_path}"
            )
            self.monitor.send_to_opensearch("sensitive_file_modified", event.src_path)
            print(f"ALERT: Sensitive file modified: {event.src_path}")  # Immediate console output
            
        self.monitor.log_bulk_operation("modified", event.src_path)

    def on_deleted(self, event):
        if self.monitor.should_ignore(event.src_path):
            return
            
        # Log individual file deletion
        if not event.is_directory:
            self.monitor.logger.info(f"File deleted: {event.src_path}")
            
        if (event.is_directory and 
            not self.monitor.should_ignore(event.src_path) and
            self.monitor.should_alert(event.src_path, "deleted")):
            self.monitor.log_folder_deletion(event.src_path)
            self.monitor.send_to_opensearch("folder_deleted", event.src_path)
        elif self.monitor.is_sensitive_file(event.src_path):
            self.monitor.logger.warning(f"Sensitive file deleted: {event.src_path}")
            self.monitor.send_to_opensearch("sensitive_file_deleted", event.src_path)

        # Log bulk operation
        self.monitor.log_bulk_operation("deleted", event.src_path)
        self.monitor.clean_deleted_folders()

    def on_created(self, event):
        if self.monitor.should_ignore(event.src_path):
            return
            
        # Log individual file creation    
        if not event.is_directory:
            self.monitor.logger.info(f"File created: {event.src_path}")
            
        if self.monitor.is_sensitive_file(event.src_path):
            self.monitor.logger.warning(f"New sensitive file created: {event.src_path}")
            self.monitor.send_to_opensearch("sensitive_file_created", event.src_path)
            
        self.monitor.log_bulk_operation("created", event.src_path)

    def on_moved(self, event):
        if self.monitor.should_ignore(event.src_path):
            return
            
        if self.monitor.is_sensitive_file(event.dest_path):
            self.monitor.logger.warning(
                f"Sensitive file moved: {event.src_path} -> {event.dest_path}"
            )
            details = {"source_path": event.src_path}
            self.monitor.send_to_opensearch("sensitive_file_moved", event.dest_path, details)
            
        self.monitor.log_bulk_operation("moved", event.dest_path)

def main():
    print("\nIntelligent File Activity Monitor\n==========================")
    
    # Create monitor with explicit log directory
    monitor = UserFileMonitor(log_dir="file_monitor_logs")
    
    try:
        # Test logging before starting
        monitor.logger.info("Starting monitoring system...")
        print("Monitoring started - check file_monitor_logs directory for detailed logs")
        
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping file monitor...")
    except Exception as e:
        print(f"\nError: {str(e)}")
        monitor.logger.error(f"Fatal error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
