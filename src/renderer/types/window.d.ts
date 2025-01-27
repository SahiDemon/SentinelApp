export {};

declare global {
    interface Window {
        api: {
            getSystemStats: () => Promise<{ cpu: number; ram: number; storage: number; }>;
            minimizeWindow: () => void;
            closeWindow: () => void;
        }
    }
}
