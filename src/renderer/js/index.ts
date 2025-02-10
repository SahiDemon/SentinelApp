import { handleLogin as login, handleLogout as logout, getUserSecurityTier, getCurrentUser } from './auth.js';
import { notificationManager } from './notifications.js';
const { ipcRenderer } = require('electron');

// Key for storing dashboard state
const DASHBOARD_STATE_KEY = 'sentinel_dashboard_state';

async function handleLogin() {
    const username = document.getElementById('username') as HTMLInputElement;
    const password = document.getElementById('password') as HTMLInputElement;
    const rememberMe = document.getElementById('rememberMe') as HTMLInputElement;
    const errorElement = document.getElementById('loginError')!;
    errorElement.textContent = '';
    
    try {
        notificationManager.show('Login in progress...', 'info');
        const result = await login(username.value, password.value, rememberMe.checked);
        if (result.success) {
            notificationManager.show('Login successful', 'success');
            document.getElementById('loginContainer')!.classList.remove('active');
            document.getElementById('dashboard')!.classList.add('active');
            
            // Show loading overlay only for fresh logins
            if (!document.referrer.includes('index.html')) {
                (window as any).showDashboardLoadingOverlay();
            }
            
            // Set user email in greeting
            const user = await getCurrentUser();
            if (user?.email) {
                document.getElementById('userEmail')!.textContent = user.email;
            }
            
            await init();
            sessionStorage.setItem(DASHBOARD_STATE_KEY, 'visible');
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Login failed';
        notificationManager.show(errorMessage, 'error');
        errorElement.textContent = errorMessage;
    }
}

async function handleLogout() {
    try {
        notificationManager.show('Logging out...', 'info');
        await logout();
        sessionStorage.removeItem(DASHBOARD_STATE_KEY);
        notificationManager.show('Logged out successfully', 'success');
        document.getElementById('dashboard')!.classList.remove('active');
        document.getElementById('loginContainer')!.classList.add('active');
        (document.getElementById('username') as HTMLInputElement).value = '';
        (document.getElementById('password') as HTMLInputElement).value = '';
        document.getElementById('loginError')!.textContent = '';
    } catch (error) {
        notificationManager.show('Logout failed', 'error');
    }
}

async function fetchSystemInfo() {
    const cpuUsageElement = document.getElementById('cpu-usage');
    const ramUsageElement = document.getElementById('ram-usage');
    const storageInfoElement = document.getElementById('storage-info');

    try {
        const info = await ipcRenderer.invoke('get-system-info');
        
        if (cpuUsageElement) {
            cpuUsageElement.textContent = typeof info.cpu === 'number' ? 
                info.cpu.toFixed(1) : 'N/A';
        }

        if (ramUsageElement) {
            ramUsageElement.textContent = typeof info.ram === 'number' ? 
                info.ram.toFixed(1) : 'N/A';
        }

        if (storageInfoElement) {
            storageInfoElement.textContent = info.storage || 'N/A';
        }
    } catch (error) {
        if (cpuUsageElement) cpuUsageElement.textContent = 'N/A';
        if (ramUsageElement) ramUsageElement.textContent = 'N/A';
        if (storageInfoElement) storageInfoElement.textContent = 'N/A';
    }
}

async function init() {
    const securityInfo = await getUserSecurityTier();
    const tierElement = document.getElementById('securityTier');
    if (tierElement) {
        tierElement.textContent = securityInfo.tier;
        tierElement.className = `tier ${securityInfo.tier}`;
    }
    
    const statusElement = document.getElementById('statusDescription');
    if (statusElement) {
        statusElement.textContent = securityInfo.description;
    }

    await fetchSystemInfo();
    setInterval(fetchSystemInfo, 5000); // Update system info every 5 seconds
}

// Check for existing session on startup
async function checkSession() {
    try {
        // Check if we're coming back from a refresh
        const savedState = sessionStorage.getItem(DASHBOARD_STATE_KEY);
        if (savedState === 'visible') {
            document.getElementById('loginContainer')!.classList.remove('active');
            document.getElementById('dashboard')!.classList.add('active');
            const user = await getCurrentUser();
            if (user?.email) {
                document.getElementById('userEmail')!.textContent = user.email;
            }
            await init();
            return;
        }

        notificationManager.show('Checking session...', 'info');
        const user = await getCurrentUser();
        if (user) {
            notificationManager.show('Auto-login successful', 'success');
            document.getElementById('loginContainer')!.classList.remove('active');
            document.getElementById('dashboard')!.classList.add('active');
            sessionStorage.setItem(DASHBOARD_STATE_KEY, 'visible');
            
            // Don't show overlay immediately, wait for splash screen signal
            const showOverlay = () => {
                (window as any).showDashboardLoadingOverlay();
            };
            
            // If this is a fresh start (not a refresh), wait for splash screen
            if (!document.referrer.includes('index.html')) {
                ipcRenderer.once('splash-screen-done', showOverlay);
            }
            
            document.getElementById('userEmail')!.textContent = user.email || '';
            await init();
        }
    } catch (error) {
        console.error('Session check failed:', error);
        notificationManager.show('Auto-login failed', 'error');
        sessionStorage.removeItem(DASHBOARD_STATE_KEY);
    }
}

// Handle page reloads
ipcRenderer.on('preserve-state', () => {
    if (document.getElementById('dashboard')!.style.display === 'block') {
        sessionStorage.setItem(DASHBOARD_STATE_KEY, 'visible');
    } else {
        sessionStorage.removeItem(DASHBOARD_STATE_KEY);
    }
});

// Theme management
function initializeTheme() {
    const savedTheme = localStorage.getItem('sentinel-theme') || 'cyberpunk';
    document.body.className = `theme-${savedTheme}`;
    
    // Update active button
    document.querySelectorAll('.theme-button').forEach(button => {
        const themeButton = button as HTMLButtonElement;
        if (themeButton.getAttribute('data-theme') === savedTheme) {
            themeButton.classList.add('active');
        } else {
            themeButton.classList.remove('active');
        }
    });
}

function handleThemeSwitch(event: Event) {
    const target = event.target as HTMLElement;
    const themeButton = target.closest('.theme-button') as HTMLButtonElement;
    if (!themeButton) return;
    
    const theme = themeButton.getAttribute('data-theme');
    if (!theme) return;
    
    // Update active state
    document.querySelectorAll('.theme-button').forEach(btn => {
        (btn as HTMLButtonElement).classList.remove('active');
    });
    themeButton.classList.add('active');
    
    // Apply theme
    document.body.className = `theme-${theme}`;
    localStorage.setItem('sentinel-theme', theme);
}

function toggleThemeSwitcher() {
    const themeButtons = document.getElementById('theme-buttons');
    if (themeButtons) {
        themeButtons.classList.toggle('active');
    }
}

// Add event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize theme
    initializeTheme();
    
    // Theme switcher
    document.getElementById('theme-switcher-toggle')?.addEventListener('click', toggleThemeSwitcher);
    document.querySelectorAll('.theme-button').forEach(button => {
        button.addEventListener('click', handleThemeSwitch);
    });
    
    // Don't show any UI until we check the session
    document.getElementById('loginContainer')!.classList.remove('active');
    document.getElementById('dashboard')!.classList.remove('active');
    
    // Check for existing session
    await checkSession();
    
    // Only show login if no session was found
    if (!sessionStorage.getItem(DASHBOARD_STATE_KEY)) {
        // Wait for splash screen before showing login
        if (!document.referrer.includes('index.html')) {
            ipcRenderer.once('splash-screen-done', () => {
                document.getElementById('loginContainer')!.classList.add('active');
            });
        } else {
            document.getElementById('loginContainer')!.classList.add('active');
        }
    }
    
    // Password visibility toggle
    const togglePassword = document.getElementById('togglePassword');
    const password = document.getElementById('password') as HTMLInputElement;
    
    togglePassword?.addEventListener('click', () => {
        const type = password.type === 'password' ? 'text' : 'password';
        password.type = type;
        
        // Update icon
        const icon = togglePassword.querySelector('i');
        if (icon) {
            icon.className = `fas fa-${type === 'password' ? 'eye' : 'eye-slash'}`;
        }
    });

    // Handle email input
    const username = document.getElementById('username') as HTMLInputElement;
    username?.addEventListener('input', (e) => {
        const input = e.target as HTMLInputElement;
        // Remove @gmail.com if user types it
        if (input.value.includes('@')) {
            input.value = input.value.split('@')[0];
        }
    });

    // Handle email on form submission
    const handleLoginWithEmail = async () => {
        const email = username.value;
        if (!email.includes('@')) {
            username.value = `${email}@gmail.com`;
        }
        await handleLogin();
        // Reset the display value without @gmail.com
        username.value = email;
    };
    
    // Login and logout buttons
    document.getElementById('loginButton')?.addEventListener('click', handleLoginWithEmail);
    document.getElementById('logoutButton')?.addEventListener('click', handleLogout);
    
    // Handle Enter key in login form
    password?.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            handleLoginWithEmail();
        }
    });

    // Window control buttons
    document.getElementById('minimize-btn')?.addEventListener('click', () => {
        ipcRenderer.send('minimize-window');
    });
    document.getElementById('close-btn')?.addEventListener('click', () => {
        ipcRenderer.send('close-window');
    });
});
