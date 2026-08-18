// 后端 API 封装
const BASE = '/api'

// 获取认证 token
function getToken() {
  return localStorage.getItem('lanshare_token') || ''
}

// 请求封装：自动带 token，统一处理错误
async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['X-Auth-Token'] = token

  const resp = await fetch(BASE + url, { ...options, headers })

  if (resp.status === 401) {
    // token 失效，跳转到密码页
    window.dispatchEvent(new CustomEvent('lanshare-auth-fail'))
    throw new Error('需要访问密码')
  }
  if (!resp.ok) {
    let msg = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (data.detail) msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch (e) { /* ignore */ }
    throw new Error(msg)
  }
  return resp
}

async function getJSON(url) {
  const resp = await request(url)
  return resp.json()
}

async function postJSON(url, body) {
  const resp = await request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return resp.json()
}

// 文件列表
export const listFiles = (path) => getJSON(`/files?path=${encodeURIComponent(path)}`)
export const searchFiles = (path, keyword) => getJSON(`/files/search?path=${encodeURIComponent(path)}&keyword=${encodeURIComponent(keyword)}`)
export const mkdir = (path) => postJSON('/dir', { path })
export const deleteFile = (path) => request(`/file?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
export const renameFile = (path, newName) => postJSON('/file/rename', { path, newName })
export const getStorage = () => getJSON('/storage')
export const getNetwork = () => getJSON('/meta/network')

// 上传
export const uploadInit = (md5, fileName, totalSize, chunkSize) => {
  const fd = new FormData()
  fd.append('md5', md5)
  fd.append('fileName', fileName)
  fd.append('totalSize', String(totalSize))
  fd.append('chunkSize', String(chunkSize))
  return request('/upload/init', { method: 'POST', body: fd }).then(r => r.json())
}

export const uploadChunk = (uploadId, chunkIndex, chunkMd5, blob, signal) => {
  const fd = new FormData()
  fd.append('uploadId', String(uploadId))
  fd.append('chunkIndex', String(chunkIndex))
  fd.append('chunkMd5', chunkMd5)
  fd.append('file', blob, `chunk-${chunkIndex}`)
  return request('/upload/chunk', { method: 'POST', body: fd, signal }).then(r => r.json())
}

export const getUploadStatus = (uploadId) => getJSON(`/upload/status?uploadId=${uploadId}`)
export const mergeUpload = (uploadId, targetDir) => {
  const fd = new FormData()
  fd.append('uploadId', String(uploadId))
  fd.append('targetDir', targetDir)
  return request('/upload/merge', { method: 'POST', body: fd }).then(r => r.json())
}
export const cancelUpload = (uploadId) => {
  const fd = new FormData()
  fd.append('uploadId', String(uploadId))
  return request('/upload/cancel', { method: 'POST', body: fd }).then(r => r.json())
}

// 认证
export const verifyPassword = (password) => postJSON('/auth/verify', { password })
export const getAuthStatus = () => getJSON('/auth/status')

// 下载 URL 生成
export const downloadUrl = (path) => `${BASE}/download?path=${encodeURIComponent(path)}`
export const zipDownloadUrl = (paths) => `${BASE}/download/zip?paths=${encodeURIComponent(paths.join(','))}`

// 带 token 的下载链接
export function withToken(url) {
  const token = getToken()
  if (!token) return url
  return url + (url.includes('?') ? '&' : '?') + `token=${encodeURIComponent(token)}`
}
