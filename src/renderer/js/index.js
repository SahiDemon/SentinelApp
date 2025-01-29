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
});
