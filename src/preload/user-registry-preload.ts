import { contextBridge, ipcRenderer } from 'electron';

// Define the user registry API
contextBridge.exposeInMainWorld('userRegistry', {
  /**
   * Register a user session
   */
  registerUserSession: (userId: string, userEmail: string) => {
    return ipcRenderer.invoke('user-registry:register-session', { userId, userEmail });
  },
  
  /**
   * Update user activity
   */
  updateActivity: () => {
    return ipcRenderer.invoke('user-registry:update-activity');
  },
  
  /**
   * Get the current user's correlation ID for logs
   */
  getCorrelationId: () => {
    return ipcRenderer.invoke('user-registry:get-correlation-id');
  },
  
  /**
   * Get the current user's security tier
   */
  getSecurityTier: () => {
    return ipcRenderer.invoke('user-registry:get-security-tier');
  },
  
  /**
   * Subscribe to security tier changes
   */
  onSecurityTierChange: (callback: (data: any) => void) => {
    const subscription = (event: any, data: any) => callback(data);
    ipcRenderer.on('user-registry:security-tier-change', subscription);
    
    // Return a function to unsubscribe
    return () => {
      ipcRenderer.removeListener('user-registry:security-tier-change', subscription);
    };
  },
  
  /**
   * Handle messages from the Python process
   */
  onPythonMessage: (callback: (data: any) => void) => {
    const subscription = (event: any, data: any) => callback(data);
    ipcRenderer.on('python-process:message', subscription);
    
    // Return a function to unsubscribe
    return () => {
      ipcRenderer.removeListener('python-process:message', subscription);
    };
  }
}); 