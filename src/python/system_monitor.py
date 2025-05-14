import psutil
import time
import os
import logging
from datetime import datetime
import threading
from collections import deque
import numpy as np
from opensearch_logger import OpenSearchLogger

class SystemMonitor:
    def __init__(self, log_dir="logs", electron_user_id=None,
                 normal_interval=900, alert_interval=5,
                 window_size=120, alert_trigger_count=3, alert_clear_count=5):
        """Initialize system monitor"""
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "system_monitor.log")
        
        # Setup logging to append in real-time
        self.logger = logging.getLogger('system_monitor')
        if not self.logger.hasHandlers():
            self.logger.setLevel(logging.INFO)
            handler = logging.FileHandler(self.log_file, mode='a')
            formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            self.logger.addHandler(console)

        self.opensearch_logger = OpenSearchLogger(electron_user_id=electron_user_id)
        self.logger.info("System Monitor initialized. Attempting to connect to OpenSearch...")
        if not self.opensearch_logger.client:
            self.logger.warning("Failed to connect to OpenSearch. Logs will not be sent.")
        else:
            self.logger.info("OpenSearch connection successful.")
        
        self.last_disk_io = psutil.disk_io_counters()
        self.last_disk_time = time.time()

        # Smart logging config
        self.normal_interval = normal_interval
        self.alert_interval = alert_interval
        self.alert_trigger_count = alert_trigger_count
        self.alert_clear_count = alert_clear_count
        self._reset_alert_state()
        self._last_log_time = 0

        # Rolling windows for self-tuning thresholds
        self.window_size = window_size
        self.cpu_window = deque(maxlen=window_size)
        self.mem_window = deque(maxlen=window_size)
        self.disk_read_window = deque(maxlen=window_size)
        self.disk_write_window = deque(maxlen=window_size)

    def _reset_alert_state(self):
        self.in_alert = False
        self.cpu_alert_count = 0
        self.mem_alert_count = 0
        self.disk_alert_count = 0
        self.cpu_normal_count = 0
        self.mem_normal_count = 0
        self.disk_normal_count = 0

    def _format_bytes(self, bytes):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024

    def _get_disk_activity(self):
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

    def _update_windows(self, cpu_percent, mem_percent, disk_activity):
        self.cpu_window.append(cpu_percent)
        self.mem_window.append(mem_percent)
        if disk_activity:
            self.disk_read_window.append(disk_activity['read_speed'])
            self.disk_write_window.append(disk_activity['write_speed'])
        else:
            self.disk_read_window.append(0)
            self.disk_write_window.append(0)

    def _dynamic_threshold(self, window):
        if len(window) < 10:
            # Not enough data, use a high threshold to avoid false alerts
            return float('inf')
        arr = np.array(window)
        return arr.mean() + 2 * arr.std()

    def _check_alerts(self, cpu_percent, mem_percent, disk_activity):
        cpu_thresh = self._dynamic_threshold(self.cpu_window)
        mem_thresh = self._dynamic_threshold(self.mem_window)
        disk_read_thresh = self._dynamic_threshold(self.disk_read_window)
        disk_write_thresh = self._dynamic_threshold(self.disk_write_window)
        # CPU
        if cpu_percent >= cpu_thresh:
            self.cpu_alert_count += 1
            self.cpu_normal_count = 0
        else:
            self.cpu_normal_count += 1
            self.cpu_alert_count = 0
        # Memory
        if mem_percent >= mem_thresh:
            self.mem_alert_count += 1
            self.mem_normal_count = 0
        else:
            self.mem_normal_count += 1
            self.mem_alert_count = 0
        # Disk
        disk_alert = False
        if disk_activity:
            if (disk_activity['read_speed'] >= disk_read_thresh or
                disk_activity['write_speed'] >= disk_write_thresh):
                self.disk_alert_count += 1
                self.disk_normal_count = 0
                disk_alert = True
            else:
                self.disk_normal_count += 1
                self.disk_alert_count = 0
        # Enter alert mode if any metric is above threshold for alert_trigger_count
        if (self.cpu_alert_count >= self.alert_trigger_count or
            self.mem_alert_count >= self.alert_trigger_count or
            self.disk_alert_count >= self.alert_trigger_count):
            self.in_alert = True
        # Exit alert mode if all metrics are normal for alert_clear_count
        if (self.in_alert and
            self.cpu_normal_count >= self.alert_clear_count and
            self.mem_normal_count >= self.alert_clear_count and
            self.disk_normal_count >= self.alert_clear_count):
            self.in_alert = False
            self._reset_alert_state()

    def _log_system_metrics(self, cpu_percent, cpu_per_core, memory, disk_activity):
        memory_used = self._format_bytes(memory.used)
        memory_total = self._format_bytes(memory.total)
        opensearch_details = {
            "cpu_percent_overall": cpu_percent,
            "cpu_percent_per_core": cpu_per_core,
            "memory_percent": memory.percent,
            "memory_used_bytes": memory.used,
            "memory_total_bytes": memory.total,
        }
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
        self.logger.info(
            f"CPU: {cpu_percent}% (Cores: {cpu_per_core}) | "
            f"Memory: {memory_used}/{memory_total} ({memory.percent}%) | "
            f"Disk: {disk_msg}"
        )
        if self.opensearch_logger.client:
            self.opensearch_logger.log(
                monitor_type="system_monitor",
                event_type="system_stats_snapshot",
                event_details=opensearch_details
            )

    def monitor(self):
        self.logger.info("Starting system monitoring...")
        self.logger.info("Logging CPU, Memory, and Disk activity...")
        try:
            while True:
                # Get metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                cpu_per_core = psutil.cpu_percent(percpu=True)
                memory = psutil.virtual_memory()
                disk_activity = self._get_disk_activity()
                # Update rolling windows
                self._update_windows(cpu_percent, memory.percent, disk_activity)
                # Check for alert state
                self._check_alerts(cpu_percent, memory.percent, disk_activity)
                now = time.time()
                # Decide if we should log/send
                should_log = False
                if self.in_alert:
                    if now - self._last_log_time >= self.alert_interval:
                        should_log = True
                else:
                    if now - self._last_log_time >= self.normal_interval:
                        should_log = True
                if should_log:
                    self._log_system_metrics(cpu_percent, cpu_per_core, memory, disk_activity)
                    self._last_log_time = now
                # Sleep a short time to keep checking
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("System monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in monitoring: {str(e)}")

def main():
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