import { supabase } from '../../supabase/client';

// Get DOM elements
const loginContainer = document.getElementById('loginContainer');
const dashboard = document.getElementById('dashboard');
const loginButton = document.getElementById('loginButton');
const logoutButton = document.getElementById('logoutButton');
const userName = document.getElementById('userName');
const userNameDisplay = document.getElementById('userNameDisplay');
const userDepartment = document.getElementById('userDepartment');
const userEmail = document.getElementById('userEmail');
const userRole = document.getElementById('userRole');
const mfaStatus = document.getElementById('mfaStatus');
const securityTier = document.getElementById('securityTier');
const statusDescription = document.getElementById('statusDescription');
const userBadge = document.getElementById('userBadge');

// Enable electron logging
const log = (...args) => {
    console.log('[SentinelApp]:', ...args);
    // If you're using electron's IPC
    if (window.electron) {
        window.electron.log(...args);
    }
};

// Function to get security description
function getSecurityDescription(tier) {
    const descriptions = {
        'RELIABLE': 'Your system activity indicates normal behavior patterns. Continue maintaining good security practices.',
        'SUSPICIOUS': 'Unusual activity detected. Please review your recent actions and security settings.',
        'COMPROMISED': 'Security breach detected! Immediate action required to secure your account.'
    };
    return descriptions[tier] || descriptions['RELIABLE'];
}

// Function to show error messages
function showError(message) {
    const errorElement = document.getElementById('loginError');
    if (errorElement) {
        errorElement.textContent = message;
    }
    console.error('Error:', message);
}

// Function to handle user login
async function handleLogin(email, password) {
    try {
        console.log('=== Starting Login Process ===');
        
        const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password,
        });
        
        if (error) {
            console.error('Login error:', error);
            const errorElement = document.getElementById('loginError');
            if (errorElement) {
                errorElement.textContent = error.message;
            }
            return;
        }

        console.log('Login successful:', data);
        
        if (data.user) {
            await updateUserInterface(data.user);
        }
    } catch (error) {
        console.error('Login error:', error);
        const errorElement = document.getElementById('loginError');
        if (errorElement) errorElement.textContent = 'Login failed. Please try again.';
    }
}

// Function to force update user details
function forceUpdateUserDetails() {
    // Get all elements
    const userName = document.querySelector('#userName');
    const userNameDisplay = document.querySelector('#userNameDisplay');
    const userDepartment = document.querySelector('#userDepartment');
    const userEmail = document.querySelector('#userEmail');
    const userRole = document.querySelector('#userRole');
    const mfaStatus = document.querySelector('#mfaStatus');
    
    console.log('Found elements:', {
        userName: !!userName,
        userNameDisplay: !!userNameDisplay,
        userDepartment: !!userDepartment,
        userEmail: !!userEmail,
        userRole: !!userRole,
        mfaStatus: !!mfaStatus
    });

    // Force set text content
    if (userName) userName.textContent = 'Sahindu';
    if (userNameDisplay) userNameDisplay.textContent = 'Sahindu';
    if (userDepartment) userDepartment.textContent = 'IT';
    if (userEmail) userEmail.textContent = 'gsahindu@gmail.com';
    if (userRole) userRole.textContent = 'AUTHENTICATED';
    if (mfaStatus) mfaStatus.textContent = 'DISABLED';

    // Force show user details
    const userDetails = document.querySelector('#userDetails');
    if (userDetails) {
        userDetails.style.display = 'block';
        console.log('Forced userDetails display to block');
    }

    // Update security status
    const securityTier = document.querySelector('#securityTier');
    const statusDescription = document.querySelector('#statusDescription');
    
    if (securityTier) {
        securityTier.textContent = 'SUSPICIOUS';
        securityTier.className = 'tier suspicious';
    }
    
    if (statusDescription) {
        statusDescription.textContent = 'Some unusual activity has been detected. Please review your recent actions and security settings.';
    }
}

// Function to update UI with user data
async function updateUserInterface(userData) {
    try {
        console.log('=== Starting updateUserInterface ===');
        
        // Hide login, show dashboard
        const loginContainer = document.querySelector('#loginContainer');
        const dashboard = document.querySelector('#dashboard');
        const userBadge = document.querySelector('#userBadge');
        
        if (loginContainer) loginContainer.style.display = 'none';
        if (dashboard) dashboard.style.display = 'block';
        if (userBadge) {
            userBadge.style.display = 'flex';
            // Add click handler to userBadge
            userBadge.onclick = () => {
                console.log('UserBadge clicked');
                forceUpdateUserDetails();
            };
        }

        // Force initial update
        forceUpdateUserDetails();
        
        console.log('=== UI Update Complete ===');
    } catch (error) {
        console.error('Error in updateUserInterface:', error);
    }
}

// Function to handle logout
async function handleLogout() {
    try {
        console.log('Logging out user');
        await supabase.auth.signOut();
        loginContainer.style.display = 'block';
        dashboard.style.display = 'none';
    } catch (error) {
        console.error('Logout error:', error);
    }
}

// Initialize event listeners
document.addEventListener('DOMContentLoaded', () => {
    console.log('=== DOM Content Loaded ===');

    // --- Tab Switching Logic --- 
    const tabButtons = document.querySelectorAll('.tabs .tab-button'); // Be more specific with selector
    const tabContents = document.querySelectorAll('.dashboard .tab-content'); // Be more specific
    console.log('[Tabs] Found Buttons:', tabButtons.length);
    console.log('[Tabs] Found Content Panes:', tabContents.length);

    // Function to switch tabs
    function switchTab(targetTabId) {
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
                content.style.display = 'none';
            }
        });
        
        // Then show the target content with animation
        const targetContent = document.getElementById(`${targetTabId}-tab-content`);
        if (targetContent) {
            // Display the content
            targetContent.style.display = 'block';
            // Force a reflow
            targetContent.offsetHeight;
            // Add active class for animation
            targetContent.classList.add('active');

            // Special handling for specific tabs
            if (targetTabId === 'monitor-status' && typeof updateMonitorStatus === 'function') {
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
            const clickedButton = event.currentTarget;
            console.log('[Tabs] Tab button clicked:', clickedButton); // Debug
            // Ensure clickedButton is an element before getting attribute
            if (clickedButton instanceof Element) {
                const targetTab = clickedButton.getAttribute('data-tab');
                if (targetTab) {
                     switchTab(targetTab);
                } else {
                     console.error('[Tabs] Clicked tab button missing data-tab attribute:', clickedButton); // Debug
                }
            } else {
                 console.error('[Tabs] Click target is not an Element:', clickedButton);
            }
        });
    });
    
    // Activate the default or last active tab on load
    const initialTab = 'home'; // Default to home
    console.log('[Tabs] Initializing default tab:', initialTab);
    // Use setTimeout to ensure rendering is complete before switching (might help)
    setTimeout(() => switchTab(initialTab), 0); 
    // --- End Tab Switching Logic ---

    // Add login button listener
    const loginButton = document.querySelector('#loginButton');
    if (loginButton) {
        loginButton.addEventListener('click', (e) => {
            e.preventDefault();
            const email = document.querySelector('#username')?.value;
            const password = document.querySelector('#password')?.value;
            if (email && password) {
                handleLogin(email, password);
            }
        });
    }

    // Add logout button listener
    const logoutButton = document.querySelector('#logoutButton');
    if (logoutButton) {
        logoutButton.addEventListener('click', handleLogout);
    }

    // Add click handler to user badge
    const userBadge = document.querySelector('#userBadge');
    if (userBadge) {
        userBadge.onclick = forceUpdateUserDetails;
    }

    // Check for existing session
    supabase.auth.onAuthStateChange((event, session) => {
        console.log('Auth state changed:', event);
        if (event === 'SIGNED_IN' && session?.user) {
            updateUserInterface(session.user);
        } else {
            const loginContainer = document.querySelector('#loginContainer');
            const dashboard = document.querySelector('#dashboard');
            if (loginContainer) loginContainer.style.display = 'block';
            if (dashboard) dashboard.style.display = 'none';
        }
    });

    // Theme switcher functionality
    const themeButtons = document.querySelectorAll('.theme-button');
    console.log('[Theme] Found theme buttons:', themeButtons.length);
    
    themeButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const target = event.currentTarget; // Use currentTarget instead of target.closest for direct button reference
            
            const theme = target.getAttribute('data-theme');
            if (!theme) return;
            
            console.log('[Theme] Switching theme to:', theme);

            // Update active state
            themeButtons.forEach(btn => btn.classList.remove('active'));
            target.classList.add('active');

            // Apply theme
            document.body.className = `theme-${theme}`;
            localStorage.setItem('sentinel-theme', theme);

            // Notify other windows about theme change
            if (window.electron) {
                window.electron.send('theme-changed', theme);
            }
        });
    });

    // Initialize theme
    const savedTheme = localStorage.getItem('sentinel-theme') || 'cyberpunk';
    document.body.className = `theme-${savedTheme}`;
    console.log('[Theme] Initial theme:', savedTheme);
    
    themeButtons.forEach(button => {
        const buttonTheme = button.getAttribute('data-theme');
        if (buttonTheme === savedTheme) {
            button.classList.add('active');
        } else {
            button.classList.remove('active');
        }
    });

    // Log Viewer Functionality
    const refreshLogsButton = document.getElementById('refresh-logs');
    const clearLogsButton = document.getElementById('clear-logs');
    const logFilter = document.getElementById('log-filter');
    const sentinelLogs = document.getElementById('sentinel-logs');
    
    if (refreshLogsButton && clearLogsButton && logFilter && sentinelLogs) {
        // Initialize logs
        fetchLogs();
        
        // Set up event listeners
        refreshLogsButton.addEventListener('click', fetchLogs);
        clearLogsButton.addEventListener('click', clearLogs);
        logFilter.addEventListener('change', filterLogs);
        
        // Set up auto-refresh
        setInterval(fetchLogs, 30000); // Refresh every 30 seconds
    } else {
        console.error('Log viewer elements not found');
    }
});

// Log viewer functions
async function fetchLogs() {
    const sentinelLogs = document.getElementById('sentinel-logs');
    if (!sentinelLogs) return;
    
    try {
        sentinelLogs.innerHTML = 'Loading logs...';
        
        // Get Sentinel logs
        const sentinelLogResult = await window.api.getSentinelLogs();
        
        // Get Python process logs
        const pythonLogResult = await window.api.getPythonLogs();
        
        // Build the log content
        let logContent = '';
        
        if (sentinelLogResult.success && sentinelLogResult.logs) {
            logContent += '=== SENTINEL LOG ===\n\n';
            logContent += sentinelLogResult.logs;
            logContent += '\n\n';
        } else {
            logContent += '=== SENTINEL LOG ===\n';
            logContent += sentinelLogResult.message || 'No sentinel logs available';
            logContent += '\n\n';
        }
        
        if (pythonLogResult.success && pythonLogResult.logs) {
            logContent += '=== PYTHON PROCESS LOGS ===\n\n';
            logContent += pythonLogResult.logs;
        } else {
            logContent += '=== PYTHON PROCESS LOGS ===\n';
            logContent += pythonLogResult.message || 'No Python process logs available';
        }
        
        // Display logs
        sentinelLogs.innerHTML = formatLogs(logContent);
        
        // Store raw logs for filtering
        sentinelLogs.dataset.rawLogs = logContent;
        
        // Apply current filter
        filterLogs();
        
        // Auto-scroll to bottom
        sentinelLogs.scrollTop = sentinelLogs.scrollHeight;
    } catch (error) {
        console.error('Error fetching logs:', error);
        sentinelLogs.innerHTML = `Error loading logs: ${error.message || 'Unknown error'}`;
    }
}

function clearLogs() {
    const sentinelLogs = document.getElementById('sentinel-logs');
    if (!sentinelLogs) return;
    
    sentinelLogs.innerHTML = 'Logs cleared. Click Refresh to load logs.';
    sentinelLogs.dataset.rawLogs = '';
}

function filterLogs() {
    const logFilter = document.getElementById('log-filter');
    const sentinelLogs = document.getElementById('sentinel-logs');
    if (!logFilter || !sentinelLogs) return;
    
    const filterValue = logFilter.value;
    const rawLogs = sentinelLogs.dataset.rawLogs || '';
    
    if (!rawLogs) {
        return;
    }
    
    if (filterValue === 'all') {
        sentinelLogs.innerHTML = formatLogs(rawLogs);
        return;
    }
    
    // Filter logs based on selected level
    const lines = rawLogs.split('\n');
    const filteredLines = lines.filter(line => {
        const lowerLine = line.toLowerCase();
        
        switch (filterValue) {
            case 'info':
                return lowerLine.includes('info') || lowerLine.includes('sentinel status');
            case 'warning':
                return lowerLine.includes('warn');
            case 'error':
                return lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('critical');
            default:
                return true;
        }
    });
    
    sentinelLogs.innerHTML = formatLogs(filteredLines.join('\n'));
}

function formatLogs(logs) {
    if (!logs) return '';
    
    // Apply syntax highlighting based on log level
    return logs.replace(/^(.*info.*)$/gim, '<span class="log-info">$1</span>')
              .replace(/^(.*warn.*)$/gim, '<span class="log-warning">$1</span>')
              .replace(/^(.*error.*|.*exception.*|.*critical.*)$/gim, '<span class="log-error">$1</span>');
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
        monitorStatusContainer.innerHTML = '<div class="loading-indicator">Loading monitor status...</div>';

        // Get status from backend
        const status = await window.api.checkSentinelStatus();
        
        // Create status elements
        let statusHTML = `
            <div class="monitor-status-header">
                <h3>Monitor Status</h3>
                <button id="refresh-status" class="status-button"><i class="fas fa-sync"></i> Refresh</button>
            </div>
            <div class="monitor-status-list">`;
            
        // Define the monitors we want to show
        const monitors = [
            { id: 'usb_monitor', name: 'USB Monitor', icon: 'usb' },
            { id: 'system_monitor', name: 'System Monitor', icon: 'laptop' },
            { id: 'process_monitor', name: 'Process Monitor', icon: 'tasks' },
            { id: 'network_monitor', name: 'Network Monitor', icon: 'network-wired' },
            { id: 'browser_monitor', name: 'Browser Monitor', icon: 'globe' },
            { id: 'login_monitor', name: 'Login Monitor', icon: 'sign-in-alt' },
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
        
        // Add refresh button handler
        const refreshButton = document.getElementById('refresh-status');
        if (refreshButton) {
            refreshButton.addEventListener('click', updateMonitorStatus);
        }
        
    } catch (error) {
        console.error("Error updating monitor status:", error);
        monitorStatusContainer.innerHTML = `<div class="error-message">Error loading monitor status: ${error instanceof Error ? error.message : String(error)}</div>`;
    }
}
