const { contextBridge, ipcRenderer } = require('electron')

const API_BASE = (
  process.env.SUMVIDEO_API_BASE_URL ||
  process.env.SUMVIDEO_BACKEND_URL ||
  `http://127.0.0.1:${process.env.SUMVIDEO_API_PORT || 8000}`
).replace(/\/$/, '')

contextBridge.exposeInMainWorld('sumvideo', {
  isDesktop: true,
  pickVideo: () => ipcRenderer.invoke('pick-video'),
  readVideoFile: (filePath, name) =>
    ipcRenderer.invoke('read-video-file', filePath, name),
  getApiBase: () => API_BASE,
})
