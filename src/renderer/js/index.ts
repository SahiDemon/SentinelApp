import { notificationManager } from './notifications';
import { handleLogin as login, handleLogout as logout, getUserSecurityTier, getCurrentUser } from './auth.js';

// Key for storing dashboard state
const DASHBOARD_STATE_KEY = 'sentinel_dashboard_state';

// Add variable to track connection attempts
let sentinelConnectionAttempts = 0;
const MAX_CONNECTION_ATTEMPTS = 5;

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
            
            // Send user ID to main process for sentinel monitoring
            if (user?.email && window.api) {
                console.log(`Sending user ID to main process: ${user.email}`);
                window.api.updateSentinelUser(user.email);
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
        
        // Stop sentinel monitoring
        if (window.api) {
            console.log('Sending empty user ID to stop monitoring.');
            window.api.updateSentinelUser('');
        }
    } catch (error) {
        notificationManager.show('Logout failed', 'error');
    }
}

async function fetchSystemInfo() {
    const cpuUsageElement = document.getElementById('cpu-usage');
    const ramUsageElement = document.getElementById('ram-usage');
    const storageInfoElement = document.getElementById('storage-info');

    try {
        const info = await window.api.getSystemStats();
        
        if (cpuUsageElement) {
            cpuUsageElement.textContent = typeof info.cpu === 'number' ? 
                info.cpu.toFixed(1).toString() : 'N/A';
        }

        if (ramUsageElement) {
            ramUsageElement.textContent = typeof info.ram === 'number' ? 
                info.ram.toFixed(1).toString() : 'N/A';
        }

        if (storageInfoElement) {
            storageInfoElement.textContent = info.storage || 'N/A';
        }
        
        // DO NOT update Sentinel status here. It's handled by listeners and checkSentinelStatus().
        
    } catch (error) {
        if (cpuUsageElement) cpuUsageElement.textContent = 'N/A';
        if (ramUsageElement) ramUsageElement.textContent = 'N/A';
        if (storageInfoElement) storageInfoElement.textContent = 'N/A';
    }
}

// Interface for the status object from main process
interface SentinelStatus {
    running: boolean;
    status: string; // More descriptive status (e.g., 'Running', 'Stopped', 'Error', 'Initializing', 'Requires Admin')
    admin: boolean;
    requiresAdmin: boolean;
    lastError?: string;
    pid?: number | null;
    userId?: string | null;
    // Legacy fields for backward compatibility
    user_id?: string;
    adminRequired?: boolean;
    monitors?: Record<string, boolean>;
}

// Consolidated function to update all Sentinel-related UI elements
function updateSentinelUI(sentinelStatus: SentinelStatus) {
    const sentinelStatusBadge = document.getElementById('sentinel-status');
    const sentinelMonitorStatusText = document.getElementById('sentinel-monitor-status'); // Assuming this is the text element
    const adminIndicator = document.getElementById('admin-status'); // Assuming an element for admin status text/icon

    console.log("Updating Sentinel UI with status:", sentinelStatus);
    
    if (sentinelStatusBadge) {
        sentinelStatusBadge.classList.remove('active', 'inactive', 'requires-admin', 'error');
        let badgeText = '';
        let badgeClass = '';

        if (sentinelStatus.running) {
            // Add admin badge indicator with visual style
            const adminBadge = sentinelStatus.admin ? 
                '<span class="admin-badge" style="background-color: #2ecc71; color: white; padding: 2px 4px; border-radius: 3px; font-size: 0.8em; margin-left: 5px;">ADMIN</span>' : 
                '<span class="non-admin-badge" style="background-color: #e74c3c; color: white; padding: 2px 4px; border-radius: 3px; font-size: 0.8em; margin-left: 5px;">LIMITED</span>';
            badgeText = `<i class="fas fa-shield-alt"></i> Sentinel ${sentinelStatus.status} ${adminBadge}`;
            badgeClass = 'active';
        } else if (sentinelStatus.status === 'Requires Admin') {
            badgeText = '<i class="fas fa-exclamation-triangle"></i> Sentinel Requires Admin';
            badgeClass = 'requires-admin';
            notificationManager.show('Sentinel requires administrator privileges for full monitoring. Please restart as administrator.', 'info', 10000);
        } else if (sentinelStatus.status.includes('Error') || sentinelStatus.status.includes('Failed') || sentinelStatus.status.includes('Crashed')) {
            badgeText = `<i class="fas fa-times-circle"></i> Sentinel ${sentinelStatus.status}`;
            badgeClass = 'error';
            if (sentinelStatus.lastError || sentinelStatus.status !== 'Error') {
                notificationManager.show(`Sentinel Error: ${sentinelStatus.lastError || sentinelStatus.status}`, 'error', 10000);
            }
        } else {
            badgeText = '<i class="fas fa-exclamation-triangle"></i> Sentinel Inactive';
            badgeClass = 'inactive';
        }

        sentinelStatusBadge.innerHTML = badgeText;
        sentinelStatusBadge.classList.add(badgeClass);
    }
    
    // Update the more detailed status text (optional element)
    if (sentinelMonitorStatusText) {
        sentinelMonitorStatusText.classList.remove('status-active', 'status-inactive', 'status-error');
        let statusText = sentinelStatus.status;
        let statusClass = 'status-inactive';

        if (sentinelStatus.running) {
            statusClass = 'status-active';
            if (sentinelStatus.pid) {
                statusText += ` [PID: ${sentinelStatus.pid}]`;
            }
            
            // Add admin status to detailed text
            statusText += sentinelStatus.admin ? ' (Admin)' : ' (Limited)';
        } else if (sentinelStatus.status.includes('Error') || sentinelStatus.status.includes('Failed') || sentinelStatus.status.includes('Crashed')) {
             statusClass = 'status-error';
        } else if (sentinelStatus.requiresAdmin && !sentinelStatus.admin) {
            statusText += ' (Admin Required)';
            statusClass = 'status-error';
        }
        
        sentinelMonitorStatusText.textContent = statusText;
        sentinelMonitorStatusText.classList.add(statusClass);
    }
    
    // Update admin indicator text/icon
    if (adminIndicator) {
        adminIndicator.classList.remove('admin-yes', 'admin-no', 'admin-required');
        let adminText = 'Admin: No';
        let adminClass = 'admin-no';

        if (sentinelStatus.requiresAdmin && !sentinelStatus.admin) {
            adminText = 'Admin: Required!';
            adminClass = 'admin-required';
        } else if (sentinelStatus.admin) {
            adminText = 'Admin: Yes';
            adminClass = 'admin-yes';
        }
        adminIndicator.textContent = adminText;
        adminIndicator.classList.add(adminClass);
        adminIndicator.style.display = 'inline-block'; // Or block
    }
}

// Function to update monitor status display
async function updateMonitorStatus() {
    console.log("Updating monitor status...");
    const monitorStatusContainer = document.getElementById('monitor-status-container');
    
    if (!monitorStatusContainer) {
        console.error("Monitor status container not found");
        return;
    }

    try {
        // Set loading state
        monitorStatusContainer.innerHTML = '<div class="loading-indicator"><i class="fas fa-circle-notch fa-spin"></i> Loading monitor status...</div>';

        // Get status from backend
        const status = await window.api.checkSentinelStatus();
        
        // Start with empty monitor list
        let statusHTML = `<div class="monitor-status-list">`;
            
        // Define the monitors we want to show with proper icons
        const monitors = [
            { id: 'usb_monitor', name: 'Device Monitor', icon: 'plug' },
            { id: 'system_monitor', name: 'System Monitor', icon: 'laptop' },
            { id: 'process_monitor', name: 'Process Monitor', icon: 'microchip' },
            { id: 'network_monitor', name: 'Network Monitor', icon: 'globe' },
            { id: 'browser_monitor', name: 'Browser Monitor', icon: 'window-maximize' },
            { id: 'login_monitor', name: 'Login Monitor', icon: 'user-shield' },
            { id: 'filesystem_monitor', name: 'Filesystem Monitor', icon: 'folder' }
        ];
        
        // For demo/development, assume all are running if we can't determine status
        const isRunning = status.running;
        
        // Add each monitor's status
        monitors.forEach(monitor => {
            // Check monitor status - if sentinel is running, consider monitors active
            // In a real implementation, you would use status.monitors[monitor.id]
            const isActive = isRunning;
            const statusClass = isActive ? 'status-active' : 'status-inactive';
            const statusText = isActive ? 'Active' : 'Inactive';
            
            statusHTML += `
                <div class="monitor-status-item">
                    <div class="monitor-icon"><i class="fas fa-${monitor.icon}"></i></div>
                    <div class="monitor-name">${monitor.name}</div>
                    <div class="monitor-status ${statusClass}">${statusText}</div>
                </div>`;
        });
        
        statusHTML += `</div>`;
        
        // Set the content
        monitorStatusContainer.innerHTML = statusHTML;
        
    } catch (error) {
        console.error("Error updating monitor status:", error);
        monitorStatusContainer.innerHTML = `<div class="error-message">Error loading monitor status: ${error instanceof Error ? error.message : String(error)}</div>`;
    }
}

// Function to check Sentinel status and update UI
async function checkSentinelStatus() {
    console.log("Requesting initial Sentinel status...");
    if (window.api && typeof window.api.checkSentinelStatus === 'function') {
        try {
            const rawStatus = await window.api.checkSentinelStatus();
            // Convert legacy status format if needed
            const normalizedStatus: SentinelStatus = {
                running: rawStatus.running,
                status: (rawStatus as any).status || 'Unknown',
                admin: typeof rawStatus.admin === 'boolean' ? rawStatus.admin : false,
                requiresAdmin: (rawStatus as any).requiresAdmin || rawStatus.adminRequired || false,
                lastError: rawStatus.lastError,
                pid: rawStatus.pid,
                userId: (rawStatus as any).userId || rawStatus.user_id
            };
            updateSentinelUI(normalizedStatus); // Update UI with fetched status
        } catch (error) {
            console.error('Error fetching initial Sentinel status:', error);
            updateSentinelUI({ // Update UI to show error state
                running: false,
                status: 'Error Checking Status',
                admin: false, // Unknown
                requiresAdmin: false, // Unknown
                lastError: error instanceof Error ? error.message : String(error)
            });
        }
    } else {
        console.error('Error checking Sentinel status: API not available');
        updateSentinelUI({ // Update UI to show API unavailable
            running: false,
            status: 'Service Unavailable',
            admin: false,
            requiresAdmin: false,
            lastError: 'API not available'
        });
    }
}

// Check status every 30 seconds
let sentinelCheckInterval: NodeJS.Timeout | null = null;

function startStatusChecks() {
    if (!sentinelCheckInterval) { // Only start if not already running
        console.log("Starting periodic Sentinel status checks.");
        // Initial check
        checkSentinelStatus(); // This function now requests status via invoke and updates UI
        // Set interval (optional, as we rely on pushed updates)
        sentinelCheckInterval = setInterval(checkSentinelStatus, 60 * 1000); // Re-check status periodically
    } else {
        console.log("Periodic status checks already running.");
    }
}

function stopStatusChecks() {
    if (sentinelCheckInterval) {
        console.log("Stopping periodic Sentinel status checks.");
        clearInterval(sentinelCheckInterval);
        sentinelCheckInterval = null;
    }
}

async function init() {
    notificationManager.show('Initializing dashboard...', 'info');
    
    // Setup listeners first
    setupSentinelListeners();
    
    // Perform initial status check now that listeners are ready
    startStatusChecks(); // This function now calls checkSentinelStatus immediately
    
    // Fetch initial system info
    await fetchSystemInfo();
    
    // User email should already be set by checkSession or handleLogin
    
    // Send user ID to main process for sentinel monitoring
    // User ID should already have been sent by checkSession or handleLogin
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
            
            // Send user ID to main process for sentinel monitoring
            if (user?.id && window.api) {
                console.log(`Sending user ID to main process: ${user.id}`);
                window.api.updateSentinelUser(user.id);
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
                // Use a proper event handler for one-time events
                const splashDoneHandler = () => {
                    showOverlay();
                    // No need to unregister since it's a one-time operation
                };
                window.api.receive('splash-screen-done', splashDoneHandler);
            }
            
            document.getElementById('userEmail')!.textContent = user.email || '';
            
            // Send user ID to main process for sentinel monitoring
            if (user.id && window.api) {
                console.log(`Sending user ID to main process: ${user.id}`);
                window.api.updateSentinelUser(user.id);
            }
            
            await init();
        }
    } catch (error) {
        console.error('Session check failed:', error);
        notificationManager.show('Auto-login failed', 'error');
        sessionStorage.removeItem(DASHBOARD_STATE_KEY);
    }
}

// Handle page reloads
window.api.receive('preserve-state', () => {
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

function showServiceStatus() {
    const statusSection = document.getElementById('statusSection');
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    const elevateButton = document.getElementById('elevateButton');
    const userInput = document.getElementById('userInput') as HTMLInputElement;
    const userSubmit = document.getElementById('userSubmit');
    
    if (!statusSection || !statusIndicator || !statusText) return;
    
    // Initially show loading state
    statusIndicator.className = 'status-indicator loading';
    statusText.textContent = 'Checking service status...';
    
    if (elevateButton) {
        elevateButton.style.display = 'none';
    }
    
    // Check sentinel status
    window.api.checkSentinelStatus().then((rawStatus: any) => {
        // Normalize the status object
        const status: SentinelStatus = {
            running: rawStatus.running,
            status: rawStatus.status || 'Unknown',
            admin: typeof rawStatus.admin === 'boolean' ? rawStatus.admin : false,
            requiresAdmin: rawStatus.requiresAdmin || rawStatus.adminRequired || false,
            lastError: rawStatus.lastError,
            pid: rawStatus.pid,
            userId: rawStatus.userId || rawStatus.user_id
        };
        
        if (status.running) {
            statusIndicator.className = 'status-indicator active';
            statusText.textContent = 'Service Active';
            
            if (status.userId && userInput) {
                userInput.value = status.userId;
                userInput.disabled = true;
                if (userSubmit) {
                    userSubmit.setAttribute('disabled', 'true');
                }
            }
            
            // Listen for sentinel output
            window.api.receive('sentinel-output', (data: string) => {
                console.log('Sentinel output:', data);
                // You can update UI here if needed
            });
            
            // Listen for sentinel errors
            window.api.receive('sentinel-error', (error: string) => {
                console.error('Sentinel error:', error);
                notificationManager.show(`Service error: ${error}`, 'error');
            });
            
            // Listen for sentinel stopped
            window.api.receive('sentinel-stopped', (code: number) => {
                console.log('Sentinel stopped with code:', code);
                statusIndicator.className = 'status-indicator inactive';
                statusText.textContent = 'Service Stopped';
                notificationManager.show(`Service has stopped with code: ${code}`, 'error');
            });
        } else {
            if (status.requiresAdmin && !status.admin) {
                // We need admin privileges
                statusIndicator.className = 'status-indicator error';
                statusText.textContent = 'Administrator privileges required';
                
                if (elevateButton) {
                    elevateButton.style.display = 'block';
                    elevateButton.addEventListener('click', () => {
                        window.api.send('elevate-privileges', {});
                    });
                }
            } else if (status.lastError) {
                // Show error
                statusIndicator.className = 'status-indicator error';
                statusText.textContent = 'Service Error';
                notificationManager.show(`Service error: ${status.lastError}`, 'error');
            } else {
                // Not running for other reasons
                statusIndicator.className = 'status-indicator inactive';
                statusText.textContent = 'Service Inactive';
            }
        }
    }).catch(err => {
        console.error('Failed to check sentinel status:', err);
        statusIndicator.className = 'status-indicator error';
        statusText.textContent = 'Failed to check service status';
    });
}

// Handle user ID submission
function handleUserIdSubmit() {
    const userInput = document.getElementById('userInput') as HTMLInputElement;
    const userSubmit = document.getElementById('userSubmit');
    
    if (!userInput || !userSubmit) return;
    
    userSubmit.addEventListener('click', () => {
        const userId = userInput.value.trim();
        if (userId) {
            window.api.updateSentinelUser(userId);
            userInput.disabled = true;
            userSubmit.setAttribute('disabled', 'true');
            notificationManager.show('User ID updated', 'success');
        } else {
            notificationManager.show('Please enter a valid User ID', 'error');
        }
    });
}

// Tab switching function
function setupTabSwitching() {
    const tabButtons = document.querySelectorAll('.tabs .tab-button');
    const tabContents = document.querySelectorAll('.dashboard .tab-content');
    console.log('[Tabs] Found Buttons:', tabButtons.length);
    console.log('[Tabs] Found Content Panes:', tabContents.length);

    function switchTab(targetTabId: string) {
        console.log('[Tabs] Attempting to switch to tab:', targetTabId);
        if (!targetTabId) {
            console.error('[Tabs] switchTab called with invalid targetTabId');
            return;
        }

        // First, handle buttons
        tabButtons.forEach(button => {
            const buttonTabId = button.getAttribute('data-tab');
            button.classList.toggle('active', buttonTabId === targetTabId);
        });

        // Improved animation: First hide all content
        tabContents.forEach(content => {
            content.classList.remove('active');
            // Hide non-target content immediately
            if (content.id !== `${targetTabId}-tab-content`) {
                (content as HTMLElement).style.display = 'none';
            }
        });
        
        // Then show the target content with animation
        const targetContent = document.getElementById(`${targetTabId}-tab-content`);
        if (targetContent) {
            // Display the content
            (targetContent as HTMLElement).style.display = 'block';
            // Force a reflow
            (targetContent as HTMLElement).offsetHeight;
            // Add active class for animation
            targetContent.classList.add('active');

            // Special handling for logs tab
            if (targetTabId === 'logs' && typeof window.fetchLogs === 'function') {
                console.log('[Tabs] Fetching logs for active Logs tab.');
                window.fetchLogs();
            }
            
            // Special handling for monitor status tab
            if (targetTabId === 'monitor-status') {
                console.log('[Tabs] Updating monitor status.');
                updateMonitorStatus();
            }
        } else {
            console.error(`[Tabs] Content pane not found for ID: ${targetTabId}-tab-content`);
        }
    }

    tabButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            // Use currentTarget to ensure we're getting the button the listener was attached to
            const clickedButton = event.currentTarget as HTMLElement;
            console.log('[Tabs] Tab button clicked:', clickedButton); // Debug
            
            const targetTab = clickedButton.getAttribute('data-tab');
            if (targetTab) {
                switchTab(targetTab);
            } else {
                console.error('[Tabs] Clicked tab button missing data-tab attribute:', clickedButton); // Debug
            }
        });
    });
    
    // Activate the default tab on load
    const initialTab = 'home'; // Default to home
    console.log('[Tabs] Initializing default tab:', initialTab);
    // Use setTimeout to ensure rendering is complete before switching
    setTimeout(() => switchTab(initialTab), 0);
}

// Declare fetchLogs on window to avoid TypeScript errors
declare global {
    interface Window {
        fetchLogs?: () => void;
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
    
    // Setup IPC listeners for Sentinel *early* before checking session
    setupSentinelListeners();
    
    // Check for existing session
    await checkSession();
    
    // Only show login if no session was found
    if (!sessionStorage.getItem(DASHBOARD_STATE_KEY)) {
        // Wait for splash screen before showing login
        if (!document.referrer.includes('index.html')) {
            const loginReadyHandler = () => {
                document.getElementById('loginContainer')!.classList.add('active');
            };
            window.api.receive('splash-screen-done', loginReadyHandler);
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
        window.api.minimizeWindow();
    });
    document.getElementById('close-btn')?.addEventListener('click', () => {
        window.api.closeWindow();
    });

    // Settings menu toggle
    const settingsIcon = document.querySelector('.settings-icon');
    const settingsMenu = document.querySelector('.settings-menu');

    if (settingsIcon && settingsMenu) {
        settingsIcon.addEventListener('click', (e) => {
            e.stopPropagation();
            settingsMenu.classList.toggle('active');
        });

        document.addEventListener('click', (e) => {
            const target = e.target as Node;
            if (!settingsIcon.contains(target) && !settingsMenu.contains(target)) {
                settingsMenu.classList.remove('active');
            }
        });
    }

    // Initial status check
    checkSentinelStatus();
    
    // Start periodic checks
    startStatusChecks();

    showServiceStatus();
    handleUserIdSubmit();

    // Setup tab switching
    setupTabSwitching();
});

// Setup IPC listeners
function setupSentinelListeners() {
    // Use the receive method for all listeners to avoid TS errors
    window.api.receive('sentinel-status-update', (status: any) => {
        console.log('Received sentinel-status-update:', status);
        // Normalize the status object
        const normalizedStatus: SentinelStatus = {
            running: status.running,
            status: status.status || 'Unknown',
            admin: typeof status.admin === 'boolean' ? status.admin : false,
            requiresAdmin: status.requiresAdmin || status.adminRequired || false,
            lastError: status.lastError,
            pid: status.pid,
            userId: status.userId || status.user_id
        };
        updateSentinelUI(normalizedStatus);
    });
    console.log("Sentinel status update listener registered.");

    // Listen for raw output
    window.api.receive('sentinel-output', (output: string) => {
        console.log('[Sentinel Output]:', output);
        // TODO: Append to a debug console UI element if desired
    });
    console.log("Sentinel output listener registered.");

    // Listen for errors
    window.api.receive('sentinel-error', (error: string) => {
        console.error('[Sentinel Error]:', error);
        // Potentially show a notification for critical errors
        if (error.includes('FATAL') || error.includes('CRITICAL')) {
            notificationManager.show(`Sentinel Critical Error: ${error}`, 'error');
        }
    });
    console.log("Sentinel error listener registered.");
}

// Handle window beforeunload
window.addEventListener('beforeunload', () => {
    // Stop status checks when the window unloads
    stopStatusChecks();
});
