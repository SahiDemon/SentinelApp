import { contextBridge, ipcRenderer } from 'electron';

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld(
    'api', {
        send: (channel: string, data: any) => {
            // whitelist channels
            let validChannels = ['toMain', 'update-sentinel-user', 'minimize-window', 'close-window', 'exit-dialog-response'];
            if (validChannels.includes(channel)) {
                ipcRenderer.send(channel, data);
            }
        },
        receive: (channel: string, func: Function) => {
            let validChannels = ['fromMain', 'splash-screen-done', 'preserve-state', 'sentinel-output', 'sentinel-error', 'sentinel-stopped', 'sentinel-status-update', 'sentinel-start-failed'];
            if (validChannels.includes(channel)) {
                // Deliberately strip event as it includes `sender` 
                ipcRenderer.on(channel, (event, ...args) => func(...args));
            }
        },
        getSystemStats: (): Promise<{ cpu: number; ram: number; storage: string; }> => {
            return ipcRenderer.invoke('get-system-info');
        },
        minimizeWindow: () => {
            ipcRenderer.send('minimize-window');
        },
        closeWindow: () => {
            ipcRenderer.send('close-window');
        },
        updateSentinelUser: (userId: string) => {
            ipcRenderer.send('update-sentinel-user', userId);
        },
        checkSentinelStatus: (): Promise<{ 
            running: boolean;
            status: string;
            admin: boolean;
            requiresAdmin: boolean;
            lastError?: string;
            pid?: number;
            userId?: string;
        }> => {
            return ipcRenderer.invoke('check-sentinel-status');
        },
        // Helper methods to listen for specific events
        onSentinelStatusUpdate: (callback: Function) => {
            ipcRenderer.on('sentinel-status-update', (event, ...args) => callback(...args));
        },
        onSentinelOutput: (callback: Function) => {
            ipcRenderer.on('sentinel-output', (event, ...args) => callback(...args));
        },
        onSentinelError: (callback: Function) => {
            ipcRenderer.on('sentinel-error', (event, ...args) => callback(...args));
        },
        // New methods for log retrieval
        getSentinelLogs: (): Promise<{ success: boolean; logs?: string; message?: string; }> => {
            return ipcRenderer.invoke('get-sentinel-logs');
        },
        getPythonLogs: (): Promise<{ success: boolean; logs?: string; message?: string; }> => {
            return ipcRenderer.invoke('get-python-logs');
        },
        // New method to get monitor status directly
        getMonitorStatus: (): Promise<{ success: boolean; status?: any; message?: string; }> => {
            return ipcRenderer.invoke('get-monitor-status');
        }
    }
);
