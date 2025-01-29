import psutil
import time
import os
import logging
import socket
import ctypes
import sys
from datetime import datetime
from collections import defaultdict
import re
import sqlite3
import shutil
import tempfile
from pathlib import Path

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

def is_admin():
    """Check if script is running with admin rights"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class BrowserMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize browser monitor"""
        if not is_admin():
            raise PermissionError("Administrator privileges required")
            
        self.logger = setup_logger('browser_monitor', log_dir)
        self.browsers = {
            'chrome.exe': {
                'name': 'Google Chrome',
                'path': os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\History'),
                'query': '''
                    SELECT url, title, last_visit_time 
                    FROM urls 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                '''
            },
            'msedge.exe': {
                'name': 'Microsoft Edge',
                'path': os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History'),
                'query': '''
                    SELECT url, title, last_visit_time 
                    FROM urls 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                '''
            },
            'firefox.exe': {
                'name': 'Firefox',
                'path': os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles'),
                'query': '''
                    SELECT url, title, last_visit_date 
                    FROM moz_places 
                    ORDER BY last_visit_date DESC 
                    LIMIT 50
                '''
            },
            'opera.exe': {'name': 'Opera'},
            'brave.exe': {'name': 'Brave'}
        }
        
        self.web_ports = {80, 443, 8080, 8443}
        self.last_connections = defaultdict(set)
        self.url_history = defaultdict(set)
        self.last_checked = defaultdict(int)
        self.db_errors = defaultdict(int)
        self.db_timeout = 5000  # 5 seconds
        self.max_db_errors = 3  # Max errors before skipping a browser

    def _get_process_info(self, pid):
        """Get process information"""
        try:
            proc = psutil.Process(pid)
            return {
                'name': proc.name(),
                'cmdline': ' '.join(proc.cmdline()) if proc.cmdline() else ''
            }
        except:
            return None

    def _resolve_domain(self, ip):
        """Resolve IP address to domain name"""
        try:
            domain = socket.gethostbyaddr(ip)[0]
            return domain.lower()
        except:
            return ip

    def _get_firefox_db(self):
        """Get Firefox history database path"""
        profiles_dir = Path(os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles'))
        if profiles_dir.exists():
            for profile in profiles_dir.glob('*.default*'):
                history_db = profile / 'places.sqlite'
                if history_db.exists():
                    return str(history_db)
        return None

    def _copy_db(self, src_path):
        """Create a temporary copy of database to avoid locks"""
        if not os.path.exists(src_path):
            return None
            
        temp_path = os.path.join(tempfile.gettempdir(), f'temp_history_{os.getpid()}.db')
        try:
            retries = 3
            while retries > 0:
                try:
                    shutil.copy2(src_path, temp_path)
                    return temp_path
                except PermissionError:
                    time.sleep(1)
                    retries -= 1
            return None
        except:
            return None

    def _get_browser_history(self, browser_info):
        """Get URLs from browser history database"""
        try:
            if not browser_info.get('path') or not browser_info.get('query'):
                return []

            # Skip if too many errors
            if self.db_errors[browser_info['name']] >= self.max_db_errors:
                return []

            # Get database path
            db_path = browser_info['path']
            if browser_info['name'] == 'Firefox':
                db_path = self._get_firefox_db()
            
            if not db_path:
                return []

            # Create temporary copy
            temp_db = self._copy_db(db_path)
            if not temp_db:
                self.db_errors[browser_info['name']] += 1
                return []

            # Query the database
            urls = []
            try:
                with sqlite3.connect(temp_db, timeout=self.db_timeout) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(browser_info['query'])
                    urls = [row[0] for row in cursor.fetchall()]
                self.db_errors[browser_info['name']] = 0  # Reset error count
            except sqlite3.Error as e:
                self.db_errors[browser_info['name']] += 1
            finally:
                try:
                    os.remove(temp_db)
                except:
                    pass

            return urls

        except Exception as e:
            self.logger.error(f"Error reading {browser_info['name']} history: {str(e)}")
            self.db_errors[browser_info['name']] += 1
            return []

    def monitor(self):
        """Start monitoring browser network activity"""
        self.logger.info("Starting browser monitoring...")
        self.logger.info("Tracking browser activity...")

        try:
            while True:
                try:
                    current_connections = defaultdict(set)
                    
                    # Monitor network connections
                    for conn in psutil.net_connections(kind='inet'):
                        if not conn.pid or not conn.raddr:
                            continue
                            
                        proc_info = self._get_process_info(conn.pid)
                        if not proc_info or proc_info['name'] not in self.browsers:
                            continue
                        
                        browser_info = self.browsers[proc_info['name']]
                        browser_name = browser_info['name']
                        remote_ip = conn.raddr.ip
                        remote_port = conn.raddr.port
                        
                        # Skip non-web ports
                        if remote_port not in self.web_ports:
                            continue
                            
                        # Get domain name
                        domain = self._resolve_domain(remote_ip)
                        
                        # Add to current connections
                        key = f"{browser_name}-{conn.pid}"
                        current_connections[key].add(f"{domain}:{remote_port}")
                        
                        # Log new connections
                        if domain not in {d.split(':')[0] for d in self.last_connections[key]}:
                            self.logger.info(
                                f"Browser Activity | {browser_name} | "
                                f"Domain: {domain} | "
                                f"Port: {remote_port}"
                            )
                    
                    # Update connections
                    self.last_connections = current_connections

                    # Check browser history periodically
                    current_time = time.time()
                    for proc_name, browser_info in self.browsers.items():
                        if current_time - self.last_checked[proc_name] >= 30:
                            urls = self._get_browser_history(browser_info)
                            for url in urls:
                                if url not in self.url_history[browser_info['name']]:
                                    self.url_history[browser_info['name']].add(url)
                                    self.logger.info(
                                        f"Browser History | {browser_info['name']} | "
                                        f"URL: {url}"
                                    )
                            self.last_checked[proc_name] = current_time
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.logger.error(f"Error monitoring browsers: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            self.logger.info("Browser monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in browser monitoring: {str(e)}")

def main():
    """Main function"""
    if not is_admin():
        print("\nThis application requires administrator privileges.")
        print("Please run as administrator.\n")
        sys.exit(1)

    print("\nBrowser Activity Monitor")
    print("=====================")
    print("Tracking:")
    print("- Browser connections")
    print("- Domain names")
    print("- Browser history")
    print("\nSupported Browsers:")
    for browser in BrowserMonitor().browsers.values():
        if 'name' in browser:
            print(f"- {browser['name']}")
    print("=====================\n")
    
    monitor = BrowserMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping browser monitor...")

if __name__ == "__main__":
    main()