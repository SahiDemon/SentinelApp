import time
import os
import win32file
import win32api
from datetime import datetime
import psutil
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
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

class USBFileHandler(FileSystemEventHandler):
    def __init__(self, logger, drive_letter):
        self.logger = logger
        self.drive_letter = drive_letter
        self.file_sizes = {}  # Track file sizes for copy detection
        self.system_paths = self._get_system_paths()
        self.deletion_times = {}  # Track deletion times
        self.creation_times = {}  # Track creation times

    def _get_system_paths(self):
        """Get common system paths to track file movements"""
        user_profile = os.path.expanduser('~')
        return {
            'Desktop': os.path.join(user_profile, 'Desktop'),
            'Documents': os.path.join(user_profile, 'Documents'),
            'Downloads': os.path.join(user_profile, 'Downloads')
        }

    def _get_file_size(self, filepath):
        """Get file size safely"""
        try:
            return os.path.getsize(filepath)
        except:
            return None

    def _find_similar_file(self, filename, size):
        """Find similar file in system paths"""
        for path_name, system_path in self.system_paths.items():
            try:
                system_file = os.path.join(system_path, filename)
                if os.path.exists(system_file):
                    system_size = self._get_file_size(system_file)
                    creation_time = os.path.getctime(system_file)
                    return path_name, system_file, creation_time
            except:
                continue
        return None, None, None

    def on_created(self, event):
        if event.is_directory:
            return

        try:
            current_time = time.time()
            self.creation_times[event.src_path] = current_time
            
            # Get file details
            file_size = self._get_file_size(event.src_path)
            filename = os.path.basename(event.src_path)
            
            if file_size is not None:
                # Store file size for tracking
                self.file_sizes[event.src_path] = file_size
                
                # Log creation without assuming copy direction
                self.logger.info(
                    f"New file detected on USB ({self.drive_letter}:)\n"
                    f"File: {filename}\n"
                    f"Size: {file_size:,} bytes"
                )

        except Exception as e:
            self.logger.error(f"Error tracking file creation: {str(e)}")

    def on_deleted(self, event):
        if event.is_directory:
            return

        try:
            current_time = time.time()
            filename = os.path.basename(event.src_path)
            original_size = self.file_sizes.get(event.src_path)
            creation_time = self.creation_times.get(event.src_path)
            
            if original_size is not None:
                # Check if file appeared in system paths
                system_location, _, system_creation_time = self._find_similar_file(filename, original_size)
                
                if system_location and system_creation_time:
                    # If the system file was created after our file was created on USB
                    # and within the last few seconds, it was likely copied TO system
                    if (creation_time and 
                        system_creation_time > creation_time and 
                        current_time - system_creation_time < 5):  # 5 second threshold
                        self.logger.info(
                            f"File copied FROM USB ({self.drive_letter}:) TO System ({system_location})\n"
                            f"File: {filename}\n"
                            f"Size: {original_size:,} bytes"
                        )
                    else:
                        # Just a regular deletion
                        self.logger.info(
                            f"File deleted from USB ({self.drive_letter}:)\n"
                            f"File: {filename}"
                        )
                else:
                    # No matching file in system, must be a deletion
                    self.logger.info(
                        f"File deleted from USB ({self.drive_letter}:)\n"
                        f"File: {filename}"
                    )
                
                # Clean up tracking
                del self.file_sizes[event.src_path]
                if event.src_path in self.creation_times:
                    del self.creation_times[event.src_path]

        except Exception as e:
            self.logger.error(f"Error tracking file deletion: {str(e)}")

    def on_modified(self, event):
        if event.is_directory:
            return

        try:
            filename = os.path.basename(event.src_path)
            new_size = self._get_file_size(event.src_path)
            original_size = self.file_sizes.get(event.src_path)
            
            if new_size is not None and original_size is not None and new_size != original_size:
                self.logger.info(
                    f"File modified on USB ({self.drive_letter}:)\n"
                    f"File: {filename}\n"
                    f"Original size: {original_size:,} bytes\n"
                    f"New size: {new_size:,} bytes"
                )
                self.file_sizes[event.src_path] = new_size
        except Exception as e:
            self.logger.error(f"Error tracking file modification: {str(e)}")

class USBMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize USB monitor"""
        self.logger = setup_logger('usb_monitor', log_dir)
        self.known_devices = {}
        self.drive_letters = set()
        self.observers = {}
        self._update_current_drives()

    def _update_current_drives(self):
        """Update currently available drive letters"""
        drives = win32api.GetLogicalDriveStrings()
        self.drive_letters = set(d[0] for d in drives.split('\000') if d)

    def _get_drive_info(self, drive_letter):
        """Get information about the drive"""
        try:
            drive_type = win32file.GetDriveType(f"{drive_letter}:\\")
            if drive_type == win32file.DRIVE_REMOVABLE:
                volume_info = win32api.GetVolumeInformation(f"{drive_letter}:\\")
                volume_name = volume_info[0]
                fs_name = volume_info[4]
                total_bytes = win32file.GetDiskFreeSpaceEx(f"{drive_letter}:\\")[1]
                return {
                    'volume_name': volume_name,
                    'filesystem': fs_name,
                    'total_size': f"{total_bytes:,} bytes",
                    'type': 'Removable'
                }
        except Exception as e:
            self.logger.error(f"Error getting drive info for {drive_letter}: {str(e)}")
        return None

    def _inventory_drive(self, drive_letter):
        """Take inventory of files on USB drive"""
        try:
            path = f"{drive_letter}:\\"
            total_files = 0
            total_size = 0
            file_list = []

            for root, _, files in os.walk(path):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        size = os.path.getsize(file_path)
                        rel_path = os.path.relpath(file_path, path)
                        total_files += 1
                        total_size += size
                        file_list.append(f"{rel_path} ({size:,} bytes)")
                    except:
                        continue

            self.logger.info(
                f"USB Drive Inventory ({drive_letter}:)\n"
                f"Total Files: {total_files}\n"
                f"Total Size: {total_size:,} bytes\n"
                "Files:\n" + "\n".join(f"  - {f}" for f in file_list)
            )

        except Exception as e:
            self.logger.error(f"Error inventorying drive {drive_letter}: {str(e)}")

    def _start_file_monitoring(self, drive_letter):
        """Start monitoring file operations on a USB drive"""
        try:
            path = f"{drive_letter}:\\"
            event_handler = USBFileHandler(self.logger, drive_letter)
            observer = Observer()
            observer.schedule(event_handler, path, recursive=True)
            observer.start()
            self.observers[drive_letter] = observer
            
            # Take initial inventory
            self._inventory_drive(drive_letter)
                
        except Exception as e:
            self.logger.error(f"Error starting file monitoring on {drive_letter}: {str(e)}")

    def _stop_file_monitoring(self, drive_letter):
        """Stop monitoring file operations on a USB drive"""
        if drive_letter in self.observers:
            try:
                # Take final inventory before stopping
                self._inventory_drive(drive_letter)
                self.observers[drive_letter].stop()
                self.observers[drive_letter].join()
            except:
                pass
            finally:
                del self.observers[drive_letter]

    def _monitor_drive_changes(self):
        """Monitor for new or removed drives"""
        current_drives = set(d[0] for d in win32api.GetLogicalDriveStrings().split('\000') if d)
        
        # Check for new drives
        new_drives = current_drives - self.drive_letters
        for drive in new_drives:
            drive_info = self._get_drive_info(drive)
            if drive_info:
                self.logger.info(
                    f"New USB drive detected ({drive}:)\n"
                    f"Volume Name: {drive_info['volume_name']}\n"
                    f"Filesystem: {drive_info['filesystem']}\n"
                    f"Total Size: {drive_info['total_size']}"
                )
                self._start_file_monitoring(drive)
                
        # Check for removed drives
        removed_drives = self.drive_letters - current_drives
        for drive in removed_drives:
            self.logger.info(f"USB drive removed: {drive}:")
            self._stop_file_monitoring(drive)
        
        self.drive_letters = current_drives

    def monitor(self):
        """Start monitoring USB devices"""
        self.logger.info("Starting USB device monitoring...")
        self.logger.info("Monitoring for USB drive events...")

        try:
            while True:
                try:
                    # Monitor drive changes
                    self._monitor_drive_changes()
                    time.sleep(1)  # Prevent high CPU usage
                    
                except Exception as e:
                    self.logger.error(f"Error monitoring USB: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            self.logger.info("USB monitoring stopped")
            # Stop all file monitoring
            for drive in list(self.observers.keys()):
                self._stop_file_monitoring(drive)
        except Exception as e:
            self.logger.error(f"Error in USB monitoring: {str(e)}")
            raise

def main():
    """Main function"""
    print("\nUSB Device Monitor")
    print("=================")
    print("Monitoring:")
    print("- USB drive connection/removal")
    print("- File operations on USB drives")
    print("- File copying tracking")
    print("=================\n")
    
    monitor = USBMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping USB monitor...")

if __name__ == "__main__":
    main()