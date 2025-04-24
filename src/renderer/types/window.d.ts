export {};

declare global {
    interface Window {
        api: {
            send: (channel: string, data?: any) => void;
            receive: (channel: string, func: Function) => void;
            getSystemStats: () => Promise<{ cpu: number; ram: number; storage: string; }>;
            minimizeWindow: () => void;
            closeWindow: () => void;
            updateSentinelUser: (userId: string) => void;
            checkSentinelStatus: () => Promise<{ 
                running: boolean; 
                admin?: boolean;
                adminRequired?: boolean;
                lastError?: string;
                pid?: number;
                monitors?: Record<string, boolean>;
                user_id?: string;
            }>;
        }
    }
}
