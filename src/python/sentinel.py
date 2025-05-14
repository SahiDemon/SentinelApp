import os
import logging
import threading
import sys
import time
import argparse
import signal
import psutil
import re
import ctypes
import json

# Add parent directory to path to fix imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# When running as module (-m), imports need to be absolute from inside the module
from src.python.opensearch_logger import OpenSearchLogger
from src.python.login_monitor import LoginMonitor
from src.python.process_monitor import ProcessMonitor
from src.python.network_monitor import NetworkMonitor
from src.python.filesystem_monitor import UserFileMonitor as FileSystemMonitor
from src.python.system_monitor import SystemMonitor
from src.python.browser_monitor import BrowserMonitor
from src.python.usb_monitor import USBMonitor
from src.python.user_identity import user_identity

# Global instance for signal handling
_sentinel_instance = None

# Function to check if actually running with admin privileges (Windows)
def is_admin():
    try:
        if os.name == 'nt':  # Windows
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:  # Unix-like
            return os.geteuid() == 0  # Root has UID 0
    except:
        return False

class SentinelMonitor:
    def __init__(self, user_id, is_admin_flag, log_dir="logs"):
        """Initialize the sentinel monitoring system"""
        # Double-check actual admin privileges
        actual_admin = is_admin()
        if is_admin_flag and not actual_admin:
            print(f"WARNING: Admin flag is set but process is NOT running with admin privileges. Some monitors will be limited.", 
                  file=sys.stderr, flush=True)
            # Override to match reality
            is_admin_flag = False
            
        print(f"Initializing SentinelMonitor for user: {user_id}, Admin flag: {is_admin_flag}, Actual admin: {actual_admin}")
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        self.user_id = user_id
        self.is_admin = is_admin_flag # Set based on command-line arg and reality check
        self.start_time = time.time()
        
        # Setup sentinel logger
        self.logger = logging.getLogger('sentinel')
        self.logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(os.path.join(log_dir, "sentinel.log"))
        # Log to console/stderr as well for debugging, but use print for Electron comms
        console_handler = logging.StreamHandler(sys.stderr) 
        console_handler.setLevel(logging.WARNING) # Only show warnings/errors on console log
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                   datefmt='%Y-%m-%d %H:%M:%S')
        
        handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.addHandler(console_handler)
        
        # Initialize user identity
        self._initialize_user_identity(user_id)
        
        self.logger.info(f"Sentinel starting. User ID: {self.user_id}, Admin privileges: {self.is_admin}")
        print(f"Sentinel starting for user {self.user_id}. Admin: {self.is_admin}", flush=True) # Info to stdout
            
        # Store configurations, defer instantiation for admin-required monitors
        self.monitors_config = {
            'Login': {'class': LoginMonitor, 'requires_admin': True, 'instance': None, 'status': False},
            'Process': {'class': ProcessMonitor, 'requires_admin': False, 'instance': None, 'status': False},
            'Network': {'class': NetworkMonitor, 'requires_admin': True, 'instance': None, 'status': False},
            'Filesystem': {'class': FileSystemMonitor, 'requires_admin': False, 'instance': None, 'status': False},
            'System': {'class': SystemMonitor, 'requires_admin': True, 'instance': None, 'status': False},
            'Browser': {'class': BrowserMonitor, 'requires_admin': True, 'instance': None, 'status': False},
            'USB': {'class': USBMonitor, 'requires_admin': True, 'instance': None, 'status': False}
        }
        
        # Create OpenSearch logger with user identity
        self.opensearch_logger = OpenSearchLogger(electron_user_id=self.user_id)
        
        # Log session start
        self._log_session_start()
        
        # Instantiate non-admin monitors immediately
        for name, config in self.monitors_config.items():
            if not config['requires_admin']:
                try:
                    self.logger.info(f"Instantiating non-admin monitor: {name}")
                    config['instance'] = config['class'](electron_user_id=self.user_id)
                except Exception as e:
                    self.logger.error(f"Error instantiating {name} monitor in __init__: {e}", exc_info=True)
                    config['status'] = False # Mark as failed
        
        self.threads = {}
        self.stopping = False
    
    def _initialize_user_identity(self, user_id: str):
        """Initialize the user identity for consistent identification"""
        # Get device information for correlation
        device_info = self._get_device_info()
        
        # Set the user in the user identity module
        user_identity.set_user(user_id)
        
        # Start a new session
        session_id = user_identity.start_session()
        
        # Log this information
        self.logger.info(f"User identity initialized: User ID: {user_id}, Session: {session_id}")
        
        # We'll register this auth event in OpenSearch after logger is initialized
    
    def _get_device_info(self):
        """Get device information for identity correlation"""
        try:
            device_info = {
                "os": sys.platform,
                "hostname": os.environ.get("COMPUTERNAME", "unknown") if sys.platform == "win32" else os.uname().nodename,
                "username": os.environ.get("USERNAME", "unknown") if sys.platform == "win32" else os.environ.get("USER", "unknown"),
                "cpu_cores": psutil.cpu_count(),
                "memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "sentinel_start_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time))
            }
            return device_info
        except Exception as e:
            self.logger.error(f"Error getting device info: {e}")
            return {"error": str(e)}
    
    def _log_session_start(self):
        """Log session start event to OpenSearch"""
        try:
            # Get device info for the session
            device_info = self._get_device_info()
            
            # Log session start event
            self.opensearch_logger.log(
                monitor_type="sentinel",
                event_type="session_start",
                event_details={
                    "user_id": self.user_id,
                    "session_id": user_identity.session_id,
                    "correlation_id": user_identity.correlation_id,
                    "device_info": device_info,
                    "admin_privileges": self.is_admin
                }
            )
            
            # Register this authentication event
            self.logger.info("Registering new session in user registry")
            
            # We need to communicate with main process to call the JS API
            print(json.dumps({
                "type": "session_start",
                "data": {
                    "user_id": self.user_id,
                    "session_id": user_identity.session_id,
                    "correlation_id": user_identity.correlation_id,
                    "device_info": device_info
                }
            }), flush=True)
            
        except Exception as e:
            self.logger.error(f"Error logging session start: {e}")

    def _run_monitor(self, name):
        """Instantiate (if needed) and run a monitor in a loop"""
        monitor_info = self.monitors_config[name]
        monitor_class = monitor_info['class']
        requires_admin = monitor_info['requires_admin']
        monitor_instance = monitor_info.get('instance')

        # Skip if admin required but not available
        if requires_admin and not self.is_admin:
            self.logger.warning(f"Skipping {name} monitor: requires admin privileges which are not available.")
            print(f"WARNING: Skipping {name} monitor (requires admin)", file=sys.stderr, flush=True)
            self.monitors_config[name]['status'] = False
            return

        # Instantiate if not already done (primarily for admin-required monitors)
        if monitor_instance is None:
            try:
                self.logger.info(f"Instantiating monitor: {name} (Requires Admin: {requires_admin}) ...")
                monitor_instance = monitor_class(electron_user_id=self.user_id)
                self.monitors_config[name]['instance'] = monitor_instance # Store the created instance
            except PermissionError as pe:
                 err_msg = f"PermissionError during instantiation of {name} monitor: {str(pe)}"
                 self.logger.error(err_msg)
                 print(f"ERROR: {err_msg}", file=sys.stderr, flush=True)
                 self.monitors_config[name]['status'] = False
                 return # Stop this thread
            except Exception as e:
                 err_msg = f"Error instantiating {name} monitor: {str(e)}"
                 self.logger.error(err_msg, exc_info=True)
                 print(f"ERROR: {err_msg}", file=sys.stderr, flush=True)
                 self.monitors_config[name]['status'] = False
                 return # Stop this thread
        
        # Check again if instance creation failed silently
        if monitor_instance is None: 
             self.logger.error(f"Cannot start {name} monitor: Instance is None after instantiation attempt.")
             self.monitors_config[name]['status'] = False
             return

        # Run the monitor's main loop
        try:
            log_msg = f"Starting {name} monitor execution..."
            self.logger.info(log_msg)
            print(log_msg, flush=True)
            self.monitors_config[name]['status'] = True
            monitor_instance.monitor()
        except PermissionError as pe:
            err_msg = f"PermissionError during {name}.monitor() run: {str(pe)}"
            self.logger.error(err_msg)
            print(f"ERROR: {err_msg}", file=sys.stderr, flush=True)
            self.monitors_config[name]['status'] = False
        except Exception as e:
            err_msg = f"Error during {name}.monitor() run: {str(e)}"
            self.logger.error(err_msg, exc_info=True)
            print(f"ERROR: {err_msg}", file=sys.stderr, flush=True)
            self.monitors_config[name]['status'] = False
        finally:
            # Log when the monitor loop finishes or crashes
            final_status = self.monitors_config[name]['status']
            log_msg_end = f"{name} monitor loop ended."
            self.logger.info(log_msg_end)
            print(log_msg_end, flush=True)
            # Ensure status reflects that the loop is no longer active
            self.monitors_config[name]['status'] = False

    def _check_monitor_status(self):
        """Log the status of all monitors based on thread and config status"""
        while not self.stopping:
            status_parts = []
            active_thread_count = 0
            for name, config in self.monitors_config.items():
                thread = self.threads.get(name)
                is_alive = thread and thread.is_alive()
                
                current_monitor_status = "Unknown"
                if config['requires_admin'] and not self.is_admin:
                    current_monitor_status = "Skipped (Admin Required)"
                elif is_alive:
                    current_monitor_status = "Running"
                    active_thread_count += 1
                elif config.get('instance') is None and not config['requires_admin']: 
                     # Non-admin monitor failed instantiation in __init__
                     current_monitor_status = "Failed to Init"
                elif not is_alive:
                    # Thread is dead or never started properly
                    current_monitor_status = "Stopped / Error"
                    
                status_parts.append(f"{name}: {current_monitor_status}")
            
            self.logger.info("Monitor Status Check | " + " | ".join(status_parts))
            
            if self.stopping: break
            time.sleep(60) 

    def start(self):
        """Start all monitoring components"""
        self.logger.info("Attempting to start Sentinel monitoring threads...")
        
        # Start status monitoring thread
        status_thread = threading.Thread(
            target=self._check_monitor_status,
            name="StatusMonitor"
        )
        status_thread.daemon = True # Ensure it exits with main thread
        status_thread.start()
        
        # Start individual monitor threads
        monitors_to_start = []
        for name, config in self.monitors_config.items():
            if config['requires_admin'] and not self.is_admin:
                self.logger.info(f"Will skip starting thread for {name} (Admin Required).")
                continue # Don't create a thread if it will be skipped anyway
            monitors_to_start.append(name)
            
        for name in monitors_to_start:
            thread = threading.Thread(
                target=self._run_monitor,
                args=(name,),
                name=f"{name}Monitor"
            )
            thread.daemon = True # Ensure child threads exit if main script crashes
            self.threads[name] = thread
            self.logger.info(f"Starting thread for {name} monitor...")
            thread.start()
            time.sleep(0.2) # Small delay between starts
        
        self.logger.info(f"{len(monitors_to_start)} monitor threads initiated.")
        
        # Give monitors a moment to initialize or fail
        time.sleep(2.0)
        
        # Check initial status after allowing some startup time
        initial_running_count = sum(1 for name, t in self.threads.items() if t.is_alive())
        self.logger.info(f"Initial check: {initial_running_count} monitor threads are alive.")

        # Send READY signal regardless of how many started, Electron handles status display
        print("SENTINEL_READY", flush=True)
        self.logger.info("SENTINEL_READY signal sent.")

        # Main loop to keep the script alive
        try:
            while not self.stopping:
                alive_count = 0
                should_be_running_count = 0
                for name, thread in self.threads.items():
                     config = self.monitors_config[name]
                     should_run = not (config['requires_admin'] and not self.is_admin)
                     if should_run:
                          should_be_running_count += 1
                     if thread.is_alive():
                          alive_count += 1
                     elif config['status']: 
                          # Was running but thread died
                          self.logger.warning(f"Monitor thread {name} appears to have stopped unexpectedly.")
                          self.monitors_config[name]['status'] = False # Mark as stopped

                if should_be_running_count > 0 and alive_count == 0:
                    self.logger.error("All active monitor threads have stopped. Exiting.")
                    print("ERROR: All active monitors stopped.", file=sys.stderr, flush=True)
                    self.stopping = True
                    break
                    
                time.sleep(5)
                
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received.")
            self.stop(signal.SIGINT)
        except Exception as e:
             self.logger.critical(f"Critical error in main loop: {e}", exc_info=True)
             self.stop()
        finally:
             self.logger.info("Sentinel main execution loop finished.")
             print("Sentinel main execution loop finished.", flush=True)

    def stop(self, signum=None, frame=None):
        """Stop all monitoring components gracefully"""
        if self.stopping: return
            
        signal_name = signal.Signals(signum).name if signum else "programmatically"
        self.logger.info(f"Received stop signal ({signal_name}). Initiating shutdown...")
        print(f"Stopping Sentinel monitoring system... (Triggered by: {signal_name})", flush=True)
        
        self.stopping = True
        
        # Signal monitor instances to stop (if they have a stop method)
        for name, config in self.monitors_config.items():
            monitor_instance = config.get('instance')
            thread = self.threads.get(name)
            if monitor_instance and hasattr(monitor_instance, 'stop'):
                if thread and thread.is_alive(): # Only stop if thread is running
                    self.logger.info(f"Calling stop() for {name} monitor...")
                    try:
                        monitor_instance.stop()
                    except Exception as e:
                        self.logger.error(f"Error calling {name}.stop(): {e}")
                else:
                     self.logger.debug(f"Skipping stop() call for {name} (thread not alive or instance missing).")
            elif thread and thread.is_alive():
                 self.logger.info(f"{name} monitor instance has no stop() method.")

        # Wait briefly for threads to potentially exit from stop() signal
        self.logger.info("Waiting briefly for threads to stop...")
        time.sleep(1.0)

        # Check which threads are still alive after trying to stop them
        # Daemon threads should exit when the main thread finishes anyway
        alive_threads = [name for name, t in self.threads.items() if t.is_alive()]
        if alive_threads:
            self.logger.warning(f"Threads still alive after stop attempt: {', '.join(alive_threads)}")
        else:
             self.logger.info("All managed threads have stopped.")

        print("Sentinel shutdown sequence complete.", flush=True)
        self.logger.info("Sentinel shutdown sequence complete.")

def signal_handler(signum, frame):
    global _sentinel_instance
    print(f"\nSignal {signal.Signals(signum).name} received.", flush=True)
    if _sentinel_instance:
        _sentinel_instance.stop(signum, frame)
    else:
        print("Sentinel instance not found, exiting.", file=sys.stderr, flush=True)
        sys.exit(1)

def main():
    global _sentinel_instance
    
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Sentinel Monitoring System")
    parser.add_argument("--log-dir", default="logs", help="Directory for log files")
    parser.add_argument("--user-id", required=True, help="User ID from Electron app")
    # Use mutually exclusive group for admin flags
    admin_group = parser.add_mutually_exclusive_group(required=True)
    admin_group.add_argument("--admin", action="store_true", help="Run with admin privileges (passed from Electron)")
    admin_group.add_argument("--no-admin", action="store_false", dest="admin", help="Run without admin privileges (passed from Electron)")

    args = parser.parse_args()
    is_admin_flag = args.admin
    user_id = args.user_id

    # Verify if we actually have admin privileges
    actual_admin = is_admin()
    
    if is_admin_flag and not actual_admin:
        print(f"WARNING: --admin flag was specified but process is NOT running with admin privileges.", file=sys.stderr, flush=True)
        print(f"Some monitoring features will be limited. Please restart with administrator rights.", file=sys.stderr, flush=True)
        # Continue with limited functionality
    
    # Check for existing sentinel.py instances with the same user_id
    # This prevents duplicate admin instances from running
    if is_admin_flag:
        # Check if we're launched from Electron with SENTINEL_INTEGRATED flag
        sentinel_integrated = os.environ.get('SENTINEL_INTEGRATED', 'false').lower() == 'true'
        
        # If Electron is already running in admin mode with SENTINEL_INTEGRATED,
        # check if we're the nested process
        if sentinel_integrated:
            # Look for sentinel.py parent process that's part of Electron
            parent_pid = os.getppid()
            try:
                parent = psutil.Process(parent_pid)
                parent_cmdline = ' '.join(parent.cmdline() or [])
                # If parent is electron, and it's marked as integrated, we'll run directly
                if 'electron' in parent_cmdline.lower() or 'sentinel' in parent_cmdline.lower():
                    print(f"SENTINEL_INTEGRATED=true detected. Parent process appears to be Electron running as admin: {actual_admin}", 
                          flush=True)
                    if not actual_admin:
                        print(f"WARNING: Electron thinks it's admin but it isn't. Limited monitoring will be available.", 
                              file=sys.stderr, flush=True)
                    print(f"Running monitoring directly within Electron process.", flush=True)
                    # We'll continue with normal execution instead of exiting
                    # This ensures monitoring is active
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # If we can't check the parent, proceed with normal operation

        # Check for other sentinel.py processes if not in integrated mode or if we couldn't verify parent
        elif not sentinel_integrated:
            # Perform existing check for duplicate processes
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Skip the current process
                    if proc.info['pid'] == current_pid:
                        continue
                    
                    # Look for python processes running sentinel.py with the same user ID
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if 'sentinel.py' in cmdline and f'--user-id {user_id}' in cmdline and '--admin' in cmdline:
                            print(f"CRITICAL: Another Sentinel instance is already running for user {user_id} with admin privileges (PID: {proc.info['pid']})", 
                                  file=sys.stderr, flush=True)
                            print("Exiting to prevent duplicate instances.", flush=True)
                            sys.exit(0)  # Exit cleanly
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGBREAK'): # Windows specific
        signal.signal(signal.SIGBREAK, signal_handler)
        
    # Initialize and start the monitor
    try:
        _sentinel_instance = SentinelMonitor(user_id=user_id, is_admin_flag=is_admin_flag, log_dir=args.log_dir)
        _sentinel_instance.start()
    except Exception as e:
        print(f"CRITICAL: Failed to initialize or start SentinelMonitor: {e}", file=sys.stderr, flush=True)
        logging.exception("Critical error during Sentinel initialization/start") # Log detailed traceback
        sys.exit(1)
    finally:
        # Ensure cleanup/logging even if start() fails or exits early
        if _sentinel_instance and not _sentinel_instance.stopping:
             _sentinel_instance.logger.info("SentinelMonitor main function exiting.")
        print("Sentinel process main function finished.", flush=True)

    sys.exit(0) # Explicitly exit with code 0 if loop finishes normally

if __name__ == "__main__":
    main()