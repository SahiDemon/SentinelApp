import time
from datetime import datetime
import win32evtlog
import win32con
import win32api
import os
import sys
import ctypes
import logging

def setup_logger(name, log_dir="logs"):
    """Set up a logger instance"""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Create handlers
    file_handler = logging.FileHandler(os.path.join(log_dir, f"{name}.log"))
    console_handler = logging.StreamHandler()
    
    # Create formatters and add it to handlers
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class LoginMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize login monitor"""
        self.logger = setup_logger('login_monitor', log_dir)
        self.server = 'localhost'
        self.logtype = 'Security'
        self.last_event = {}
        self.handle = None

    def _is_admin(self):
        """Check if script is running with admin rights"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def _get_logon_type(self, logon_type):
        """Convert logon type to readable format"""
        try:
            logon_type = int(logon_type)
            types = {
                2: "Interactive Login",
                3: "Network Login",
                4: "Batch Login",
                5: "Service Login",
                7: "Unlock",
                8: "Network Login (Clear Text)",
                9: "New Credentials",
                10: "Remote Desktop",
                11: "Cached Login"
            }
            return types.get(logon_type, f"Unknown Type ({logon_type})")
        except:
            return "Unknown Type"

    def _get_status(self, status):
        """Convert status code to readable format"""
        codes = {
            "0xC0000064": "Invalid Username",
            "0xc0000380": "Invalid Password",
            "0xC000006A": "Wrong Password",
            "0xC0000234": "Account Locked",
            "0xC0000072": "Account Disabled",
            "0xC000006F": "Time Restriction",
            "0xC0000070": "Workstation Restriction",
            "0xC0000193": "Account Expired",
            "0xC0000071": "Password Expired"
        }
        return codes.get(status, status)

    def _should_log_event(self, username):
        """Check if event should be logged"""
        if not username:
            return False
            
        # Skip system accounts
        ignore_patterns = [
            "NT AUTHORITY", "SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE",
            "ANONYMOUS LOGON", "WINDOW MANAGER", "FONT DRIVER HOST", "DWM",
            "UMFD", "$"
        ]
        return not any(pattern.lower() in username.lower() for pattern in ignore_patterns)

    def _format_event_data(self, event):
        """Format event data into structured format"""
        try:
            data = {}
            message = event.StringInserts

            if not message or len(message) < 5:
                return None

            # Extract username and domain
            data['username'] = message[5]  # Account Name
            data['domain'] = message[6]    # Account Domain
            
            if event.EventID == 4624:  # Successful login
                data['logon_type'] = message[8]
                data['workstation'] = message[11]
                data['source_ip'] = message[18]
            elif event.EventID == 4625:  # Failed login
                data['logon_type'] = message[10]
                data['workstation'] = message[13]
                data['status'] = message[7]
                data['sub_status'] = message[9]

            return data
        except:
            return None

    def _open_event_log(self):
        """Open event log handle"""
        try:
            if self.handle:
                try:
                    win32evtlog.CloseEventLog(self.handle)
                except:
                    pass
            self.handle = win32evtlog.OpenEventLog(self.server, self.logtype)
            return True
        except Exception as e:
            self.logger.error(f"Failed to open event log: {str(e)}")
            return False

    def monitor(self):
        """Start monitoring login events"""
        if not self._is_admin():
            self.logger.error("This script requires administrator privileges!")
            if sys.platform == 'win32':
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable,
                    " ".join(sys.argv), None, 1
                )
            sys.exit(1)

        self.logger.info("Starting login monitoring...")
        self.logger.info("Monitoring for login success/failure events...")

        flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        
        try:
            while True:
                try:
                    if not self.handle and not self._open_event_log():
                        time.sleep(5)
                        continue

                    events = win32evtlog.ReadEventLog(self.handle, flags, 0)
                    
                    for event in events:
                        if event.EventID not in [4624, 4625]:
                            continue
                            
                        data = self._format_event_data(event)
                        if not data:
                            continue
                            
                        username = data.get('username')
                        domain = data.get('domain')
                        
                        if not username or not domain:
                            continue
                            
                        full_username = f"{domain}\\{username}"
                        
                        if not self._should_log_event(full_username):
                            continue
                            
                        event_key = f"{full_username}-{event.EventID}-{event.TimeGenerated}"
                        
                        if event_key in self.last_event:
                            continue
                            
                        self.last_event[event_key] = time.time()
                        
                        if event.EventID == 4624:  # Success
                            msg_parts = [
                                "LOGIN SUCCESS",
                                f"User: {full_username}"
                            ]
                            
                            logon_type = self._get_logon_type(data.get('logon_type', ''))
                            if logon_type:
                                msg_parts.append(f"Type: {logon_type}")
                                
                            if data.get('workstation', '-') != '-':
                                msg_parts.append(f"From: {data['workstation']}")
                                
                            if data.get('source_ip', '-') not in ['-', '::1', '127.0.0.1']:
                                msg_parts.append(f"IP: {data['source_ip']}")
                                
                            self.logger.info(" | ".join(msg_parts))
                            
                        else:  # Failure
                            msg_parts = [
                                "LOGIN FAILED",
                                f"User: {full_username}"
                            ]
                            
                            if data.get('sub_status'):
                                reason = self._get_status(data['sub_status'])
                                msg_parts.append(f"Reason: {reason}")
                                
                            if data.get('workstation', '-') != '-':
                                msg_parts.append(f"From: {data['workstation']}")
                                
                            if data.get('source_ip', '-') not in ['-', '::1', '127.0.0.1']:
                                msg_parts.append(f"IP: {data['source_ip']}")
                                
                            self.logger.warning(" | ".join(msg_parts))

                    # Clean up old events
                    current_time = time.time()
                    self.last_event = {
                        k: v for k, v in self.last_event.items() 
                        if current_time - v < 5
                    }

                except Exception as e:
                    self.logger.error(f"Error reading events: {str(e)}")
                    self.handle = None  # Force handle refresh
                    time.sleep(5)
                    continue

                time.sleep(1)  # Small delay to prevent high CPU usage

        except KeyboardInterrupt:
            self.logger.info("Login monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in login monitoring: {str(e)}")
        finally:
            if self.handle:
                try:
                    win32evtlog.CloseEventLog(self.handle)
                except:
                    pass

def main():
    """Main function"""
    print("\nLogin Monitor")
    print("=============")
    print("Monitoring:")
    print("- User login success/failure")
    print("- Login types and sources")
    print("- Remote access attempts")
    print("=============\n")
    
    monitor = LoginMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping login monitor...")

if __name__ == "__main__":
    main()