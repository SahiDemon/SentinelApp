import os
import time
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import re
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timedelta
import psutil
import shutil
import logging

def setup_logger(name, log_dir="logs"):
    """Set up a logger instance"""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    file_handler = logging.FileHandler(os.path.join(log_dir, f"{name}.log"))
    console_handler = logging.StreamHandler()
    
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class FileSystemMonitor:
    def __init__(self, log_dir="logs", monitored_paths=None, sensitive_patterns=None):
        """Initialize file system monitor"""
        self.logger = setup_logger('filesystem_monitor', log_dir)
        
        # Default monitored paths if none provided
        if monitored_paths is None:
            monitored_paths = [
                os.path.expanduser("~"),  # User's home directory
                os.path.join(os.path.expanduser("~"), "Desktop"),
                os.path.join(os.path.expanduser("~"), "Documents"),
                os.path.join(os.path.expanduser("~"), "Downloads"),
                # os.environ.get('PROGRAMDATA', r'C:\ProgramData'),  # Program Data
                # os.environ.get('APPDATA', ''),  # AppData Roaming
                # os.environ.get('LOCALAPPDATA', ''),  # AppData Local
                # r'C:\Program Files',
                # r'C:\Program Files (x86)'
            ]
            # Filter out empty or non-existent paths
            monitored_paths = [p for p in monitored_paths if p and os.path.exists(p)]
        
        self.monitored_paths = monitored_paths
        self.sensitive_patterns = sensitive_patterns or [
            r"\.env$",
            r"\.config$",
            r"password",
            r"\.key$",
            r"\.pem$"
        ]
        self.file_hashes = {}
        self.temp_patterns = [
            r"\.tmp$",
            r"\.temp$",
            r"~\$",
            r"\.bak$",
            r"\.swp$",
            r"Temp",
            r"Cache"
        ]
        
        # Size thresholds (in bytes)
        self.large_file_threshold = 100 * 1024 * 1024  # 100MB
        self.huge_file_threshold = 1024 * 1024 * 1024  # 1GB
        
        # Event tracking
        self.event_history = defaultdict(lambda: deque(maxlen=100))  # Last 100 events per directory
        self.rate_limits = {
            'created': 50,    # Max files per minute
            'modified': 100,  # Max modifications per minute
            'deleted': 30     # Max deletions per minute
        }
        
        # Directory size tracking
        self.dir_sizes = {}
        self.last_dir_scan = {}
        self.dir_scan_interval = 300  # 5 minutes
        
        # Mass operation detection
        self.operation_window = 60  # 1 minute window
        self.mass_operations = defaultdict(lambda: {
            'timestamps': deque(maxlen=1000),
            'paths': set()
        })

    def _is_temp_file(self, path):
        """Check if file is temporary"""
        return any(re.search(pattern, path, re.IGNORECASE) 
                  for pattern in self.temp_patterns)

    def _is_sensitive_file(self, path):
        """Check if file is sensitive"""
        return any(re.search(pattern, path, re.IGNORECASE) 
                  for pattern in self.sensitive_patterns)

    def _calculate_file_hash(self, filepath):
        """Calculate SHA-256 hash of file"""
        try:
            if os.path.isfile(filepath):
                sha256_hash = hashlib.sha256()
                with open(filepath, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating hash for {filepath}: {str(e)}")
        return None

    def _get_directory_size(self, path):
        """Calculate total size of a directory"""
        try:
            total = 0
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        total += self._get_directory_size(entry.path)
            return total
        except Exception:
            return 0

    def _check_directory_changes(self, path):
        """Monitor directory for significant changes"""
        current_time = time.time()
        if path not in self.last_dir_scan or \
           current_time - self.last_dir_scan[path] >= self.dir_scan_interval:
            
            current_size = self._get_directory_size(path)
            if path in self.dir_sizes:
                size_diff = current_size - self.dir_sizes[path]
                if abs(size_diff) > self.large_file_threshold:
                    self.logger.warning(
                        f"Large directory change detected in {path}: "
                        f"{self._format_size(abs(size_diff))} "
                        f"{'increased' if size_diff > 0 else 'decreased'}"
                    )
            
            self.dir_sizes[path] = current_size
            self.last_dir_scan[path] = current_time

    def _detect_mass_operations(self, event_type, path):
        """Detect mass file operations"""
        current_time = time.time()
        operation = self.mass_operations[event_type]
        
        # Remove old timestamps
        while operation['timestamps'] and \
              current_time - operation['timestamps'][0] > self.operation_window:
            operation['timestamps'].popleft()
        
        operation['timestamps'].append(current_time)
        operation['paths'].add(os.path.dirname(path))
        
        # Check for mass operations
        if len(operation['timestamps']) >= self.rate_limits[event_type]:
            self.logger.warning(
                f"Mass {event_type} operation detected! "
                f"{len(operation['timestamps'])} files in the last minute. "
                f"Affected directories: {', '.join(operation['paths'])}"
            )
            # Reset tracking
            operation['timestamps'].clear()
            operation['paths'].clear()

    def _format_size(self, size):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def _check_file_size(self, path):
        """Check and log large file operations"""
        try:
            size = os.path.getsize(path)
            if size >= self.huge_file_threshold:
                self.logger.warning(
                    f"Huge file detected: {path} "
                    f"Size: {self._format_size(size)}"
                )
            elif size >= self.large_file_threshold:
                self.logger.info(
                    f"Large file detected: {path} "
                    f"Size: {self._format_size(size)}"
                )
            return size
        except Exception:
            return 0

    def monitor(self):
        """Start monitoring file system events"""
        self.logger.info("Starting file system monitoring...")
        self.logger.info("Monitored directories:")
        for path in self.monitored_paths:
            self.logger.info(f"- {path}")
        
        # Create observer and handler
        event_handler = FileHandler(self)
        observer = Observer()
        
        # Add watchers for all monitored paths
        monitored_count = 0
        for path in self.monitored_paths:
            if os.path.exists(path):
                observer.schedule(event_handler, path, recursive=True)
                monitored_count += 1
            else:
                self.logger.warning(f"Path does not exist: {path}")
        
        if monitored_count == 0:
            self.logger.error("No valid paths to monitor!")
            return
        
        # Start monitoring
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            self.logger.info("File system monitoring stopped")
        observer.join()

class FileHandler(FileSystemEventHandler):
    def __init__(self, monitor):
        self.monitor = monitor

    def on_created(self, event):
        if event.is_directory or self.monitor._is_temp_file(event.src_path):
            return
        
        size = self.monitor._check_file_size(event.src_path)
        msg = f"File created: {event.src_path} ({self.monitor._format_size(size)})"
        
        if self.monitor._is_sensitive_file(event.src_path):
            self.monitor.logger.warning(f"SENSITIVE {msg}")
        else:
            self.monitor.logger.info(msg)
            
        # Calculate and store initial hash
        file_hash = self.monitor._calculate_file_hash(event.src_path)
        if file_hash:
            self.monitor.file_hashes[event.src_path] = file_hash

        self.monitor._detect_mass_operations('created', event.src_path)
        self.monitor._check_directory_changes(os.path.dirname(event.src_path))

    def on_modified(self, event):
        if event.is_directory or self.monitor._is_temp_file(event.src_path):
            return
            
        if event.src_path in self.monitor.file_hashes:
            new_hash = self.monitor._calculate_file_hash(event.src_path)
            if new_hash and new_hash != self.monitor.file_hashes[event.src_path]:
                msg = f"File modified: {event.src_path}"
                if self.monitor._is_sensitive_file(event.src_path):
                    self.monitor.logger.warning(f"SENSITIVE {msg}")
                else:
                    self.monitor.logger.info(msg)
                self.monitor.file_hashes[event.src_path] = new_hash

    def on_deleted(self, event):
        if event.is_directory or self.monitor._is_temp_file(event.src_path):
            return
            
        msg = f"File deleted: {event.src_path}"
        if self.monitor._is_sensitive_file(event.src_path):
            self.monitor.logger.warning(f"SENSITIVE {msg}")
        else:
            self.monitor.logger.info(msg)
            
        # Remove hash if exists
        self.monitor.file_hashes.pop(event.src_path, None)

    def on_moved(self, event):
        if event.is_directory or self.monitor._is_temp_file(event.src_path):
            return
            
        msg = f"File moved/renamed: from {event.src_path} to {event.dest_path}"
        if (self.monitor._is_sensitive_file(event.src_path) or 
            self.monitor._is_sensitive_file(event.dest_path)):
            self.monitor.logger.warning(f"SENSITIVE {msg}")
        else:
            self.monitor.logger.info(msg)
            
        # Update hash dictionary
        if event.src_path in self.monitor.file_hashes:
            self.monitor.file_hashes[event.dest_path] = self.monitor.file_hashes.pop(event.src_path)

def main():
    """Main function"""
    print("\nFile System Monitor")
    print("==================")
    print("Monitoring:")
    print("- File creation/deletion/modification")
    print("- File moves and renames")
    print("- Large file operations")
    print("- Sensitive file access")
    print("- Mass file operations")
    print("==================\n")
    
    monitor = FileSystemMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping filesystem monitor...")

if __name__ == "__main__":
    main()