import os
import logging
import threading
import ctypes
import sys
from login_monitor import LoginMonitor
from process_monitor import ProcessMonitor
from network_monitor import NetworkMonitor
from filesystem_monitor import FileSystemMonitor
from system_monitor import SystemMonitor
from browser_monitor import BrowserMonitor
from usb_monitor import USBMonitor
import time

def is_admin():
    """Check if script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with admin privileges"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )

class SentinelMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize the sentinel monitoring system"""
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Setup sentinel logger
        self.logger = logging.getLogger('sentinel')
        self.logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(os.path.join(log_dir, "sentinel.log"))
        console = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                   datefmt='%Y-%m-%d %H:%M:%S')
        
        handler.setFormatter(formatter)
        console.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.addHandler(console)
        
        # Check for admin privileges
        if not is_admin():
            self.logger.error("This script requires administrator privileges!")
            print("\nThis script requires administrator privileges.")
            print("Please run as administrator to enable all monitoring features.")
            print("Attempting to restart with elevated privileges...\n")
            run_as_admin()
            sys.exit(1)
            
        # Initialize all monitors
        self.monitors = {
            'Login': {
                'instance': LoginMonitor(self.log_dir),
                'requires_admin': True,
                'status': False
            },
            'Process': {
                'instance': ProcessMonitor(self.log_dir),
                'requires_admin': False,
                'status': False
            },
            'Network': {
                'instance': NetworkMonitor(self.log_dir),
                'requires_admin': True,
                'status': False
            },
            'Filesystem': {
                'instance': FileSystemMonitor(self.log_dir),
                'requires_admin': False,
                'status': False
            },
            'System': {
                'instance': SystemMonitor(self.log_dir),
                'requires_admin': True,
                'status': False
            },
            'Browser': {
                'instance': BrowserMonitor(self.log_dir),
                'requires_admin': True,
                'status': False
            },
            'USB': {
                'instance': USBMonitor(self.log_dir),
                'requires_admin': True,
                'status': False
            }
        }
        
        self.threads = {}
        self.stopping = False

    def _run_monitor(self, name):
        """Run a monitor in a loop"""
        monitor = self.monitors[name]['instance']
        try:
            self.logger.info(f"Starting {name} monitor...")
            self.monitors[name]['status'] = True
            monitor.monitor()
        except Exception as e:
            self.logger.error(f"Error in {name} monitor: {str(e)}")
            self.monitors[name]['status'] = False
        finally:
            self.monitors[name]['status'] = False

    def _check_monitor_status(self):
        """Log the status of all monitors"""
        while not self.stopping:
            status = []
            for name, info in self.monitors.items():
                thread = self.threads.get(name)
                is_alive = thread and thread.is_alive()
                status.append(f"{name}: {'Running' if is_alive else 'Stopped'}")
            
            self.logger.info("Monitor Status | " + " | ".join(status))
            time.sleep(60)  # Check status every minute

    def start(self):
        """Start all monitoring components"""
        print("\nSentinel Monitoring System")
        print("========================")
        print("Active Monitors:")
        for i, name in enumerate(self.monitors.keys(), 1):
            print(f"{i}. {name} Monitor")
        print("========================\n")
        
        self.logger.info("Starting Sentinel monitoring system...")
        
        # Restore status monitoring thread
        status_thread = threading.Thread(
            target=self._check_monitor_status,
            name="StatusMonitor"
        )
        status_thread.daemon = True
        status_thread.start()
        
        # Start monitor threads normally
        for name in self.monitors:
            thread = threading.Thread(
                target=self._run_monitor,
                args=(name,),
                name=f"{name}Monitor"
            )
            thread.daemon = True
            self.threads[name] = thread
            thread.start()
            time.sleep(1)
        
        try:
            while True:
                # Only check thread health
                all_dead = True
                for name, thread in self.threads.items():
                    if thread.is_alive():
                        all_dead = False
                    elif self.monitors[name]['status']:
                        self.logger.error(f"{name} monitor has stopped unexpectedly!")
                        self._restart_monitor(name)
                
                if all_dead:
                    self.logger.error("All monitors have stopped!")
                    break
                    
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\nStopping Sentinel monitoring system...")
            self.stopping = True
            
            # Wait for threads to finish
            for thread in self.threads.values():
                thread.join(timeout=2)
            
            self.logger.info("All monitoring stopped")

    def _restart_monitor(self, name):
        """Restart a failed monitor"""
        self.monitors[name]['status'] = False
        new_thread = threading.Thread(
            target=self._run_monitor,
            args=(name,),
            name=f"{name}Monitor"
        )
        new_thread.daemon = True
        self.threads[name] = new_thread
        new_thread.start()

def main():
    monitor = SentinelMonitor()
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\nStopping Sentinel monitor...")

if __name__ == "__main__":
    main()