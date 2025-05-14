import { ipcMain, BrowserWindow } from 'electron';
import { supabase } from '../supabase/client';
import os from 'os';
import path from 'path';
import fs from 'fs';

/**
 * User Registry Manager for the main process
 * Handles user session registration, correlation, and communication with Supabase
 */
export class UserRegistryManager {
  private userId: string | null = null;
  private userEmail: string | null = null;
  private correlationId: string | null = null;
  private sessionId: string | null = null;
  private securityTier: string | null = null;
  private riskScore: number | null = null;
  private mainWindow: BrowserWindow | null = null;
  private deviceInfo: any = null;
  private lastActivityTime: Date = new Date();
  
  constructor(mainWindow: BrowserWindow) {
    this.mainWindow = mainWindow;
    this.setupIPCHandlers();
    this.initDeviceInfo();
    
    // Start periodic security tier check
    this.startSecurityTierCheck();
  }
  
  /**
   * Initialize device information
   */
  private initDeviceInfo() {
    try {
      this.deviceInfo = {
        platform: process.platform,
        osVersion: os.release(),
        hostname: os.hostname(),
        cores: os.cpus().length,
        memory: Math.round(os.totalmem() / (1024 * 1024 * 1024)),
        arch: process.arch
      };
    } catch (err) {
      console.error('Error getting device info:', err);
      this.deviceInfo = { error: 'Failed to get device info' };
    }
  }
  
  /**
   * Set up IPC handlers for communication with the renderer process
   */
  private setupIPCHandlers() {
    // Register a user session
    ipcMain.handle('user-registry:register-session', async (event, { userId, userEmail }) => {
      return this.registerUserSession(userId, userEmail);
    });
    
    // Update user activity
    ipcMain.handle('user-registry:update-activity', async () => {
      return this.updateUserActivity();
    });
    
    // Get the current correlation ID
    ipcMain.handle('user-registry:get-correlation-id', () => {
      return this.correlationId;
    });
    
    // Get the current security tier
    ipcMain.handle('user-registry:get-security-tier', () => {
      return {
        tier: this.securityTier,
        score: this.riskScore
      };
    });
  }
  
  /**
   * Handle messages from the Python process
   */
  public handlePythonMessage(messageStr: string) {
    try {
      const message = JSON.parse(messageStr);
      
      if (message.type === 'session_start') {
        // Store session information from Python
        const { user_id, session_id, correlation_id, device_info } = message.data;
        
        if (session_id) this.sessionId = session_id;
        if (correlation_id) this.correlationId = correlation_id;
        
        // Forward to renderer
        if (this.mainWindow) {
          this.mainWindow.webContents.send('python-process:message', message);
        }
        
        // Register this session with Supabase if we have a user ID
        if (user_id && this.userId && this.userId === user_id) {
          this.registerAuthEvent(device_info);
        }
      }
    } catch (err) {
      console.error('Error handling Python message:', err);
    }
  }
  
  /**
   * Register a user session
   */
  private async registerUserSession(userId: string, userEmail: string): Promise<{ success: boolean, correlationId?: string }> {
    try {
      this.userId = userId;
      this.userEmail = userEmail;
      
      // Create a correlation ID if not already set by Python
      if (!this.correlationId) {
        this.correlationId = `${userId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      }
      
      // Register auth event in Supabase
      await this.registerAuthEvent();
      
      // Get initial security tier
      await this.checkSecurityTier();
      
      return { 
        success: true, 
        correlationId: this.correlationId 
      };
    } catch (err) {
      console.error('Error registering user session:', err);
      return { success: false };
    }
  }
  
  /**
   * Register an authentication event in Supabase
   */
  private async registerAuthEvent(pythonDeviceInfo?: any) {
    if (!this.userId) return false;
    
    try {
      // Combine device info from both sources
      const combinedDeviceInfo = {
        ...this.deviceInfo,
        ...pythonDeviceInfo,
        appVersion: process.env.npm_package_version || 'unknown'
      };
      
      // Register the auth event in Supabase
      const { error } = await supabase
        .from('auth_events')
        .insert({
          user_id: this.userId,
          correlation_id: this.correlationId,
          session_id: this.sessionId,
          device_info: combinedDeviceInfo,
          timestamp: new Date().toISOString()
        });
        
      if (error) {
        console.error('Error registering auth event:', error);
        return false;
      }
      
      return true;
    } catch (err) {
      console.error('Error in registerAuthEvent:', err);
      return false;
    }
  }
  
  /**
   * Update user activity timestamp
   */
  private async updateUserActivity(): Promise<boolean> {
    if (!this.userId) return false;
    
    this.lastActivityTime = new Date();
    
    try {
      const { error } = await supabase
        .from('user_activity')
        .upsert({
          user_id: this.userId,
          last_seen: this.lastActivityTime.toISOString()
        }, {
          onConflict: 'user_id'
        });
        
      if (error) {
        console.error('Error updating user activity:', error);
        return false;
      }
      
      return true;
    } catch (err) {
      console.error('Error in updateUserActivity:', err);
      return false;
    }
  }
  
  /**
   * Check the user's security tier
   */
  private async checkSecurityTier() {
    if (!this.userId) return;
    
    try {
      const { data, error } = await supabase
        .from('user_security')
        .select('tier, risk_score, last_updated')
        .eq('id', this.userId)
        .single();
        
      if (error) {
        console.error('Error checking security tier:', error);
        return;
      }
      
      if (data) {
        const prevTier = this.securityTier;
        this.securityTier = data.tier;
        this.riskScore = data.risk_score;
        
        // Notify renderer if tier changed
        if (prevTier !== null && prevTier !== this.securityTier && this.mainWindow) {
          this.mainWindow.webContents.send('user-registry:security-tier-change', {
            tier: this.securityTier,
            previousTier: prevTier,
            score: this.riskScore
          });
        }
      }
    } catch (err) {
      console.error('Error in checkSecurityTier:', err);
    }
  }
  
  /**
   * Start periodic security tier check
   */
  private startSecurityTierCheck() {
    // Check security tier every 5 minutes
    setInterval(() => {
      if (this.userId) {
        this.checkSecurityTier();
      }
    }, 5 * 60 * 1000);
  }
  
  /**
   * Get user session data
   */
  public getUserSessionData() {
    return {
      userId: this.userId,
      userEmail: this.userEmail,
      correlationId: this.correlationId,
      sessionId: this.sessionId,
      securityTier: this.securityTier,
      riskScore: this.riskScore,
      lastActivity: this.lastActivityTime
    };
  }
}

export default UserRegistryManager; 