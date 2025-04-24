import psutil
import time
import os
from datetime import datetime
import re
from opensearch_logger import OpenSearchLogger

class ProcessMonitor:
    def __init__(self, electron_user_id=None):
        """Initialize process monitor"""
        self.opensearch_logger = OpenSearchLogger(electron_user_id=electron_user_id)
        print("Process Monitor initialized. Attempting to connect to OpenSearch...")
        if not self.opensearch_logger.client:
            print("WARNING: Failed to connect to OpenSearch. Logs will not be sent.")
        else:
            print("OpenSearch connection successful.")
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

    def monitor(self):
        """Start monitoring processes"""
        print("Starting process monitoring...")
        print("Monitoring all non-system processes...")

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
                                event_details = {
                                    "process_pid": pid,
                                    "process_name": info.get('name'),
                                    "command_line": info.get('cmdline'),
                                    "user": info.get('username'),
                                    "parent_process": info.get('parent'),
                                    "status": info.get('status'),
                                    "create_time": info.get('create_time')
                                }
                                event_details = {k: v for k, v in event_details.items() if v is not None and v != ''}
                                self.opensearch_logger.log(
                                    monitor_type="process_monitor",
                                    event_type="process_started",
                                    event_details=event_details
                                )
                    
                    # Check for terminated processes
                    for pid in list(self.known_processes.keys()):
                        if pid not in current_processes:
                            info = self.known_processes[pid]
                            event_details = {
                                "process_pid": pid,
                                "process_name": info.get('name'),
                                "command_line": info.get('cmdline'),
                                "user": info.get('username'),
                                "parent_process": info.get('parent'),
                                "create_time": info.get('create_time')
                            }
                            event_details = {k: v for k, v in event_details.items() if v is not None and v != ''}
                            self.opensearch_logger.log(
                                monitor_type="process_monitor",
                                event_type="process_terminated",
                                event_details=event_details
                            )
                            del self.known_processes[pid]
                    
                    time.sleep(1)  # Small delay to prevent high CPU usage
                    
                except Exception as e:
                    print(f"ERROR: Error monitoring processes: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            print("Process monitoring stopped")
        except Exception as e:
            print(f"ERROR: Error in process monitoring: {str(e)}")

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