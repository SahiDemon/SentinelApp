import psutil
import time
import os
import logging
from datetime import datetime
import re

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

class ProcessMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize process monitor"""
        self.logger = setup_logger('process_monitor', log_dir)
        self.known_processes = {}
        
        # System processes to ignore
        self.system_processes = {
            'svchost.exe', 'services.exe', 'csrss.exe', 'smss.exe', 'lsass.exe',
            'winlogon.exe', 'spoolsv.exe', 'wininit.exe', 'system', 'registry',
            'fontdrvhost.exe', 'dwm.exe', 'ctfmon.exe', 'conhost.exe',
            'runtimebroker.exe', 'taskhostw.exe', 'explorer.exe', 'SearchHost.exe',
            'SearchIndexer.exe', 'ShellExperienceHost.exe', 'StartMenuExperienceHost.exe',
            'ApplicationFrameHost.exe', 'TextInputHost.exe', 'sihost.exe',
            'SecurityHealthService.exe', 'SearchProtocolHost.exe', 'dllhost.exe',
            'WmiPrvSE.exe', 'Memory Compression', 'Idle', 'System Idle Process',
            'Registry', 'secure system'
        }

    def _should_monitor_process(self, name):
        """Check if process should be monitored"""
        if not name:
            return False
            
        name_lower = name.lower()
        return not (
            name_lower in {p.lower() for p in self.system_processes} or
            'system32' in name_lower or
            'windows' in name_lower or
            'microsoft' in name_lower
        )

    def _get_process_info(self, proc):
        """Get relevant process information"""
        try:
            cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else ''
            
            info = {
                'name': proc.name(),
                'cmdline': cmdline,
                'username': proc.username(),
                'cpu_percent': proc.cpu_percent(),
                'memory_percent': round(proc.memory_percent(), 2),
                'status': proc.status(),
                'create_time': datetime.fromtimestamp(proc.create_time()).strftime('%Y-%m-%d %H:%M:%S')
            }
            
            try:
                parent = proc.parent()
                if parent:
                    info['parent'] = f"{parent.name()} (PID: {parent.pid})"
            except:
                info['parent'] = "Unknown"
                
            return info
        except:
            return None

    def _format_process_message(self, pid, info, event_type="Started"):
        """Format process information into a readable message"""
        if not info:
            return None
            
        msg_parts = [
            f"Process {event_type}",
            f"{info['name']} (PID: {pid})"
        ]
        
        if info.get('cmdline'):
            # Truncate command line if too long
            cmdline = info['cmdline']
            if len(cmdline) > 100:
                cmdline = cmdline[:97] + "..."
            msg_parts.append(f"CMD: {cmdline}")
            
        if info.get('cpu_percent') or info.get('memory_percent'):
            resources = []
            if info.get('cpu_percent'):
                resources.append(f"CPU: {info['cpu_percent']}%")
            if info.get('memory_percent'):
                resources.append(f"Memory: {info['memory_percent']}%")
            msg_parts.append(" ".join(resources))
            
        if info.get('parent', 'Unknown') != 'Unknown':
            msg_parts.append(f"Parent: {info['parent']}")
            
        if info.get('username'):
            msg_parts.append(f"User: {info['username']}")
            
        return " | ".join(msg_parts)

    def monitor(self):
        """Start monitoring processes"""
        self.logger.info("Starting process monitoring...")
        self.logger.info("Monitoring all non-system processes...")

        try:
            while True:
                try:
                    # Get current processes
                    current_processes = {
                        p.pid: p for p in psutil.process_iter(['name', 'pid', 'cmdline', 'username'])
                        if self._should_monitor_process(p.info['name'])
                    }
                    
                    # Check for new processes
                    for pid, proc in current_processes.items():
                        if pid not in self.known_processes:
                            info = self._get_process_info(proc)
                            if info:
                                self.known_processes[pid] = info
                                msg = self._format_process_message(pid, info)
                                if msg:
                                    self.logger.info(msg)
                    
                    # Check for terminated processes
                    for pid in list(self.known_processes.keys()):
                        if pid not in current_processes:
                            info = self.known_processes[pid]
                            msg = self._format_process_message(pid, info, "Terminated")
                            if msg:
                                self.logger.info(msg)
                            del self.known_processes[pid]
                    
                    time.sleep(1)  # Small delay to prevent high CPU usage
                    
                except Exception as e:
                    self.logger.error(f"Error monitoring processes: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            self.logger.info("Process monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in process monitoring: {str(e)}")

def main():
    """Main function"""
    print("\nProcess Monitor")
    print("==============")
    print("Monitoring:")
    print("- All non-system processes")
    print("- Process creation/termination")
    print("- Command line arguments")
    print("- Resource usage")
    print("==============\n")
    
    monitor = ProcessMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping process monitor...")

if __name__ == "__main__":
    main()