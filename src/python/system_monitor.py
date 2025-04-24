import psutil
import time
import os
import logging
from datetime import datetime
import threading
from opensearch_logger import OpenSearchLogger

class SystemMonitor:
    def __init__(self, log_dir="logs", electron_user_id=None):
        """Initialize system monitor"""
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "system_monitor.log")
        
        # Setup logging to append in real-time
        self.logger = logging.getLogger('system_monitor')
        # Prevent adding handlers multiple times if script re-run/re-imported
        if not self.logger.hasHandlers():
            self.logger.setLevel(logging.INFO)
            handler = logging.FileHandler(self.log_file, mode='a')
            formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
            # For console output
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            self.logger.addHandler(console)

        # Instantiate OpenSearch Logger
        self.opensearch_logger = OpenSearchLogger(electron_user_id=electron_user_id)
        self.logger.info("System Monitor initialized. Attempting to connect to OpenSearch...")
        if not self.opensearch_logger.client:
            self.logger.warning("Failed to connect to OpenSearch. Logs will not be sent.")
        else:
            self.logger.info("OpenSearch connection successful.")
        
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
            # Note: Calling cpu_percent twice quickly might give skewed results. Get overall first.
            # cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True) # Shorter interval for per-core?
            cpu_per_core = psutil.cpu_percent(percpu=True) # Get instantaneous per-core after overall
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_used = self._format_bytes(memory.used)
            memory_total = self._format_bytes(memory.total)
            
            # Prepare structured data for OpenSearch
            opensearch_details = {
                "cpu_percent_overall": cpu_percent,
                "cpu_percent_per_core": cpu_per_core,
                "memory_percent": memory.percent,
                "memory_used_bytes": memory.used,
                "memory_total_bytes": memory.total,
            }

            # Get disk activity
            disk_activity = self._get_disk_activity()
            if disk_activity and (disk_activity['read_bytes'] > 0 or disk_activity['write_bytes'] > 0):
                disk_msg = (
                    f"Read: {self._format_bytes(disk_activity['read_speed'])}/s "
                    f"({self._format_bytes(disk_activity['read_bytes'])} total) | "
                    f"Write: {self._format_bytes(disk_activity['write_speed'])}/s "
                    f"({self._format_bytes(disk_activity['write_bytes'])} total)"
                )
                opensearch_details["disk_read_speed_bps"] = disk_activity['read_speed']
                opensearch_details["disk_write_speed_bps"] = disk_activity['write_speed']
                opensearch_details["disk_read_bytes_interval"] = disk_activity['read_bytes']
                opensearch_details["disk_write_bytes_interval"] = disk_activity['write_bytes']
            else:
                disk_msg = "No disk activity"
            
            # Log to file/console
            self.logger.info(
                f"CPU: {cpu_percent}% (Cores: {cpu_per_core}) | "
                f"Memory: {memory_used}/{memory_total} ({memory.percent}%) | "
                f"Disk: {disk_msg}"
            )
            
            # Send structured log to OpenSearch
            if self.opensearch_logger.client:
                self.opensearch_logger.log(
                    monitor_type="system_monitor",
                    event_type="system_stats_snapshot",
                    event_details=opensearch_details
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