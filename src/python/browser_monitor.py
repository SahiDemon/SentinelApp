import psutil
import time
import os
import logging
import socket
import ctypes
import sys
import json
import sqlite3
import shutil
import tempfile
import requests
from datetime import datetime, timezone
from urllib.parse import unquote, parse_qs, urlparse
import urllib3
from opensearch_logger import OpenSearchLogger
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def setup_logger(name, log_dir="logs"):
    """Set up a JSON logger"""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        return logger  # Prevent duplicate handlers
    
    logger.setLevel(logging.INFO)
    
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            if isinstance(record.msg, dict):
                log_entry = {
                    'timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                    'level': record.levelname,
                    **record.msg
                }
                return json.dumps(log_entry)
            return super().format(record)
    
    file_handler = logging.FileHandler(os.path.join(log_dir, f"{name}.json"))
    file_handler.setFormatter(JSONFormatter())

    logger.addHandler(file_handler)
    
    return logger

class BrowserMonitor:
    def __init__(self, log_dir="logs", electron_user_id=None):
        """Initialize browser monitor"""
        self.logger = setup_logger('browser_monitor', log_dir)
        self.opensearch_logger = OpenSearchLogger(electron_user_id=electron_user_id)
        self.logger.info({"message": "Browser Monitor initialized. Attempting to connect to OpenSearch..."})
        if not self.opensearch_logger.client:
            self.logger.warning({"message": "Failed to connect to OpenSearch. Logs will not be sent."})
        else:
            self.logger.info({"message": "OpenSearch connection successful."})

        self.browsers = {
            'chrome.exe': {'name': 'Google Chrome', 'history_path': os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\History')},
            'msedge.exe': {'name': 'Microsoft Edge', 'history_path': os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History')},
            'firefox.exe': {'name': 'Firefox', 'history_path': self._get_firefox_db()},
        }
        
        self.active_browsers = set()  # Tracks running browsers
        self.last_logged = set()  # Prevents duplicate logs

    def _get_firefox_db(self):
        """Find Firefox history database only if Firefox is installed."""
        profiles_dir = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
        
        if not os.path.exists(profiles_dir):  # Check if Firefox is installed
            return None

        for profile in os.listdir(profiles_dir):
            history_db = os.path.join(profiles_dir, profile, 'places.sqlite')
            if os.path.exists(history_db):
                return history_db

        return None  # Return None if no database is found


    def _copy_db(self, src_path):
        """Create a temporary copy of the database to avoid locks"""
        if not os.path.exists(src_path):
            return None
        temp_path = os.path.join(tempfile.gettempdir(), f'temp_history_{os.getpid()}.db')
        try:
            shutil.copy2(src_path, temp_path)
            return temp_path
        except:
            return None

    def _get_browser_history(self, browser_name, history_path):
        """Retrieve browsing history from browser's SQLite database"""
        temp_db = self._copy_db(history_path)
        if not temp_db:
            return []

        query = "SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 50"
        urls = []
        try:
            with sqlite3.connect(temp_db, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                urls = [(row[0], row[1]) for row in cursor.fetchall()]
        except sqlite3.Error:
            pass
        finally:
            try:
                os.remove(temp_db)
            except:
                pass

        return urls

    def _parse_url(self, url):
        """Extract meaningful activity from a URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            path = parsed.path.lower()
            
            if 'search' in path or 'q=' in url:
                query_params = parse_qs(parsed.query)
                if 'q' in query_params:
                    return f"Search: {unquote(query_params['q'][0])}"
            
            return f"{domain}{path}" if path and path != "/" else domain
        except:
            return url

    def _should_log(self, browser_name, activity_type, url):
        """Prevent duplicate logs"""
        key = f"{browser_name}:{activity_type}:{url}"
        if key in self.last_logged:
            return False
        self.last_logged.add(key)
        return True

    def _log_activity(self, browser_name, url, title, activity_type="Browser History"):
        """Log and send data to OpenSearch"""
        parsed_url = self._parse_url(url)
        if not self._should_log(browser_name, activity_type, parsed_url):
            return  # Prevent duplicate logging
        
        file_log_data = {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'browser': browser_name,
            'activity_type': activity_type,
            'url': parsed_url,
            'title': title if title else ''
        }
        self.logger.info(file_log_data)

        if self.opensearch_logger.client:
            event_details = {
                "browser": browser_name,
                "activity_type": activity_type,
                "url": parsed_url,
                "title": title if title else ''
            }
            event_details = {k: v for k, v in event_details.items() if v is not None}
            self.opensearch_logger.log(
                monitor_type="browser_monitor",
                event_type="browser_history_added",
                event_details=event_details
            )

    def _detect_browsers(self):
        """Detects running browsers and updates active list"""
        current_browsers = set()
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] in self.browsers:
                current_browsers.add(proc.info['name'])
        
        self.active_browsers = current_browsers
        return len(current_browsers) > 0

    def monitor(self):
        """Monitor browser history"""
        while True:
            if self._detect_browsers():
                for browser in self.active_browsers:
                    browser_name = self.browsers[browser]['name']
                    history_path = self.browsers[browser]['history_path']

                    if history_path:
                        history_entries = self._get_browser_history(browser_name, history_path)
                        for url, title in history_entries:
                            self._log_activity(browser_name, url, title)
            
            time.sleep(5)  # Check every 5 seconds

def main():
    """Main function"""
    print("\nEnterprise Browser Monitor")
    print("===========================")
    print("Tracking starts when a browser is detected.")
    print("===========================\n")

    monitor = BrowserMonitor()
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping browser monitor...")

if __name__ == "__main__":
    main()
