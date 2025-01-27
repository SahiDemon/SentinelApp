import { app, BrowserWindow, protocol, ipcMain } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface CpuTimes {
    user: number;
    nice: number;
    sys: number;
    idle: number;
    irq: number;
}

// System info related functions
function getCpuUsage() {
    const cpus = os.cpus();
    let totalIdle = 0;
    let totalTick = 0;
    cpus.forEach(cpu => {
        const times = cpu.times as CpuTimes;
        for (const type of Object.keys(times)) {
            totalTick += times[type as keyof CpuTimes];
        }
        totalIdle += times.idle;
    });
    return { idle: totalIdle / cpus.length, total: totalTick / cpus.length };
}

let lastCpuUsage = getCpuUsage();

async function getSystemInfo() {
    try {
        // CPU Usage
        const currentCpuUsage = getCpuUsage();
        const idleDifference = currentCpuUsage.idle - lastCpuUsage.idle;
        const totalDifference = currentCpuUsage.total - lastCpuUsage.total;
        const cpuPercentage = 100 - Math.round(100 * idleDifference / totalDifference);
        lastCpuUsage = currentCpuUsage;

        // RAM Usage
        const totalRAM = os.totalmem();
        const freeRAM = os.freemem();
        const usedRAM = totalRAM - freeRAM;
        const ramPercentage = Math.round((usedRAM / totalRAM) * 100);

        // Storage Info - Using available space on root drive
        // For both Windows and Unix, get total memory and available memory
        const totalGB = (os.totalmem() / (1024 * 1024 * 1024)).toFixed(2);
        const freeGB = (os.freemem() / (1024 * 1024 * 1024)).toFixed(2);
        const storageText = `${freeGB}GB free of ${totalGB}GB`;

        return {
            cpu: cpuPercentage,
            ram: ramPercentage,
            storage: storageText
        };
    } catch (error) {
        console.error('Error getting system info:', error);
        return {
            cpu: 0,
            ram: 0,
            storage: 'Error fetching'
        };
    }
}

function createSplashScreen() {
    const splash = new BrowserWindow({
        width: 500,
        height: 400,
        frame: false,
        transparent: true,
        backgroundColor: '#00000000',
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    });

    splash.loadFile(path.join(__dirname, '../renderer/splash.html'));
    return splash;
}

function createMainWindow() {
    const mainWindow = new BrowserWindow({
        width: 800,
        height: 600,
        show: false,
        frame: false,
        backgroundColor: '#001529',
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    });

    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
    return mainWindow;
}

// Register protocol
app.whenReady().then(() => {
    protocol.registerHttpProtocol('sentinel', (req, cb) => {
        const mainWindow = BrowserWindow.getAllWindows()[0];
        if (mainWindow) {
            const redirectUrl = req.url.replace('sentinel://', 'http://');
            const url = new URL(redirectUrl);
            const hash = url.hash;
            mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'), { hash });
        }
    });
});

// Handle auth callback
app.on('open-url', (event, url) => {
    event.preventDefault();
    const mainWindow = BrowserWindow.getAllWindows()[0];
    if (mainWindow) {
        const redirectUrl = url.replace('sentinel://', 'http://');
        const parsedUrl = new URL(redirectUrl);
        mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'), { hash: parsedUrl.hash });
    }
});

// Handle IPC messages
ipcMain.handle('get-system-info', async () => {
    return await getSystemInfo();
});

ipcMain.on('minimize-window', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (window) window.minimize();
});

ipcMain.on('close-window', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (window) window.close();
});

// Handle the protocol launch for Windows
app.setAsDefaultProtocolClient('sentinel');

app.whenReady().then(() => {
    const splash = createSplashScreen();
    const mainWindow = createMainWindow();

    // Simulate initialization process
    setTimeout(() => {
        splash.close();
        mainWindow.show();
    }, 5000);

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') {
            app.quit();
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
        }
    });
});
