// 前端并发 Range 分片下载器
//
// 原理：通过 fetch + `Range: bytes=start-end` 将单个大文件切成多片并发拉取，
// 各分片以 Blob 分段累积，全部完成后按顺序拼接为完整 Blob 触发浏览器保存。
// 后端 FileResponse 原生支持 Range（206），因此无需任何后端改动。
//
// 能力检测：不支持 fetch 流式读取 / 超大文件时，调用方应回退到原生跳转下载。

const DEFAULT_CONNECTIONS = 4 // 默认并发连接数
const MAX_CONNECTIONS = 8 // 并发连接上限
const MAX_RETRIES = 2 // 单分片失败重试次数
const FALLBACK_SIZE_LIMIT = 2 * 1024 * 1024 * 1024 // >2GB 回退原生下载，避免前端 Blob 内存累积
const MIN_SIZE_FOR_DOWNLOADER = 1 * 1024 * 1024 // <1MB 直接用原生下载，免去分片开销
const SPEED_WINDOW_MS = 2000 // 速度采样窗口

function getToken() {
  return localStorage.getItem('lanshare_token') || ''
}

// 为下载链接追加 token（query 参数方式，与 api/index.js 中 withToken 一致）
export function withToken(url) {
  const token = getToken()
  if (!token) return url
  return url + (url.includes('?') ? '&' : '?') + `token=${encodeURIComponent(token)}`
}

// 能力检测：是否支持 fetch + AbortController + Blob
export function isRangeSupported() {
  try {
    if (typeof fetch !== 'function') return false
    if (!('AbortController' in window)) return false
    if (typeof Blob !== 'function') return false
    return true
  } catch (e) {
    return false
  }
}

// 是否应使用分片下载器
export function shouldUseDownloader(fileSize) {
  if (!isRangeSupported()) return false
  if (!Number.isFinite(fileSize) || fileSize <= 0) return false
  if (fileSize < MIN_SIZE_FOR_DOWNLOADER || fileSize > FALLBACK_SIZE_LIMIT) return false
  return true
}

// 回退：浏览器原生跳转下载
export function fallbackDownload(url) {
  window.location.href = url
}

let taskId = 0

export function createDownloadTask(options) {
  return new DownloadTask(options)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

class DownloadTask {
  constructor({ url, name, totalSize, connections, onProgress, onState, onDone, onError }) {
    this.id = ++taskId
    this.url = withToken(url)
    this.name = name || 'download'
    this.totalSize = totalSize || 0
    this.connections = Math.min(MAX_CONNECTIONS, Math.max(1, connections || DEFAULT_CONNECTIONS))
    this.onProgress = onProgress
    this.onState = onState
    this.onDone = onDone
    this.onError = onError

    this.status = 'pending' // pending | downloading | paused | done | error | canceled
    this.loaded = 0
    this.speed = 0
    this._chunks = []
    this._speedWindow = []
    this._abort = null
  }

  _emitState() {
    if (this.onState) {
      this.onState({
        status: this.status,
        loaded: this.loaded,
        total: this.totalSize,
        speed: this.speed
      })
    }
  }

  _updateSpeed() {
    const now = Date.now()
    this._speedWindow.push({ t: now, loaded: this.loaded })
    while (this._speedWindow.length && now - this._speedWindow[0].t > SPEED_WINDOW_MS) {
      this._speedWindow.shift()
    }
    const first = this._speedWindow[0]
    const span = (now - first.t) / 1000
    this.speed = span > 0 ? (this.loaded - first.loaded) / span : 0
  }

  _initChunks() {
    const total = this.totalSize
    const per = Math.ceil(total / this.connections)
    this._chunks = []
    for (let i = 0; i < this.connections; i++) {
      const start = i * per
      const end = Math.min(total - 1, (i + 1) * per - 1)
      if (start > end) break
      this._chunks.push({
        index: i,
        start,
        end,
        loaded: 0,
        done: false,
        parts: [],
        retries: 0
      })
    }
    this.loaded = 0
  }

  start() {
    if (this.status === 'downloading') return
    if (!this._chunks.length) this._initChunks()
    this.status = 'downloading'
    this._abort = new AbortController()
    this._emitState()
    this._runChunks()
      .then(() => this._finalize())
      .catch((e) => this._fail(e))
  }

  // 固定并发数的 worker 池：每个 worker 依次取下一个未完成分片
  async _runChunks() {
    const chunks = this._chunks.filter((c) => !c.done)
    if (!chunks.length) return
    let idx = 0
    const worker = async () => {
      while (idx < chunks.length && this.status === 'downloading') {
        await this._fetchChunk(chunks[idx++])
      }
    }
    const count = Math.min(this.connections, chunks.length)
    await Promise.all(Array.from({ length: count }, () => worker()))
  }

  async _fetchChunk(chunk) {
    while (this.status === 'downloading') {
      try {
        const resp = await fetch(this.url, {
          headers: { Range: `bytes=${chunk.start + chunk.loaded}-${chunk.end}` },
          signal: this._abort.signal
        })
        if (resp.status !== 206 && resp.status !== 200) {
          throw new Error(`HTTP ${resp.status}`)
        }
        if (!resp.body) throw new Error('当前浏览器不支持流式读取')
        const reader = resp.body.getReader()
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          chunk.parts.push(value)
          chunk.loaded += value.byteLength
          this.loaded += value.byteLength
          if (this.onProgress) {
            this.onProgress({ loaded: this.loaded, total: this.totalSize })
          }
          this._updateSpeed()
        }
        chunk.done = true
        return
      } catch (e) {
        // 主动暂停/取消导致的中止，直接结束当前分片
        if (this.status !== 'downloading') return
        chunk.retries += 1
        if (chunk.retries > MAX_RETRIES) throw e
        await sleep(300 * chunk.retries) // 退避重试
      }
    }
  }

  _finalize() {
    if (this.status !== 'downloading') return
    const actual = this._chunks.reduce((s, c) => s + c.loaded, 0)
    if (actual !== this.totalSize) {
      this.status = 'error'
      this._emitState()
      if (this.onError) this.onError(new Error('下载数据不完整'))
      return
    }
    this.status = 'done'
    this._emitState()

    // 按分片顺序拼接 Blob 并触发保存
    const allParts = this._chunks
      .slice()
      .sort((a, b) => a.index - b.index)
      .flatMap((c) => c.parts)
    const blob = new Blob(allParts)
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = this.name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10 * 1000)

    if (this.onDone) this.onDone({ name: this.name, loaded: this.loaded, total: this.totalSize })
  }

  _fail(err) {
    if (this.status === 'canceled') return
    this.status = 'error'
    this._emitState()
    if (this.onError) this.onError(err)
  }

  // 暂停：中止未完成分片，已下载数据保留在内存，继续时从断点续拉
  pause() {
    if (this.status !== 'downloading') return
    this.status = 'paused'
    if (this._abort) this._abort.abort()
    this._speedWindow = []
    this.speed = 0
    this._emitState()
  }

  // 继续：从未完成分片的断点处重新发起 Range 请求
  resume() {
    if (this.status !== 'paused' && this.status !== 'error') return
    this.start()
  }

  // 取消：丢弃全部已下载数据
  cancel() {
    if (this.status === 'done' || this.status === 'canceled') return
    this.status = 'canceled'
    if (this._abort) this._abort.abort()
    this._emitState()
  }
}
