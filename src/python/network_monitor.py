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
from ctypes import windll
import dns.resolver
import threading
import queue

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

class NetworkMonitor:
    def __init__(self, log_dir="logs"):
        """Initialize network monitor"""
        # Ensure we have admin rights before initialization
        if not is_admin():
            raise PermissionError("Administrator privileges required")
        
        self.logger = setup_logger('network_monitor', log_dir)
        self.known_connections = {}
        self.app_connections = defaultdict(set)
        self.domain_cache = defaultdict(set)  # Cache domains per process
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 1
        self.resolver.lifetime = 1
        
        # Web browsers to ignore
        self.browsers = {
            'chrome.exe', 'msedge.exe', 'firefox.exe', 'opera.exe', 
            'brave.exe', 'iexplore.exe', 'chromium.exe'
        }
        
        # System processes to ignore
        self.system_processes = {
            'svchost.exe', 'lsass.exe', 'System', 'services.exe',
            'wininit.exe', 'csrss.exe', 'spoolsv.exe'
        }

    def _resolve_domain(self, ip):
        """Resolve IP to domain name"""
        try:
            domain = socket.gethostbyaddr(ip)[0]
            return domain.lower()
        except:
            return ip

    def _get_process_info(self, pid):
        """Get detailed process information"""
        try:
            proc = psutil.Process(pid)
            return {
                'name': proc.name(),
                'exe': proc.exe(),
                'cmdline': ' '.join(proc.cmdline()) if proc.cmdline() else ''
            }
        except:
            return {'name': 'Unknown', 'exe': '', 'cmdline': ''}

    def _is_system_process(self, proc_name):
        """Check if process is a system process"""
        return proc_name.lower() in {p.lower() for p in self.system_processes}

    def _is_web_browser(self, proc_name):
        """Check if process is a web browser"""
        return proc_name.lower() in {b.lower() for b in self.browsers}

    def _format_message(self, proc_name, remote_addr, domain, status):
        """Format connection message with domain information"""
        msg_parts = [
            f"Network Activity",
            f"Process: {proc_name}"
        ]
        
        if domain and domain != remote_addr:
            msg_parts.append(f"Domain: {domain}")
            msg_parts.append(f"IP: {remote_addr}")
        else:
            msg_parts.append(f"Address: {remote_addr}")
            
        msg_parts.append(f"Status: {status}")
        
        # Add cached domains for this process
        if proc_name in self.domain_cache:
            recent_domains = list(self.domain_cache[proc_name])[-3:]  # Last 3 domains
            if recent_domains:
                domains_str = ", ".join(recent_domains)
                if len(self.domain_cache[proc_name]) > 3:
                    domains_str += f" (+{len(self.domain_cache[proc_name])-3} more)"
                msg_parts.append(f"Recent Domains: {domains_str}")
        
        return " | ".join(msg_parts)

    def monitor(self):
        """Start monitoring network connections"""
        try:
            self.logger.info("Starting network monitoring...")
            self.logger.info("Monitoring non-browser network connections...")

            while True:
                try:
                    current_connections = {}
                    
                    # Monitor network connections
                    for conn in psutil.net_connections(kind='inet'):
                        if not conn.pid or not conn.raddr:
                            continue
                            
                        proc_info = self._get_process_info(conn.pid)
                        proc_name = proc_info['name']
                        
                        # Skip system processes and browsers
                        if self._is_system_process(proc_name) or self._is_web_browser(proc_name):
                            continue
                            
                        remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}"
                        conn_key = f"{conn.pid}:{conn.laddr.port}"
                        
                        # Resolve domain
                        domain = self._resolve_domain(conn.raddr.ip)
                        if domain != conn.raddr.ip:  # If resolution successful
                            self.domain_cache[proc_name].add(domain)
                        
                        current_connections[conn_key] = {
                            'process': proc_name,
                            'remote_addr': remote_addr,
                            'domain': domain,
                            'status': conn.status
                        }
                        
                        # Log new connections
                        if conn_key not in self.known_connections:
                            self.known_connections[conn_key] = current_connections[conn_key]
                            msg = self._format_message(
                                proc_name, remote_addr, domain, conn.status
                            )
                            self.logger.info(msg)
                    
                    # Check for closed connections
                    for conn_key in list(self.known_connections.keys()):
                        if conn_key not in current_connections:
                            conn_info = self.known_connections[conn_key]
                            msg = f"Connection Closed | Process: {conn_info['process']} | Address: {conn_info['remote_addr']}"
                            self.logger.info(msg)
                            del self.known_connections[conn_key]
                    
                    # Clean up old domain cache (keep last 100 domains per process)
                    for proc in self.domain_cache:
                        if len(self.domain_cache[proc]) > 100:
                            self.domain_cache[proc] = set(list(self.domain_cache[proc])[-100:])
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.logger.error(f"Error monitoring network: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            self.logger.info("Network monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in network monitoring: {str(e)}")

def main():
    """Main function"""
    # Check for admin rights first, before any other initialization
    if not is_admin():
        print("\nThis application requires administrator privileges.")
        print("Please run as administrator.\n")
        sys.exit(1)

    print("\nNetwork Activity Monitor")
    print("======================")
    print("Monitoring:")
    print("- Application network connections")
    print("- Domain name resolution")
    print("- Connection tracking")
    print("\nFiltering:")
    print("- System processes")
    print("- Browser web traffic")
    print("======================\n")
    
    monitor = NetworkMonitor()
    
    try:
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nStopping network monitor...")

if __name__ == "__main__":
    main()