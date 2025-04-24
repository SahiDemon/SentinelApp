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
from opensearch_logger import OpenSearchLogger

def is_admin():
    """Check if script is running with admin rights"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class NetworkMonitor:
    def __init__(self, electron_user_id=None):
        """Initialize network monitor"""
        # Ensure we have admin rights before initialization
        if not is_admin():
            raise PermissionError("Administrator privileges required")
        
        self.opensearch_logger = OpenSearchLogger(electron_user_id=electron_user_id)
        print("Network Monitor initialized. Attempting to connect to OpenSearch...")
        if not self.opensearch_logger.client:
            print("WARNING: Failed to connect to OpenSearch. Logs will not be sent.")
        else:
            print("OpenSearch connection successful.")
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

    def monitor(self):
        """Start monitoring network connections"""
        try:
            print("Starting network monitoring...")
            print("Monitoring non-browser network connections...")

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
                        if proc_name.lower() in {p.lower() for p in self.system_processes} or \
                           proc_name.lower() in {b.lower() for b in self.browsers}:
                            continue
                            
                        remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}"
                        local_addr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None
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
                            event_details = {
                                "process_pid": conn.pid,
                                "process_name": proc_name,
                                "process_exe": proc_info.get('exe'),
                                "local_address": local_addr,
                                "remote_address": remote_addr,
                                "remote_domain": domain if domain != conn.raddr.ip else None,
                                "connection_status": conn.status,
                                "protocol": conn.type # SOCK_STREAM (TCP) or SOCK_DGRAM (UDP)
                            }
                            event_details = {k: v for k, v in event_details.items() if v is not None and v != ''}
                            self.opensearch_logger.log(
                                monitor_type="network_monitor",
                                event_type="network_connection_established",
                                event_details=event_details
                            )
                    
                    # Check for closed connections
                    for conn_key in list(self.known_connections.keys()):
                        if conn_key not in current_connections:
                            conn_info = self.known_connections[conn_key]
                            # Re-fetch proc info in case it changed?
                            # No, use cached info for the closed connection
                            proc_details = self._get_process_info(int(conn_key.split(':')[0])) # Get pid from key
                            event_details = {
                                "process_pid": int(conn_key.split(':')[0]),
                                "process_name": conn_info.get('process'),
                                "process_exe": proc_details.get('exe'),
                                "local_address": conn_key.split(':', 1)[1], # Approximated from key
                                "remote_address": conn_info.get('remote_addr'),
                                "remote_domain": conn_info.get('domain') if conn_info.get('domain') != conn_info.get('remote_addr', '').split(':')[0] else None,
                                "connection_status": "CLOSED" # Explicitly set status
                            }
                            event_details = {k: v for k, v in event_details.items() if v is not None and v != ''}
                            self.opensearch_logger.log(
                                monitor_type="network_monitor",
                                event_type="network_connection_closed",
                                event_details=event_details
                            )
                            del self.known_connections[conn_key]
                    
                    # Clean up old domain cache (keep last 100 domains per process)
                    for proc in self.domain_cache:
                        if len(self.domain_cache[proc]) > 100:
                            self.domain_cache[proc] = set(list(self.domain_cache[proc])[-100:])
                    
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"ERROR: Error monitoring network: {str(e)}")
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            print("Network monitoring stopped")
        except Exception as e:
            print(f"ERROR: Error in network monitoring: {str(e)}")

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