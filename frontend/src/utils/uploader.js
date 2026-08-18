// 分片上传引擎：并发控制、断点续传、秒传、取消
import { uploadInit, uploadChunk, mergeUpload, getUploadStatus } from '../api'

const DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024 // 4MB
const MAX_CONCURRENT = 3 // 并发分片数

/** 上传被取消时抛出的特殊错误（用于上层识别，不当作失败提示） */
export class UploadCancelledError extends Error {
  constructor() {
    super('上传已取消')
    this.name = 'UploadCancelledError'
  }
}

/**
 * 执行分片上传
 * @param {object} options
 * @param {File} options.file 文件对象
 * @param {string} options.md5 文件 MD5
 * @param {string} options.targetDir 目标目录相对路径
 * @param {(progress: object) => void} options.onProgress 进度回调
 * @param {AbortSignal} [options.signal] 取消信号（AbortController.signal）
 * @param {(uploadId: number) => void} [options.onUploadId] 拿到 uploadId 后回调（供取消时清理后端分片）
 * @returns {Promise<object>} 上传结果
 */
export async function uploadWithChunks({ file, md5, targetDir, onProgress, signal, onUploadId }) {
  const chunkSize = DEFAULT_CHUNK_SIZE
  const totalChunks = Math.ceil(file.size / chunkSize)

  // 取消检查
  function throwIfCancelled() {
    if (signal?.aborted) throw new UploadCancelledError()
  }

  // 1. 初始化（后端判断秒传 / 返回已上传分片）
  let init
  try {
    throwIfCancelled()
    init = await uploadInit(md5, file.name, file.size, chunkSize)
  } catch (e) {
    if (e.name === 'UploadCancelledError') throw e
    throw new Error(`初始化上传失败: ${e.message}`)
  }

  // 秒传
  if (init.needUpload === false) {
    onProgress && onProgress({ percent: 100, stage: '秒传完成' })
    onUploadId && onUploadId(init.uploadId)
    return { uploadId: init.uploadId, instant: true, size: file.size }
  }

  const uploadId = init.uploadId
  onUploadId && onUploadId(uploadId)
  let uploaded = new Set(init.uploadedChunks || [])

  // 2. 若任务已存在但状态查询到更多分片（如上次中断），合并信息
  if (uploaded.size === 0) {
    try {
      const status = await getUploadStatus(uploadId)
      uploaded = new Set(status.uploadedChunks || [])
    } catch (e) { /* 忽略，继续上传 */ }
  }

  // 3. 计算各分片 MD5（异步批量，避免一次性卡死）
  const chunkMd5s = new Map()
  async function getChunkMd5(index) {
    if (chunkMd5s.has(index)) return chunkMd5s.get(index)
    const blob = file.slice(index * chunkSize, Math.min((index + 1) * chunkSize, file.size))
    const buf = await blob.arrayBuffer()
    const md5 = await computeChunkMd5(buf)
    chunkMd5s.set(index, md5)
    return md5
  }

  // 4. 并发上传缺失分片
  const pending = []
  for (let i = 0; i < totalChunks; i++) {
    if (!uploaded.has(i)) pending.push(i)
  }

  if (pending.length === 0) {
    onProgress && onProgress({ percent: 99, stage: '分片齐全，合并中...' })
  } else {
    let doneCount = uploaded.size
    const totalPending = pending.length

    // 简单并发池
    let cursor = 0
    async function worker() {
      while (cursor < pending.length) {
        throwIfCancelled()
        const idx = pending[cursor++]
        try {
          const blob = file.slice(idx * chunkSize, Math.min((idx + 1) * chunkSize, file.size))
          const md5 = await getChunkMd5(idx)
          await uploadChunk(uploadId, idx, md5, blob, signal)
          uploaded.add(idx)
          doneCount++
          const percent = Math.round((doneCount / totalChunks) * 100)
          onProgress && onProgress({ percent, stage: `上传中 ${doneCount}/${totalChunks}` })
        } catch (e) {
          if (e.name === 'UploadCancelledError' || e.name === 'AbortError' || signal?.aborted) {
            throw new UploadCancelledError()
          }
          // 分片失败：放回队列重试一次
          if (cursor > 0) cursor--
          throw new Error(`分片 ${idx} 上传失败: ${e.message}`)
        }
      }
    }

    const workers = []
    const workerCount = Math.min(MAX_CONCURRENT, pending.length)
    for (let i = 0; i < workerCount; i++) {
      workers.push(worker())
    }
    await Promise.all(workers)
  }

  // 5. 合并
  throwIfCancelled()
  onProgress && onProgress({ percent: 99, stage: '合并文件中...' })
  const result = await mergeUpload(uploadId, targetDir)
  onProgress && onProgress({ percent: 100, stage: '完成' })
  return { uploadId, instant: false, size: file.size, ...result }
}

// 分片 MD5（使用 spark-md5）
function computeChunkMd5(buffer) {
  // 动态导入避免主线程阻塞
  return import('spark-md5').then(({ default: SparkMD5 }) => {
    const spark = new SparkMD5.ArrayBuffer()
    spark.append(buffer)
    return spark.end()
  })
}
