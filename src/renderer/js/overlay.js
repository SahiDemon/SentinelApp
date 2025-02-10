class LoadingOverlay {
    constructor() {
        this.overlay = null;
        this.messages = [
            'INITIALIZING SENTINEL CORE',
            'SYSTEM OPERATIONAL'
        ];
    }

    create() {
        // Don't show overlay on page refresh
        if (sessionStorage.getItem('sentinel_dashboard_state') === 'visible' && performance.navigation.type === 1) {
            return this;
        }

        this.overlay = document.createElement('div');
        this.overlay.className = 'loading-overlay';
        
        const content = document.createElement('div');
        content.className = 'loading-content';

        // Add logo container
        const logoContainer = document.createElement('div');
        logoContainer.className = 'logo-container';
        
        const logo = document.createElement('img');
        logo.src = '../assets/sentinalprime.png';
        logo.alt = 'Sentinel Logo';
        logoContainer.appendChild(logo);
        
        const loadingLine = document.createElement('div');
        loadingLine.className = 'loading-line';
        
        const loadingText = document.createElement('div');
        loadingText.className = 'loading-text';
        
        content.appendChild(logoContainer);
        content.appendChild(loadingText);
        content.appendChild(loadingLine);
        this.overlay.appendChild(content);
        
        document.body.appendChild(this.overlay);
        
        return this;
    }

    async start() {
        if (!this.overlay) {
            this.create();
        }

        // If no overlay was created (due to refresh), just return
        if (!this.overlay) {
            return;
        }

        const loadingText = this.overlay.querySelector('.loading-text');
        const loadingLine = this.overlay.querySelector('.loading-line');
        
        // Show first message
        await new Promise(resolve => setTimeout(resolve, 500)); // Wait for logo animation
        loadingText.textContent = this.messages[0];
        
        // Wait for 3 seconds with the loading animation
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // Show completion state
        loadingLine.classList.add('complete');
        loadingText.textContent = this.messages[1];
        loadingText.classList.add('system-operational');
        
        // Wait for completion animation
        await new Promise(resolve => setTimeout(resolve, 1200));
        
        // Slide out overlay
        this.overlay.classList.add('complete');
        
        // Remove overlay after animation
        setTimeout(() => {
            this.overlay.remove();
        }, 1000);
    }
}

export default LoadingOverlay;
