import { handleLogin as login, handleLogout as logout, getUserSecurityTier, getCurrentUser } from './auth.js';
const { ipcRenderer } = require('electron');

async function handleLogin() {
    const username = document.getElementById('username') as HTMLInputElement;
    const password = document.getElementById('password') as HTMLInputElement;
    const rememberMe = document.getElementById('rememberMe') as HTMLInputElement;
    
    try {
        const result = await login(username.value, password.value, rememberMe.checked);
        if (result.success) {
            document.getElementById('loginContainer')!.style.display = 'none';
            document.getElementById('dashboard')!.style.display = 'block';
            
            // Set user email in greeting
            const user = await getCurrentUser();
            if (user?.email) {
                document.getElementById('userEmail')!.textContent = user.email;
            }
            
            await init();
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        const errorElement = document.getElementById('loginError')!;
        errorElement.textContent = error instanceof Error ? error.message : 'Login failed';
    }
}

async function handleLogout() {
    await logout();
    document.getElementById('dashboard')!.style.display = 'none';
    document.getElementById('loginContainer')!.style.display = 'flex';
    (document.getElementById('username') as HTMLInputElement).value = '';
    (document.getElementById('password') as HTMLInputElement).value = '';
    document.getElementById('loginError')!.textContent = '';
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
        const user = await getCurrentUser();
        if (user) {
            document.getElementById('loginContainer')!.style.display = 'none';
            document.getElementById('dashboard')!.style.display = 'block';
            document.getElementById('userEmail')!.textContent = user.email || '';
            await init();
        }
    } catch (error) {
        console.error('Session check failed:', error);
    }
}

// Add event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check for existing session
    checkSession();
    
    // Login and logout buttons
    document.getElementById('loginButton')?.addEventListener('click', handleLogin);
    document.getElementById('logoutButton')?.addEventListener('click', handleLogout);
    
    // Handle Enter key in login form
    document.getElementById('password')?.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            handleLogin();
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
