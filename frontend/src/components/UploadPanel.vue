<template>
  <el-dialog
    v-model="visible"
    title="上传文件"
    width="520px"
    :close-on-click-modal="false"
    class="upload-dialog"
    @closed="onClosed"
  >
    <!-- 拖拽区域 -->
    <div
      class="drop-zone"
      :class="{ 'drag-over': dragging }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
      @click="triggerSelect"
    >
      <el-icon :size="48" color="var(--lanshare-primary)"><UploadFilled /></el-icon>
      <p class="drop-title">拖拽文件到此处，或点击选择文件</p>
      <p class="drop-tip">支持大文件分片上传 · 断点续传 · 自动秒传</p>
      <input ref="fileInput" type="file" multiple style="display:none" @change="onSelect" />
    </div>

    <!-- 上传队列 -->
    <div v-if="queue.length" class="upload-queue">
      <div v-for="item in queue" :key="item.key" class="queue-item">
        <div class="queue-info">
          <el-icon class="queue-icon" :class="item.status"><Document /></el-icon>
          <div class="queue-text">
            <span class="queue-name">{{ item.file.name }}</span>
            <span class="queue-stage">{{ item.stageText }}</span>
          </div>
          <span class="queue-size">{{ formatSize(item.file.size) }}</span>
          <el-button
            v-if="item.status === 'pending' || item.status === 'hashing' || item.status === 'uploading'"
            text size="small" type="danger" class="queue-cancel" @click="cancelItem(item)"
          >取消</el-button>
        </div>
        <el-progress
          :percentage="item.percent"
          :status="item.status === 'error' ? 'exception' : item.status === 'done' ? 'success' : undefined"
          :stroke-width="6"
        />
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { computeFileMD5 } from '../utils/md5'
import { uploadWithChunks, UploadCancelledError } from '../utils/uploader'
import { cancelUpload } from '../api'

const visible = defineModel({ type: Boolean, default: false })
const props = defineProps({
  targetDir: { type: String, default: '' }
})
const emit = defineEmits(['uploaded'])

const fileInput = ref(null)
const dragging = ref(false)
const queue = ref([])
let keyCounter = 0

// 接收全局拖拽上传的文件
function onGlobalDropFiles(e) {
  const files = e.detail
  if (files?.length) {
    visible.value = true
    addFiles(files)
  }
}
onMounted(() => window.addEventListener('lanshare-drop-files', onGlobalDropFiles))
onUnmounted(() => window.removeEventListener('lanshare-drop-files', onGlobalDropFiles))

const formatSize = (n) => {
  let size = Number(n)
  for (const unit of ['B', 'KB', 'MB', 'GB', 'TB']) {
    if (size < 1024 || unit === 'TB') return unit === 'B' ? `${size} B` : `${size.toFixed(1)} ${unit}`
    size = size / 1024
  }
  return `${n} B`
}

function triggerSelect() {
  fileInput.value?.click()
}

function onSelect(e) {
  addFiles(e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  if (e.dataTransfer?.files?.length) {
    addFiles(e.dataTransfer.files)
  }
}

function addFiles(fileList) {
  const files = Array.from(fileList)
  for (const file of files) {
    queue.value.push({
      key: ++keyCounter,
      file,
      percent: 0,
      status: 'pending',
      stageText: '等待上传',
      controller: new AbortController(),
      uploadId: null
    })
    startUpload(file, keyCounter)
  }
}

async function startUpload(file, key) {
  const item = queue.value.find((q) => q.key === key)
  if (!item) return

  try {
    // 1. 计算 MD5
    item.status = 'hashing'
    item.stageText = '计算文件指纹...'
    const md5 = await computeFileMD5(file, (p) => {
      item.percent = Math.round(p * 0.1)
    })

    // MD5 计算期间可能已被取消
    if (item.controller.signal.aborted) throw new UploadCancelledError()

    // 2. 分片上传
    item.status = 'uploading'
    item.percent = 10
    const result = await uploadWithChunks({
      file,
      md5,
      targetDir: props.targetDir,
      signal: item.controller.signal,
      onUploadId: (id) => { item.uploadId = id },
      onProgress: ({ percent, stage }) => {
        item.percent = Math.round(10 + percent * 0.9)
        item.stageText = stage
      }
    })

    item.percent = 100
    item.status = 'done'
    item.stageText = result.instant ? '秒传完成' : '上传完成'
    ElMessage.success(`${file.name} ${result.instant ? '秒传成功' : '上传成功'}`)
    emit('uploaded')
  } catch (e) {
    if (e instanceof UploadCancelledError || e.name === 'UploadCancelledError' || item.controller.signal.aborted) {
      item.status = 'cancelled'
      item.stageText = '已取消'
      return
    }
    item.status = 'error'
    item.stageText = e.message || '上传失败'
    ElMessage.error(`${file.name}: ${e.message || '上传失败'}`)
  }
}

/** 取消单个上传：中止请求 + 通知后端清理临时分片 */
function cancelItem(item) {
  if (item.status === 'done' || item.status === 'error' || item.status === 'cancelled') return
  item.controller.abort()
  item.status = 'cancelled'
  item.stageText = '正在取消...'
  // 后端清理临时分片（有 uploadId 说明已 init；无则后端还没建任务）
  if (item.uploadId) {
    cancelUpload(item.uploadId).catch(() => { /* 后端清理失败忽略，前端已停 */ })
  }
}

function onClosed() {
  // 关闭对话框后清空队列（已完成/失败条目保留供查看，此处直接清空）
  queue.value = []
  dragging.value = false
}
</script>

<style scoped>
.drop-zone {
  border: 2px dashed var(--el-border-color);
  border-radius: var(--lanshare-radius-control, 8px);
  padding: 32px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.drop-zone:hover,
.drop-zone.drag-over {
  border-color: var(--lanshare-primary);
  background: var(--el-color-primary-light-9);
}
.drop-title {
  margin-top: 12px;
  font-size: 15px;
  color: var(--lanshare-text);
}
.drop-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--lanshare-text-secondary);
}
.upload-queue {
  margin-top: 16px;
  max-height: 320px;
  overflow-y: auto;
}
.queue-item {
  padding: 8px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.queue-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.queue-icon.pending { color: var(--lanshare-text-secondary); }
.queue-icon.hashing { color: var(--lanshare-warning); }
.queue-icon.uploading { color: var(--lanshare-primary); }
.queue-icon.done { color: var(--lanshare-success); }
.queue-icon.error { color: var(--lanshare-danger); }
.queue-icon.cancelled { color: var(--lanshare-text-secondary); }
.queue-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.queue-name {
  font-size: 13px;
  color: var(--lanshare-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.queue-stage {
  font-size: 11px;
  color: var(--lanshare-text-secondary);
}
.queue-size {
  font-size: 12px;
  color: var(--lanshare-text-secondary);
  white-space: nowrap;
}
.queue-cancel {
  flex-shrink: 0;
  margin-left: 4px;
}
</style>
