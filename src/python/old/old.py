import psutil
import win32evtlog
import win32con
import win32evtlogutil
import win32security
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import json
from pathlib import Path
import logging
import logging.handlers  
from typing import Dict, List, Any
import ctypes
import sys
import hashlib
import winreg
import socket
import win32clipboard
from PIL import ImageGrab
import win32gui
import win32process
import win32api
from threading import Thread
import subprocess
import wmi

class LogManager:
    def __init__(self, base_dir="logs", max_bytes=10*1024*1024, backup_count=5):
        self.base_dir = base_dir
        self.max_bytes = max_bytes  # 10MB default
        self.backup_count = backup_count
        self.ensure_log_directory()
        self.loggers = {}
        
        # Initialize different loggers with their own files
        self.setup_logger("main", "main.log")  # General application logs
        self.setup_logger("process", "monitoring/processes.log")
        self.setup_logger("network", "monitoring/network.log")
        self.setup_logger("filesystem", "monitoring/filesystem.log")
        self.setup_logger("usb", "monitoring/usb_devices.log")
        self.setup_logger("registry", "monitoring/registry.log")
        self.setup_logger("security", "monitoring/security.log")
        self.setup_logger("clipboard", "monitoring/clipboard.log")
        self.setup_logger("screenshot", "monitoring/screenshot.log")

    def ensure_log_directory(self):
        """Create log directories if they don't exist"""
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "monitoring"), exist_ok=True)
        
    def setup_logger(self, name, filename):
        """Setup individual loggers with rotation"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        
        # Remove any existing handlers
        logger.handlers = []
        
        # Create full path for log file
        log_path = os.path.join(self.base_dir, filename)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        # Setup rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        
        # Setup formatter with more detailed information
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        # Add console handler for main logger
        if name == "main":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        logger.addHandler(handler)
        self.loggers[name] = logger

    def log(self, category, message, level=logging.INFO):
        """Log message to specific category"""
        if category in self.loggers:
            self.loggers[category].log(level, message)
        else:
            # Fallback to main logger if category doesn't exist
            self.loggers["main"].log(level, f"[{category}] {message}")

    def get_logger(self, category):
        """Get a specific logger by category"""
        return self.loggers.get(category, self.loggers["main"])

class SystemMonitor:
    def __init__(self):
        self.user_profile = os.path.expanduser('~')
        self.monitored_directories = [
            self.user_profile + '/Downloads',
            self.user_profile + '/Documents',
            self.user_profile + '/Desktop'
        ]
        self.observers: List[Observer] = []
        self.last_login_check = 0
        self.usb_devices_history: Dict[str, Any] = {}
        self.process_history = {}
        self.network_connections = set()
        self.file_hashes = {}
        self.last_process_check = time.time()
        self.last_network_check = time.time()
        self.last_registry_check = time.time()
        self.event_cache = {}  # For deduplication
        self.cache_timeout = 5  # seconds
        
        # Enhanced process monitoring
        self.important_processes = {
            "chrome.exe": "Web Browser",
            "firefox.exe": "Web Browser",
            "edge.exe": "Web Browser",
            "outlook.exe": "Email Client",
            "winword.exe": "Microsoft Word",
            "excel.exe": "Microsoft Excel",
            "powershell.exe": "PowerShell",
            "cmd.exe": "Command Prompt",
            "explorer.exe": "File Explorer"
        }
        
        self.suspicious_processes = [
            "keylogger", "wireshark", "netstat", "portmon",
            "processhacker", "processhacker2", "procmon"
        ]
        
        # Initialize file monitoring cache
        self.file_event_cache = {}
        self.last_file_events = {}
        
        # USB monitoring enhancement
        self.usb_file_operations = {}
        self.known_usb_files = set()
        
        self.log_manager = LogManager()
        
        # Create event deduplication cache
        self.event_dedup_cache = {}
        self.dedup_timeout = 5  # seconds

    def _is_duplicate_event(self, category: str, event_data: str) -> bool:
        """Check if an event is a duplicate within the timeout period"""
        current_time = time.time()
        cache_key = f"{category}:{event_data}"
        
        if cache_key in self.event_dedup_cache:
            last_time = self.event_dedup_cache[cache_key]
            if current_time - last_time < self.dedup_timeout:
                return True
        
        self.event_dedup_cache[cache_key] = current_time
        return False

    def _monitor_processes(self):
        """Enhanced process monitoring with better tracking"""
        while True:
            try:
                current_time = time.time()
                if current_time - self.last_process_check < 1:  # Check every second
                    time.sleep(0.1)
                    continue

                self.last_process_check = current_time
                current_processes = {}
                
                for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline', 'create_time']):
                    try:
                        proc_info = proc.info
                        proc_name = proc_info['name'].lower()
                        
                        # Skip system processes and duplicates
                        if proc_name in ['svchost.exe', 'system', 'registry']:
                            continue
                            
                        # Categorize the process
                        if proc_name in self.important_processes:
                            category = self.important_processes[proc_name]
                            proc_info['category'] = category
                        
                        current_processes[proc.pid] = proc_info
                        
                        # Check for new processes
                        if proc.pid not in self.process_history:
                            proc_info['start_time'] = datetime.fromtimestamp(proc_info['create_time']).isoformat()
                            proc_info['md5_hash'] = self._get_process_hash(proc.pid)
                            
                            # Only log if not a duplicate
                            event_data = f"{proc_name}:{proc.pid}"
                            if not self._is_duplicate_event('process', event_data):
                                self.log_manager.log(
                                    "process",
                                    f"New process started: {proc_name} (PID: {proc.pid})"
                                    f"{f' - {category}' if proc_name in self.important_processes else ''}"
                                )
                            
                            self.process_history[proc.pid] = proc_info
                        
                        # Check for suspicious processes
                        if any(suspicious in proc_name for suspicious in self.suspicious_processes):
                            self.log_manager.log(
                                "security",
                                f"ALERT: Suspicious process detected: {proc_name} (PID: {proc.pid})",
                                logging.WARNING
                            )
                    
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # Check for terminated processes
                for pid in list(self.process_history.keys()):
                    if pid not in current_processes:
                        proc_info = self.process_history[pid]
                        proc_name = proc_info.get('name', 'Unknown')
                        
                        event_data = f"terminated:{proc_name}:{pid}"
                        if not self._is_duplicate_event('process', event_data):
                            self.log_manager.log(
                                "process",
                                f"Process terminated: {proc_name} (PID: {pid})"
                            )
                        
                        del self.process_history[pid]
                
            except Exception as e:
                self.log_manager.log("process", f"Error in process monitoring: {str(e)}", logging.ERROR)
            
            time.sleep(0.1)

    def _check_usb_devices(self):
        """Enhanced USB device monitoring with file tracking"""
        try:
            # Get USB devices using multiple methods for better detection
            current_devices = {}
            
            # Method 1: WMI query for USB devices
            c = wmi.WMI()
            for item in c.Win32_USBHub():
                device_info = {
                    'device_id': item.DeviceID,
                    'description': item.Description,
                    'manufacturer': item.Manufacturer,
                    'name': item.Name,
                    'time_detected': datetime.now().isoformat()
                }
                current_devices[item.DeviceID] = device_info
            
            # Method 2: Check removable drives
            for drive in c.Win32_LogicalDisk(DriveType=2):  # Type 2 is removable disk
                device_info = {
                    'device_id': drive.DeviceID,
                    'volume_name': drive.VolumeName,
                    'size': drive.Size,
                    'free_space': drive.FreeSpace,
                    'time_detected': datetime.now().isoformat()
                }
                
                # Track files on USB device
                try:
                    drive_path = f"{drive.DeviceID}\\"
                    current_files = set()
                    
                    for root, _, files in os.walk(drive_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            current_files.add(file_path)
                            
                            # Check for new files
                            if file_path not in self.known_usb_files:
                                file_info = {
                                    'path': file_path,
                                    'size': os.path.getsize(file_path),
                                    'created': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat(),
                                    'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                                }
                                
                                self.log_manager.log(
                                    "usb",
                                    f"New file detected on USB drive {drive.DeviceID}: {json.dumps(file_info)}"
                                )
                                
                                # Track file operations
                                self.usb_file_operations[file_path] = {
                                    'first_seen': datetime.now().isoformat(),
                                    'operations': []
                                }
                    
                    self.known_usb_files = current_files
                    
                except Exception as e:
                    self.log_manager.log("usb", f"Error scanning USB drive {drive.DeviceID}: {str(e)}", logging.ERROR)
                
                current_devices[drive.DeviceID] = device_info
            
            # Check for new devices
            for device_id, info in current_devices.items():
                if device_id not in self.usb_devices_history:
                    if not self._is_duplicate_event('usb', device_id):
                        self.log_manager.log(
                            "usb",
                            f"New USB device connected: {json.dumps(info)}",
                            logging.WARNING
                        )
                    self.usb_devices_history[device_id] = info
            
            # Check for removed devices
            for device_id in list(self.usb_devices_history.keys()):
                if device_id not in current_devices:
                    if not self._is_duplicate_event('usb', f"removed:{device_id}"):
                        self.log_manager.log(
                            "usb",
                            f"USB device removed: {json.dumps(self.usb_devices_history[device_id])}",
                            logging.WARNING
                        )
                    del self.usb_devices_history[device_id]
            
        except Exception as e:
            self.log_manager.log("usb", f"Error in USB monitoring: {str(e)}", logging.ERROR)

    def _on_file_event(self, event):
        """Enhanced file system event handling"""
        try:
            event_type = event.event_type
            path = event.src_path
            
            # Skip temporary files and system files
            if any(skip in path.lower() for skip in ['.tmp', '.temp', '~', '$recycle.bin']):
                return
                
            # Calculate file hash for modified files
            file_hash = None
            if event_type in ['created', 'modified'] and os.path.isfile(path):
                try:
                    with open(path, 'rb') as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()
                except:
                    pass
            
            event_data = {
                'type': event_type,
                'path': path,
                'timestamp': datetime.now().isoformat(),
                'user': os.getlogin(),
                'hash': file_hash
            }
            
            # Check if this is a duplicate event
            cache_key = f"{path}:{event_type}"
            current_time = time.time()
            
            if cache_key in self.file_event_cache:
                last_time = self.file_event_cache[cache_key]
                if current_time - last_time < self.cache_timeout:
                    return
            
            self.file_event_cache[cache_key] = current_time
            
            # Check if file is from USB device
            for device_id in self.usb_devices_history:
                if device_id in path:
                    event_data['usb_source'] = device_id
                    self.usb_file_operations.setdefault(path, {
                        'first_seen': datetime.now().isoformat(),
                        'operations': []
                    })['operations'].append({
                        'type': event_type,
                        'timestamp': datetime.now().isoformat()
                    })
            
            self.log_manager.log(
                "filesystem",
                f"File event: {json.dumps(event_data)}"
            )
            
        except Exception as e:
            self.log_manager.log("filesystem", f"Error processing file event: {str(e)}", logging.ERROR)

    def _monitor_network(self):
        """Enhanced network monitoring"""
        while True:
            try:
                current_time = time.time()
                if current_time - self.last_network_check < 1:  # Check every second
                    time.sleep(0.1)
                    continue
                    
                self.last_network_check = current_time
                current_connections = set()
                
                for conn in psutil.net_connections(kind='inet'):
                    if conn.status == 'ESTABLISHED':
                        try:
                            process = psutil.Process(conn.pid)
                            process_name = process.name()
                            
                            connection_info = {
                                'process': process_name,
                                'pid': conn.pid,
                                'local_ip': conn.laddr.ip,
                                'local_port': conn.laddr.port,
                                'remote_ip': conn.raddr.ip if conn.raddr else None,
                                'remote_port': conn.raddr.port if conn.raddr else None,
                                'status': conn.status
                            }
                            
                            conn_str = json.dumps(connection_info)
                            current_connections.add(conn_str)
                            
                            if conn_str not in self.network_connections:
                                if not self._is_duplicate_event('network', conn_str):
                                    self.log_manager.log(
                                        "network",
                                        f"New network connection: {conn_str}"
                                    )
                            
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                
                # Check for closed connections
                for conn_str in self.network_connections - current_connections:
                    if not self._is_duplicate_event('network', f"closed:{conn_str}"):
                        self.log_manager.log(
                            "network",
                            f"Connection closed: {conn_str}"
                        )
                
                self.network_connections = current_connections
                
            except Exception as e:
                self.log_manager.log("network", f"Error in network monitoring: {str(e)}", logging.ERROR)
            
            time.sleep(0.1)

    def start_monitoring(self):
        """Start all monitoring systems with better thread management"""
        try:
            # Start file system monitoring
            self._start_file_monitoring()
            
            # Start monitoring threads
            threads = [
                Thread(target=self._monitor_processes, daemon=True),
                Thread(target=self._monitor_network, daemon=True),
                Thread(target=self._monitor_registry, daemon=True),
                Thread(target=self._monitor_clipboard, daemon=True)
            ]
            
            for thread in threads:
                thread.start()
            
            # Start continuous monitoring loop with better timing
            while True:
                self._check_login_events()
                self._check_usb_devices()
                self._check_for_keyloggers()
                
                # Clean up old cache entries
                current_time = time.time()
                self.event_dedup_cache = {
                    k: v for k, v in self.event_dedup_cache.items()
                    if current_time - v < self.dedup_timeout
                }
                
                time.sleep(1)
                
        except Exception as e:
            self.log_manager.log("main", f"Error in monitoring: {str(e)}", logging.ERROR)
            raise

    def _start_file_monitoring(self):
        """Initialize file system monitoring"""
        event_handler = FileSystemEventHandler()
        event_handler.on_any_event = self._on_file_event

        for directory in self.monitored_directories:
            if os.path.exists(directory):
                observer = Observer()
                observer.schedule(event_handler, directory, recursive=True)
                observer.start()
                self.observers.append(observer)
                self.log_manager.log("main", f"Started monitoring directory: {directory}")

    def _check_login_events(self):
        """Monitor Windows login events"""
        hand = None
        try:
            server = 'localhost'
            logtype = 'Security'
            hand = win32evtlog.OpenEventLog(server, logtype)
            if not hand:
                self.log_manager.log("main", "Failed to open Security event log")
                return

            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            
            events = win32evtlog.ReadEventLog(
                hand,
                flags,
                0
            )

            for event in events:
                if event.EventID == 4624:  # Successful login
                    self._process_login_event(event)
                elif event.EventID == 4625:  # Failed login
                    self._process_failed_login(event)

        except Exception as e:
            self.log_manager.log("main", f"Error checking login events: {str(e)}", logging.ERROR)
        finally:
            if hand:
                try:
                    win32evtlog.CloseEventLog(hand)
                except Exception as e:
                    self.log_manager.log("main", f"Error closing event log: {str(e)}", logging.ERROR)

    def _process_login_event(self, event):
        """Process successful login events"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'type': 'successful_login',
                'user': os.getlogin(),
                'event_id': event.EventID
            }
            self.log_manager.log("security", f"Login event: {json.dumps(data)}")
            # Here you would send this data to your central server
            
        except Exception as e:
            self.log_manager.log("security", f"Error processing login event: {str(e)}", logging.ERROR)

    def _process_failed_login(self, event):
        """Process failed login attempts"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'type': 'failed_login',
                'event_id': event.EventID
            }
            self.log_manager.log("security", f"Failed login attempt: {json.dumps(data)}")
            # Here you would send this data to your central server
            
        except Exception as e:
            self.log_manager.log("security", f"Error processing failed login: {str(e)}", logging.ERROR)

    def _log_usb_event(self, action: str, device: str, info: Dict):
        """Log USB device events"""
        try:
            event_data = {
                'action': action,
                'device': device,
                'info': info,
                'timestamp': datetime.now().isoformat(),
                'user': os.getlogin()
            }
            self.log_manager.log("usb", f"USB event: {json.dumps(event_data)}")
            
        except Exception as e:
            self.log_manager.log("usb", f"Error: {str(e)}", logging.ERROR)

    def stop_monitoring(self):
        """Stop all monitoring systems"""
        for observer in self.observers:
            observer.stop()
        for observer in self.observers:
            observer.join()
        self.log_manager.log("main", "Stopped all monitoring systems")

    def _monitor_registry(self):
        """Monitor registry changes"""
        key_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
            r"SYSTEM\CurrentControlSet\Services"
        ]
        
        while True:
            try:
                for path in key_paths:
                    self._check_registry_changes(winreg.HKEY_LOCAL_MACHINE, path)
                    self._check_registry_changes(winreg.HKEY_CURRENT_USER, path)
            except Exception as e:
                self.log_manager.log("registry", f"Error: {str(e)}", logging.ERROR)
            time.sleep(5)

    def _monitor_clipboard(self):
        """Monitor clipboard changes"""
        last_value = ""
        while True:
            try:
                win32clipboard.OpenClipboard()
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                    value = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                    if value != last_value:
                        self.clipboard_history.append({
                            'content': value,
                            'timestamp': datetime.now().isoformat()
                        })
                        last_value = value
                        self.log_manager.log("clipboard", f"Clipboard content: {value}")
                win32clipboard.CloseClipboard()
            except Exception as e:
                self.log_manager.log("clipboard", f"Error: {str(e)}", logging.ERROR)
            time.sleep(1)

    def _take_periodic_screenshot(self):
        """Take periodic screenshots"""
        current_time = time.time()
        if current_time - self.last_screenshot >= self.screenshot_interval:
            try:
                screenshot = ImageGrab.grab()
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot.save(filename)
                self.log_manager.log("screenshot", f"Screenshot saved: {filename}")
                self.last_screenshot = current_time
            except Exception as e:
                self.log_manager.log("screenshot", f"Error taking screenshot: {str(e)}", logging.ERROR)

    def _check_for_keyloggers(self):
        """Check for potential keylogger processes"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                process_name = proc.info['name'].lower()
                if any(suspicious in process_name for suspicious in self.suspicious_processes):
                    self.log_manager.log("security", f"Potential keylogger detected: {proc.info}", logging.WARNING)
        except Exception as e:
            self.log_manager.log("security", f"Error checking for keyloggers: {str(e)}", logging.ERROR)

    def _get_process_hash(self, pid):
        """Get MD5 hash of process executable"""
        try:
            process = psutil.Process(pid)
            path = process.exe()
            if path:
                with open(path, 'rb') as f:
                    return hashlib.md5(f.read()).hexdigest()
        except:
            return None

    def _get_usb_devices(self):
        """Get detailed USB device information"""
        devices = []
        try:
            cmd = 'powershell "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -match \'USB\' } | Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True)
            devices = json.loads(output)
        except Exception as e:
            self.log_manager.log("usb", f"Error getting USB devices: {str(e)}", logging.ERROR)
        return devices

    def _is_suspicious_usb(self, device_info):
        """Check if USB device is potentially malicious"""
        suspicious_indicators = [
            "rubber ducky",
            "bash bunny",
            "usb killer"
        ]
        device_string = json.dumps(device_info).lower()
        return any(indicator in device_string for indicator in suspicious_indicators)

    def _check_registry_changes(self, hive, key_path):
        """Monitor specific registry key for changes"""
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            num_values = winreg.QueryInfoKey(key)[1]
            
            for i in range(num_values):
                name, value, _ = winreg.EnumValue(key, i)
                self.log_manager.log("registry", f"Registry value: {key_path}\\{name} = {value}")
        except Exception as e:
            self.log_manager.log("registry", f"Error: {str(e)}", logging.ERROR)

def is_admin():
    """Check if the script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with admin privileges"""
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        " ".join(sys.argv),
        None,
        1
    )

if __name__ == "__main__":
    # Temporarily disabled admin check
    if not is_admin():
        print("Script must run with administrative privileges. Requesting elevation...")
        run_as_admin()
        sys.exit()

    monitor = SystemMonitor()
    try:
        monitor.start_monitoring()
    except KeyboardInterrupt:
        monitor.stop_monitoring()
