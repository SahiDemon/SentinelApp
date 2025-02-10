type NotificationType = 'success' | 'error' | 'info';

class NotificationManager {
    private static instance: NotificationManager;
    private activeNotification: HTMLElement | null = null;

    private constructor() {}

    static getInstance(): NotificationManager {
        if (!NotificationManager.instance) {
            NotificationManager.instance = new NotificationManager();
        }
        return NotificationManager.instance;
    }

    show(message: string, type: NotificationType): void {
        // Remove existing notification if any
        if (this.activeNotification) {
            this.activeNotification.remove();
        }

        // Create new notification
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        
        const icon = document.createElement('span');
        icon.className = 'notification-icon';
        
        const text = document.createElement('span');
        text.textContent = message;
        
        notification.appendChild(icon);
        notification.appendChild(text);
        
        document.body.appendChild(notification);
        this.activeNotification = notification;

        // Trigger animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        // Auto hide after 3 seconds
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
                if (this.activeNotification === notification) {
                    this.activeNotification = null;
                }
            }, 300);
        }, 3000);
    }
}

export const notificationManager = NotificationManager.getInstance();
