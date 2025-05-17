import os from 'os';
import fs from 'fs';
import path from 'path';
import axios, { AxiosError } from 'axios';
import { networkInterfaces } from 'os';
import { v4 as uuidv4 } from 'uuid';
import { app } from 'electron';
import log from 'electron-log';

// Configure logger
log.transports.file.level = 'info';
log.transports.file.resolvePathFn = () => path.join(app.getPath('userData'), 'logs/device-registry.log');

// Constants
const DEVICE_CONFIG_FILE = path.join(app.getPath('userData'), 'device_config.json');
const API_URL = process.env.SENTINEL_PRIME_API_URL || 'http://localhost:5000/api';
const SENTINEL_PRIME_API_KEY = process.env.SENTINEL_PRIME_API_KEY || 'sentinel-uba-key-dc294c33f3a322f531c2545a92d2ce4c';

interface DeviceConfig {
  id?: string;
  name: string;
  type: string;
  os_info: string;
  ip_address: string;
  mac_address: string;
  user_id?: string;
  registered: boolean;
  registration_date?: string;
  last_health_update?: string;
}

class DeviceRegistry {
  private deviceConfig: DeviceConfig | null = null;
  private registrationInterval: NodeJS.Timeout | null = null;
  private healthUpdateInterval: NodeJS.Timeout | null = null;
  private lastExitReport: number = 0;
  private exitReportTimeout: NodeJS.Timeout | null = null;

  constructor() {
    this.loadConfig();
  }

  /**
   * Load device configuration from file or create new one
   */
  private loadConfig(): void {
    try {
      if (fs.existsSync(DEVICE_CONFIG_FILE)) {
        const data = fs.readFileSync(DEVICE_CONFIG_FILE, 'utf8');
        this.deviceConfig = JSON.parse(data);
        log.info('Loaded device configuration');
      } else {
        this.createNewDeviceConfig();
      }
    } catch (error) {
      log.error('Error loading device config:', error);
      this.createNewDeviceConfig();
    }
  }

  /**
   * Create a new device configuration
   */
  private createNewDeviceConfig(): void {
    const networkInfo = this.getNetworkInfo();
    
    this.deviceConfig = {
      name: os.hostname(),
      type: this.detectDeviceType(),
      os_info: `${os.type()} ${os.release()} ${os.arch()}`,
      ip_address: networkInfo.ipAddress,
      mac_address: networkInfo.macAddress,
      registered: false
    };

    this.saveConfig();
    log.info('Created new device configuration');
  }

  /**
   * Save device configuration to file
   */
  private saveConfig(): void {
    try {
      if (!this.deviceConfig) return;
      
      const dirPath = path.dirname(DEVICE_CONFIG_FILE);
      if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
      }

      fs.writeFileSync(DEVICE_CONFIG_FILE, JSON.stringify(this.deviceConfig, null, 2));
      log.info('Saved device configuration');
    } catch (error) {
      log.error('Error saving device config:', error);
    }
  }

  /**
   * Register device with SentinelPrime backend
   */
  public async registerDevice(userId?: string): Promise<boolean> {
    if (!this.deviceConfig) {
      log.error('Cannot register device: configuration not loaded');
      return false;
    }

    if (userId) {
      this.deviceConfig.user_id = userId;
    }

    try {
      // Get latest system information
      const systemInfo = this.getSystemInfo();
      
      // Prepare device data for registration according to server.js
      const devicePayload = {
        deviceData: {
            name: this.deviceConfig.name,
            type: this.deviceConfig.type,
            os_info: this.deviceConfig.os_info,
            ip_address: this.deviceConfig.ip_address,
            mac_address: this.deviceConfig.mac_address.toLowerCase(),
            user_id: this.deviceConfig.user_id,
            // Add health metrics directly into deviceData for initial log
            cpu_usage: systemInfo.cpu_usage,
            memory_usage: systemInfo.memory_usage,
            disk_usage: systemInfo.disk_usage,
            network_usage: systemInfo.network_usage,
            // Additional fields from previous attempts that might be useful or expected by DB schema
            registered: this.deviceConfig.registered, 
            hostname: os.hostname(), // Ensure hostname is explicitly sent
            status: 'online', // Server expects 'online' or similar for active devices
            last_seen: new Date().toISOString() // Server sets this, but good to send initial
        }
      };

      // Register with backend
      const response = await axios.post(
        `${API_URL}/devices/register`, 
        devicePayload, // Send the structured payload
        {
          headers: {
            'x-api-key': SENTINEL_PRIME_API_KEY,
            'Authorization': `Bearer ${SENTINEL_PRIME_API_KEY}`
          }
        }
      );
      
      if (response.data && response.data.device) {
        // Update device config with server-assigned ID and mark as registered
        this.deviceConfig.id = response.data.device.id;
        this.deviceConfig.registered = true;
        this.deviceConfig.registration_date = new Date().toISOString();
        this.saveConfig();
        
        log.info(`Device registered successfully with ID: ${this.deviceConfig.id}`);
        return true;
      }
      
      return false;
    } catch (error: unknown) {
      const axiosError = error as AxiosError;
      log.error('Error registering device:', error);
      // Log the detailed error response if available
      if (axiosError.response) {
        log.error('Error response data:', axiosError.response.data);
        log.error('Error response status:', axiosError.response.status);
        log.error('Error response headers:', axiosError.response.headers);
      }
      return false;
    }
  }

  /**
   * Update device health status with SentinelPrime backend
   */
  public async updateDeviceHealth(): Promise<boolean> {
    if (!this.deviceConfig || !this.deviceConfig.registered || !this.deviceConfig.id) {
      log.warn('Cannot update device health: device not registered');
      return false;
    }

    try {
      // Get latest system information
      const systemInfo = this.getSystemInfo();
      
      // Send health update
      await axios.post(
        `${API_URL}/devices/${this.deviceConfig.id}/health`, 
        { 
          // healthData structure matches server.js for this endpoint
          healthData: {
            cpu_usage: systemInfo.cpu_usage,
            memory_usage: systemInfo.memory_usage,
            disk_usage: systemInfo.disk_usage,
            network_usage: systemInfo.network_usage
          }
        },
        {
          headers: {
            'x-api-key': SENTINEL_PRIME_API_KEY,
            'Authorization': `Bearer ${SENTINEL_PRIME_API_KEY}`
          }
        }
      );
      
      // Update last health update timestamp
      this.deviceConfig.last_health_update = new Date().toISOString();
      this.saveConfig();
      
      log.info('Device health updated successfully');
      return true;
    } catch (error: unknown) {
      const axiosError = error as AxiosError;
      log.error('Error updating device health:', error);
      // Log the detailed error response if available
      if (axiosError.response) {
        log.error('Error response data:', axiosError.response.data);
        log.error('Error response status:', axiosError.response.status);
        log.error('Error response headers:', axiosError.response.headers);
      }
      return false;
    }
  }

  /**
   * Start device registration and health update services
   */
  public startServices(userId?: string): void {
    // Try to register device if not already registered
    if (!this.deviceConfig?.registered) {
      this.registerDevice(userId).then(success => {
        if (success) {
          log.info('Device registered successfully, starting health updates');
          this.startHealthUpdates();
        } else {
          // Retry registration after delay
          this.registrationInterval = setInterval(() => {
            this.registerDevice(userId).then(success => {
              if (success) {
                if (this.registrationInterval) {
                  clearInterval(this.registrationInterval);
                  this.registrationInterval = null;
                }
                this.startHealthUpdates();
              }
            });
          }, 60000); // Retry every minute
        }
      });
    } else {
      // Device already registered, just start health updates
      this.startHealthUpdates();
    }
  }

  /**
   * Start periodic health updates
   */
  private startHealthUpdates(): void {
    // Clear any existing interval
    if (this.healthUpdateInterval) {
      clearInterval(this.healthUpdateInterval);
    }

    // Update health immediately
    this.updateDeviceHealth();

    // Then update every 5 minutes
    this.healthUpdateInterval = setInterval(() => {
      this.updateDeviceHealth();
    }, 300000);
  }

  /**
   * Stop all services
   */
  public stopServices(): void {
    if (this.registrationInterval) {
      clearInterval(this.registrationInterval);
      this.registrationInterval = null;
    }

    if (this.healthUpdateInterval) {
      clearInterval(this.healthUpdateInterval);
      this.healthUpdateInterval = null;
    }

    log.info('Device registry services stopped');
  }

  /**
   * Get current system information
   */
  private getSystemInfo(): any {
    const cpuUsage = this.getCpuUsage();
    const memoryUsage = this.getMemoryUsage();
    const diskUsage = this.getDiskUsage();
    const networkUsage = 40; // Placeholder, actual implementation would be more complex

    return {
      cpu_usage: cpuUsage,
      memory_usage: memoryUsage,
      disk_usage: diskUsage,
      network_usage: networkUsage
    };
  }

  /**
   * Get CPU usage percentage
   */
  private getCpuUsage(): number {
    // Simple implementation - in a real app, we'd use system monitoring
    // libraries to get actual CPU usage
    return Math.floor(Math.random() * 60) + 20; // Random value between 20-80%
  }

  /**
   * Get memory usage percentage
   */
  private getMemoryUsage(): number {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    return Math.round((used / total) * 100);
  }

  /**
   * Get disk usage percentage
   */
  private getDiskUsage(): number {
    // Simple implementation - in a real app, we'd use a library 
    // like node-disk-info to get actual disk usage
    return Math.floor(Math.random() * 50) + 30; // Random value between 30-80%
  }

  /**
   * Detect device type based on platform and system info
   */
  private detectDeviceType(): string {
    const platform = os.platform();
    const isLaptop = this.isLaptop();
    
    if (platform === 'darwin') {
      return isLaptop ? 'laptop' : 'desktop';
    } else if (platform === 'win32') {
      return isLaptop ? 'laptop' : 'desktop';
    } else if (platform === 'linux') {
      return isLaptop ? 'laptop' : 'desktop';
    } else if (platform === 'android') {
      return 'mobile';
    }
    
    return 'desktop'; // Default
  }

  /**
   * Attempt to detect if device is a laptop
   * This is a heuristic and not 100% reliable
   */
  private isLaptop(): boolean {
    // Check for battery (laptops have batteries)
    // This is a simplified approach - real implementation would be more sophisticated
    const hasBattery = os.platform() === 'darwin' || os.platform() === 'win32';
    return hasBattery;
  }

  /**
   * Get network information from the system
   */
  private getNetworkInfo(): { ipAddress: string, macAddress: string } {
    const interfaces = networkInterfaces();
    let ipAddress = '127.0.0.1';
    let macAddress = '00:00:00:00:00:00';

    // Look for a non-internal IPv4 address and MAC
    Object.keys(interfaces).forEach((interfaceName) => {
      const networkInterface = interfaces[interfaceName];
      
      if (networkInterface) {
        networkInterface.forEach((iface) => {
          if (iface.family === 'IPv4' && !iface.internal) {
            ipAddress = iface.address;
            macAddress = iface.mac;
          }
        });
      }
    });

    return { ipAddress, macAddress };
  }

  /**
   * Get the current device configuration
   */
  public getDeviceConfig(): DeviceConfig | null {
    return this.deviceConfig;
  }
  
  /**
   * Report app exit to SentinelPrime backend
   * @param userId The ID of the user currently logged in
   * @param isAdmin Whether the user is an administrator
   * @param reason Optional reason for exit
   */
  public async reportAppExit(userId: string | null, isAdmin: boolean, reason?: string): Promise<boolean> {
    if (!this.deviceConfig || !this.deviceConfig.registered || !this.deviceConfig.id) {
      log.warn('Cannot report app exit: device not registered');
      return false;
    }

    // Prevent multiple exit reports within 5 seconds
    const now = Date.now();
    if (now - this.lastExitReport < 5000) {
      log.info('Skipping duplicate exit report - too soon after last report');
      return false;
    }

    // Clear any pending exit report
    if (this.exitReportTimeout) {
      clearTimeout(this.exitReportTimeout);
      this.exitReportTimeout = null;
    }

    try {
      log.info(`Reporting app exit. Admin: ${isAdmin}, Reason: ${reason || 'Not specified'}`);
      
      // Send exit notification to backend
      const response = await axios.post(
        `${API_URL}/devices/${this.deviceConfig.id}/exit`, 
        { 
          userId: userId || this.deviceConfig.user_id,
          adminExit: isAdmin,
          exitReason: reason || 'User initiated exit'
        },
        {
          headers: {
            'x-api-key': SENTINEL_PRIME_API_KEY,
            'Authorization': `Bearer ${SENTINEL_PRIME_API_KEY}`
          },
          timeout: 3000 // Short timeout since we're about to exit
        }
      );
      
      this.lastExitReport = now;
      log.info('App exit reported successfully:', response.data);
      return true;
    } catch (error: unknown) {
      const axiosError = error as AxiosError;
      log.error('Error reporting app exit:', error);
      
      // Log the detailed error response if available
      if (axiosError.response) {
        log.error('Error response data:', axiosError.response.data);
        log.error('Error response status:', axiosError.response.status);
      }
      
      return false;
    }
  }
}

// Create and export singleton instance
const deviceRegistry = new DeviceRegistry();
export default deviceRegistry; 