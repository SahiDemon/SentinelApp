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
from urllib.parse import unquote, parse_qs, urlparse

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

def run_as_admin():
    """Attempt to restart the script with admin rights"""
    if is_admin():
        return True

    try:
        script = sys.argv[0]
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit(0)
    except Exception as e:
        print(f"Failed to elevate to admin: {str(e)}")
        sys.exit(1)

run_as_admin()

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
                    SELECT DISTINCT url, title, last_visit_time 
                    FROM urls 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                '''
            },
            'msedge.exe': {
                'name': 'Microsoft Edge',
                'path': os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History'),
                'query': '''
                    SELECT DISTINCT url, title, last_visit_time 
                    FROM urls 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                '''
            },
            'firefox.exe': {
                'name': 'Firefox',
                'path': os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles'),
                'query': '''
                    SELECT DISTINCT url, title, last_visit_date 
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

        self.known_domains = {
            '1e100.net': 'Google',
            'googleapis.com': 'Google APIs',
            'gstatic.com': 'Google Static',
            'googlevideo.com': 'Google Video',
            'cloudflare.com': 'Cloudflare',
            'cloudfront.net': 'Amazon CloudFront'
        }
        self.ignored_domains = {
            '1e100.net',
            'googleapis.com',
            'gstatic.com',
            'googlevideo.com',
            'cloudflare.com',
            'cloudfront.net',
            'amazonaws.com',
            'akadns.net'
        }
        
        # Enhanced search patterns
        self.search_patterns = {
            'google': {
                'pattern': r'google\.[^/]+/search\?.*q=([^&]+)',
                'domains': ['google.com', 'google.co.uk', 'google.ca']
            },
            'bing': {
                'pattern': r'bing\.com/search\?.*q=([^&]+)',
                'domains': ['bing.com']
            },
            'duckduckgo': {
                'pattern': r'duckduckgo\.com/\?q=([^&]+)',
                'domains': ['duckduckgo.com']
            }
        }
        
        # Enhanced site patterns with specific paths
        self.site_patterns = {
            'github.com': {
                'patterns': {
                    r'/settings(?:/.*)?$': 'GitHub Settings',
                    r'/([^/]+)/([^/]+)/settings': 'GitHub Repo Settings: {0}/{1}',
                    r'/([^/]+)/([^/]+)/pull/(\d+)': 'GitHub PR: {0}/{1}#{2}',
                    r'/([^/]+)/([^/]+)/issues/(\d+)': 'GitHub Issue: {0}/{1}#{2}',
                    r'/([^/]+)/([^/]+)$': 'GitHub Repo: {0}/{1}',
                    r'/([^/]+)$': 'GitHub Profile: {0}'
                }
            },
            'youtube.com': {
                'patterns': {
                    r'/watch\?v=([^&]+)': 'YouTube Video',
                    r'/playlist\?list=([^&]+)': 'YouTube Playlist',
                    r'/channel/([^/]+)': 'YouTube Channel',
                    r'/c/([^/]+)': 'YouTube Channel: {0}'
                }
            },
            'gmail.com': {
                'patterns': {
                    r'/#inbox': 'Gmail Inbox',
                    r'/#sent': 'Gmail Sent',
                    r'/#drafts': 'Gmail Drafts',
                    r'/compose': 'Gmail Compose'
                }
            }
        }

        # Replace the tracking sets with better ones
        self.processed_urls = set()  # Change back to simple set
        self.duplicate_timeout = 5  # Seconds to wait before logging same URL again
        
        # Add Google services pattern
        self.google_services = {
            'youtube.com': 'YouTube',
            'drive.google.com': 'Google Drive',
            'keep.google.com': 'Google Keep',
            'gemini.google.com': 'Google Gemini',
            'mail.google.com': 'Gmail',
            'docs.google.com': 'Google Docs'
        }

        # Add new tracking sets
        self.last_history_check = int(time.time() * 1000000)  # Microseconds
        self.history_check_interval = 5  # Check every 5 seconds

        # Add active browser tracking
        self.active_browsers = {}  # {browser_name: {'pid': pid, 'start_time': time}}
        self.monitoring_started = False

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

    def _is_meaningful_domain(self, domain):
        """Check if domain is meaningful (not a CDN or service domain)"""
        return not any(domain.endswith(ignored) for ignored in self.ignored_domains)

    def _clean_url(self, url):
        """Clean URL to get meaningful domain"""
        try:
            # Remove protocol
            url = re.sub(r'^https?://', '', url)
            # Remove path and query
            url = url.split('/')[0]
            # Remove port
            url = url.split(':')[0]
            return url.lower()
        except:
            return url

    def _resolve_domain(self, ip):
        """Resolve IP address to domain name with improved filtering"""
        try:
            domain = socket.gethostbyaddr(ip)[0].lower()
            # Try to get the actual website domain instead of CDN/service domain
            if not self._is_meaningful_domain(domain):
                return None
            return domain
        except:
            return None

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

    def _check_active_browsers(self):
        """Check which browsers are currently running"""
        current_browsers = {}
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                if proc.info['name'] in self.browsers:
                    browser_name = self.browsers[proc.info['name']]['name']
                    if browser_name not in current_browsers:
                        current_browsers[browser_name] = {
                            'pid': proc.info['pid'],
                            'start_time': proc.info['create_time']
                        }
                        # Log new browser detection
                        if browser_name not in self.active_browsers:
                            self.logger.info(f"Detected new {browser_name} instance (PID: {proc.info['pid']})")
            except:
                continue
                
        # Update active browsers
        self.active_browsers = current_browsers
        return len(current_browsers) > 0

    def _get_browser_history(self, browser_info, start_time):
        """Get browser history since browser was opened"""
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

            # Modify query to only get history since browser started
            if browser_info['name'] == 'Firefox':
                start_time_ms = int(start_time * 1000)  # Convert to milliseconds
                browser_info['query'] = '''
                    SELECT DISTINCT url, title, last_visit_date 
                    FROM moz_places 
                    WHERE last_visit_date > ? 
                    ORDER BY last_visit_date DESC 
                    LIMIT 50
                '''
            else:
                start_time_us = int(start_time * 1000000)  # Convert to microseconds
                browser_info['query'] = '''
                    SELECT DISTINCT url, title, last_visit_time 
                    FROM urls 
                    WHERE last_visit_time > ? 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                '''

            # Query the database
            urls = []
            try:
                with sqlite3.connect(temp_db, timeout=self.db_timeout) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(browser_info['query'], 
                        (start_time_ms if browser_info['name'] == 'Firefox' else start_time_us,))
                    urls = [(row['url'], row['title']) for row in cursor.fetchall()]
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
            return []

    def _should_log_url(self, browser_name, url, title):
        """Check if URL should be logged based on time and content"""
        try:
            current_time = time.time()
            key = f"{browser_name}:{url}:{title}"
            
            # Check if URL was recently logged
            if key in self.processed_urls:
                last_time = self.processed_urls[key]
                if current_time - last_time < self.duplicate_timeout:
                    return False
            
            self.processed_urls[key] = current_time
            return True
        except:
            return True

    def _clean_google_service_url(self, url):
        """Clean and categorize Google service URLs"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Handle Google services
            for service_domain, service_name in self.google_services.items():
                if domain.endswith(service_domain):
                    # Extract meaningful parts of the path
                    path = parsed.path.rstrip('/')
                    if path == '' or path == '/':
                        return service_name
                    elif '/drive/my-drive' in path:
                        return f"{service_name} - My Drive"
                    elif '/u/0' in path:
                        return service_name
                    elif path:
                        return f"{service_name} - {path.split('/')[-1]}"
                    return service_name
            
            return url
        except:
            return url

    def _parse_url(self, url):
        """Enhanced URL parsing with better activity detection"""
        try:
            # First check for Google services
            cleaned_service = self._clean_google_service_url(url)
            if cleaned_service != url:
                return cleaned_service
                
            # Rest of the existing parsing logic
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            path = parsed.path.lower()
            query = parse_qs(parsed.query)
            
            # Check for search queries
            for engine, info in self.search_patterns.items():
                if any(domain.endswith(d) for d in info['domains']):
                    match = re.search(info['pattern'], url)
                    if match:
                        search_query = unquote(match.group(1).replace('+', ' '))
                        return f"Searched on {engine.title()}: {search_query}"
            
            # Check for specific site patterns
            for site, info in self.site_patterns.items():
                if domain.endswith(site):
                    full_path = f"{path}{'?' + parsed.query if parsed.query else ''}"
                    for pattern, description in info['patterns'].items():
                        match = re.search(pattern, full_path)
                        if match:
                            # Format description with captured groups if any
                            if match.groups():
                                return description.format(*match.groups())
                            return description
            
            # Handle special cases
            if domain == 'linkedin.com' and '/in/' in path:
                return f"LinkedIn Profile: {path.split('/in/')[1].split('/')[0]}"
            elif domain == 'twitter.com' and len(path.split('/')) > 1:
                username = path.split('/')[1]
                if username and not username.startswith('?'):
                    return f"Twitter Profile: @{username}"
            
            # Default to cleaned domain with path for unknown patterns
            clean_path = path if path != '/' else ''
            return f"{domain}{clean_path}"
            
        except Exception as e:
            return url

    def _log_activity(self, browser_name, url, title=None, activity_type="Browser Activity"):
        """Log browser activity with enhanced URL parsing"""
        try:
            parsed_info = self._parse_url(url)
            log_key = f"{browser_name}:{parsed_info}:{title}"
            
            if log_key not in self.processed_urls:
                self.processed_urls.add(log_key)
                if title:
                    self.logger.info(
                        f"{activity_type} | {browser_name} | "
                        f"Activity: {parsed_info} | "
                        f"Title: {title}"
                    )
                else:
                    self.logger.info(
                        f"{activity_type} | {browser_name} | "
                        f"Activity: {parsed_info}"
                    )
        except Exception:
            pass

    def monitor(self):
        """Start monitoring browser network activity"""
        self.logger.info("Starting browser monitoring...")
        self.logger.info("Waiting for browsers to open...")
        
        try:
            while True:
                try:
                    # Check for active browsers
                    browsers_running = self._check_active_browsers()
                    
                    if not browsers_running:
                        if self.monitoring_started:
                            self.logger.info("No browsers running, waiting...")
                            self.monitoring_started = False
                        time.sleep(2)
                        continue
                    
                    # Start monitoring when first browser is detected
                    if not self.monitoring_started:
                        self.logger.info("Browser(s) detected, starting monitoring...")
                        self.monitoring_started = True
                        self.processed_urls.clear()  # Clear previous history
                    
                    current_time = time.time()
                    current_connections = defaultdict(set)
                    
                    # Check browser history for active browsers
                    for browser_name, info in self.active_browsers.items():
                        if current_time - self.last_checked.get(browser_name, 0) >= 30:
                            for proc_name, browser_info in self.browsers.items():
                                if browser_info['name'] == browser_name:
                                    history_entries = self._get_browser_history(
                                        browser_info, 
                                        info['start_time']
                                    )
                                    for url, title in history_entries:
                                        if url and self._is_meaningful_domain(self._clean_url(url)):
                                            self._log_activity(browser_name, url, title, "Browser History")
                            self.last_checked[browser_name] = current_time

                    # Monitor network connections for active browsers
                    for conn in psutil.net_connections(kind='inet'):
                        if not conn.pid or not conn.raddr:
                            continue
                            
                        proc_info = self._get_process_info(conn.pid)
                        if not proc_info or proc_info['name'] not in self.browsers:
                            continue
                        
                        browser_info = self.browsers[proc_info['name']]
                        browser_name = browser_info['name']
                        
                        # Only monitor active browsers
                        if browser_name not in self.active_browsers:
                            continue
                            
                        remote_ip = conn.raddr.ip
                        domain = self._resolve_domain(remote_ip)
                        if not domain:
                            continue

                        domain = self._clean_url(domain)
                        if not self._is_meaningful_domain(domain):
                            continue
                            
                        key = f"{browser_name}-{conn.pid}"
                        if domain not in self.last_connections[key]:
                            self._log_activity(browser_name, domain)
                        current_connections[key].add(domain)
                    
                    self.last_connections = current_connections
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