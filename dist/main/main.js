// src/main/main.ts
import { app, BrowserWindow, protocol, ipcMain } from "electron";
import path from "path";
import { fileURLToPath } from "url";
import os from "os";
var __filename = fileURLToPath(import.meta.url);
var __dirname = path.dirname(__filename);
function getCpuUsage() {
  const cpus = os.cpus();
  let totalIdle = 0;
  let totalTick = 0;
  cpus.forEach((cpu) => {
    const times = cpu.times;
    for (const type of Object.keys(times)) {
      totalTick += times[type];
    }
    totalIdle += times.idle;
  });
  return { idle: totalIdle / cpus.length, total: totalTick / cpus.length };
}
var lastCpuUsage = getCpuUsage();
async function getSystemInfo() {
  try {
    const currentCpuUsage = getCpuUsage();
    const idleDifference = currentCpuUsage.idle - lastCpuUsage.idle;
    const totalDifference = currentCpuUsage.total - lastCpuUsage.total;
    const cpuPercentage = 100 - Math.round(100 * idleDifference / totalDifference);
    lastCpuUsage = currentCpuUsage;
    const totalRAM = os.totalmem();
    const freeRAM = os.freemem();
    const usedRAM = totalRAM - freeRAM;
    const ramPercentage = Math.round(usedRAM / totalRAM * 100);
    const totalGB = (os.totalmem() / (1024 * 1024 * 1024)).toFixed(2);
    const freeGB = (os.freemem() / (1024 * 1024 * 1024)).toFixed(2);
    const storageText = `${freeGB}GB free of ${totalGB}GB`;
    return {
      cpu: cpuPercentage,
      ram: ramPercentage,
      storage: storageText
    };
  } catch (error) {
    console.error("Error getting system info:", error);
    return {
      cpu: 0,
      ram: 0,
      storage: "Error fetching"
    };
  }
}
function createSplashScreen() {
  const splash = new BrowserWindow({
    width: 500,
    height: 400,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });
  splash.loadFile(path.join(__dirname, "../renderer/splash.html"));
  return splash;
}
function createMainWindow() {
  const mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    show: false,
    frame: false,
    backgroundColor: "#001529",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });
  mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  return mainWindow;
}
app.whenReady().then(() => {
  protocol.registerHttpProtocol("sentinel", (req, cb) => {
    const mainWindow = BrowserWindow.getAllWindows()[0];
    if (mainWindow) {
      const redirectUrl = req.url.replace("sentinel://", "http://");
      const url = new URL(redirectUrl);
      const hash = url.hash;
      mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"), { hash });
    }
  });
});
app.on("open-url", (event, url) => {
  event.preventDefault();
  const mainWindow = BrowserWindow.getAllWindows()[0];
  if (mainWindow) {
    const redirectUrl = url.replace("sentinel://", "http://");
    const parsedUrl = new URL(redirectUrl);
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"), { hash: parsedUrl.hash });
  }
});
ipcMain.handle("get-system-info", async () => {
  return await getSystemInfo();
});
ipcMain.on("minimize-window", (event) => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (window) window.minimize();
});
ipcMain.on("close-window", (event) => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (window) window.close();
});
app.setAsDefaultProtocolClient("sentinel");
app.whenReady().then(() => {
  const splash = createSplashScreen();
  const mainWindow = createMainWindow();
  setTimeout(() => {
    splash.close();
    mainWindow.show();
  }, 5e3);
  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});
