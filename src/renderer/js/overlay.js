class LoadingOverlay {
    constructor() {
        this.overlay = null;
        this.messages = [
            'Initializing Sentinel Core Systems...',
            'Establishing Secure Connections...',
            'Loading Security Protocols...',
            'Activating Defense Mechanisms...',
            'System Ready'
        ];
        this.currentMessageIndex = 0;
    }

    create() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'loading-overlay';
        
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        
        const loadingText = document.createElement('div');
        loadingText.className = 'loading-text';
        
        const statusText = document.createElement('div');
        statusText.className = 'system-status';
        
        this.overlay.appendChild(spinner);
        this.overlay.appendChild(loadingText);
        this.overlay.appendChild(statusText);
        
        document.body.appendChild(this.overlay);
        
        return this;
    }

    async start() {
        if (!this.overlay) {
            this.create();
        }

        const loadingText = this.overlay.querySelector('.loading-text');
        const statusText = this.overlay.querySelector('.system-status');
        
        for (let message of this.messages) {
            loadingText.textContent = message;
            statusText.textContent = 'Processing...';
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        setTimeout(() => {
            this.overlay.classList.add('fade-out');
            setTimeout(() => {
                this.overlay.remove();
            }, 500);
        }, 1000);
    }
}

export default LoadingOverlay;
