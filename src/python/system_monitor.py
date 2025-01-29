import psutil
import time
import os
import logging
from datetime import datetime
import threading

class SystemMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize system monitor"""
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "system_monitor.log")
        
        # Setup logging to append in real-time
        self.logger = logging.getLogger('system_monitor')
        self.logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(self.log_file, mode='a')
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # For console output
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        self.logger.addHandler(console)
        
        # Initialize disk monitoring
        self.last_disk_io = psutil.disk_io_counters()
        self.last_disk_time = time.time()

    def _format_bytes(self, bytes):
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024

    def _get_disk_activity(self):
        """Get current disk activity"""
        try:
            current_disk_io = psutil.disk_io_counters()
            current_time = time.time()
            time_delta = current_time - self.last_disk_time

            read_bytes = current_disk_io.read_bytes - self.last_disk_io.read_bytes
            write_bytes = current_disk_io.write_bytes - self.last_disk_io.write_bytes

            read_speed = read_bytes / time_delta if time_delta > 0 else 0
            write_speed = write_bytes / time_delta if time_delta > 0 else 0

            self.last_disk_io = current_disk_io
            self.last_disk_time = current_time

            return {
                'read_speed': read_speed,
                'write_speed': write_speed,
                'read_bytes': read_bytes,
                'write_bytes': write_bytes
            }
        except:
            return None

    def _log_system_metrics(self):
        """Log current system metrics"""
        try:
            # Get CPU usage per core and overall
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_used = self._format_bytes(memory.used)
            memory_total = self._format_bytes(memory.total)
            
            # Get disk activity
            disk_activity = self._get_disk_activity()
            if disk_activity and (disk_activity['read_bytes'] > 0 or disk_activity['write_bytes'] > 0):
                disk_msg = (
                    f"Read: {self._format_bytes(disk_activity['read_speed'])}/s "
                    f"({self._format_bytes(disk_activity['read_bytes'])} total) | "
                    f"Write: {self._format_bytes(disk_activity['write_speed'])}/s "
                    f"({self._format_bytes(disk_activity['write_bytes'])} total)"
                )
            else:
                disk_msg = "No disk activity"
            
            # Format message
            self.logger.info(
                f"CPU: {cpu_percent}% (Cores: {cpu_per_core}) | "
                f"Memory: {memory_used}/{memory_total} ({memory.percent}%) | "
                f"Disk: {disk_msg}"
            )
            
        except Exception as e:
            self.logger.error(f"Error logging metrics: {str(e)}")

    def monitor(self):
        """Start system monitoring"""
        self.logger.info("Starting system monitoring...")
        self.logger.info("Logging CPU, Memory, and Disk activity...")

        try:
            while True:
                self._log_system_metrics()
                time.sleep(1)  # Update every second

        except KeyboardInterrupt:
            self.logger.info("System monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in monitoring: {str(e)}")

def main():
    """Main function"""
    print("\nSystem Monitor")
    print("==============")
    print("Monitoring:")
    print("- CPU usage (overall and per core)")
    print("- Memory usage")
    print("- Disk activity (read/write)")
    print("==============\n")
    
    monitor = SystemMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping system monitor...")

if __name__ == "__main__":
    main()