// 计算文件 MD5（使用 Web Worker 避免主线程卡顿）
// 由于 Vite 环境限制，这里实现为分块异步计算（时间切片），兼容所有浏览器

import SparkMD5 from 'spark-md5'

const CHUNK_SIZE = 2 * 1024 * 1024 // 2MB 每块

/**
 * 计算文件 MD5
 * @param {File} file 文件对象
 * @param {(progress: number) => void} onProgress 进度回调 0-100
 * @returns {Promise<string>} md5 hex 字符串
 */
export function computeFileMD5(file, onProgress) {
  return new Promise((resolve, reject) => {
    // 小文件直接计算
    if (file.size <= CHUNK_SIZE) {
      const reader = new FileReader()
      reader.onload = (e) => {
        const spark = new SparkMD5.ArrayBuffer()
        spark.append(e.target.result)
        onProgress && onProgress(100)
        resolve(spark.end())
      }
      reader.onerror = () => reject(new Error('读取文件失败'))
      reader.readAsArrayBuffer(file)
      return
    }

    // 大文件分块计算（时间切片，避免卡死 UI）
    const spark = new SparkMD5.ArrayBuffer()
    let currentChunk = 0
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
    let reader = new FileReader()

    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.onload = (e) => {
      spark.append(e.target.result)
      currentChunk++
      onProgress && onProgress(Math.round((currentChunk / totalChunks) * 100))
      if (currentChunk < totalChunks) {
        // 用 setTimeout 让出主线程，保持 UI 响应
        setTimeout(loadNext, 0)
      } else {
        resolve(spark.end())
      }
    }

    function loadNext() {
      const start = currentChunk * CHUNK_SIZE
      const end = Math.min(start + CHUNK_SIZE, file.size)
      const blob = file.slice(start, end)
      reader.readAsArrayBuffer(blob)
    }

    loadNext()
  })
}

/**
 * 将文件切片
 */
export function sliceFile(file, chunkSize) {
  const chunks = []
  const total = Math.ceil(file.size / chunkSize)
  for (let i = 0; i < total; i++) {
    chunks.push(file.slice(i * chunkSize, Math.min((i + 1) * chunkSize, file.size)))
  }
  return chunks
}
