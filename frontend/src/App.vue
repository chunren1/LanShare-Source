<template>
  <div class="app" @dragover.prevent @drop.prevent="onGlobalDrop">
    <!-- 访问密码 -->
    <el-dialog v-model="showPassword" title="访问验证" width="360px" :close-on-click-modal="false" :show-close="false">
      <el-input
        v-model="password"
        type="password"
        placeholder="请输入访问密码"
        show-password
        @keyup.enter="doVerify"
      />
      <template #footer>
        <el-button type="primary" :loading="verifying" @click="doVerify">确认</el-button>
      </template>
    </el-dialog>

    <!-- 二维码 -->
    <el-dialog v-model="showQr" title="手机扫码访问" width="340px">
      <div class="qr-body">
        <canvas ref="qrCanvas"></canvas>
        <p class="qr-tip">使用手机浏览器扫码，即可上传 / 下载文件</p>
        <p class="qr-addr">{{ qrText }}</p>
      </div>
    </el-dialog>

    <div class="header">
      <div class="header-title">
        <div class="header-logo">
          <el-icon :size="22" color="#fff"><FolderOpened /></el-icon>
        </div>
        <div class="header-text">
          <span class="header-name">LanShare</span>
          <span class="header-sub">局域网文件共享</span>
        </div>
      </div>
      <div class="header-actions">
        <el-button circle @click="showQr = true" title="扫码访问">
          <el-icon><Iphone /></el-icon>
        </el-button>
        <el-button circle type="primary" @click="openUpload" title="上传文件">
          <el-icon><Upload /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="breadcrumb">
        <el-button text :class="{ 'crumb-link': currentPath }" @click="goRoot">根目录</el-button>
        <template v-for="(crumb, idx) in crumbs" :key="idx">
          <el-icon class="crumb-sep"><ArrowRight /></el-icon>
          <el-button text :class="{ 'crumb-link': idx < crumbs.length - 1 }" @click="goPath(idx)">
            {{ crumb.name }}
          </el-button>
        </template>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchKw"
          placeholder="搜索文件..."
          clearable
          class="search-input"
          :prefix-icon="Search"
          @keyup.enter="doSearch"
          @clear="cancelSearch"
        />
        <el-button text title="刷新" @click="refresh">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button text title="新建文件夹" @click="showMkdir = true">
          <el-icon><FolderAdd /></el-icon>
        </el-button>
        <el-button text title="打包下载选中" :disabled="!selectedPaths.length" @click="downloadZip">
          <el-icon><Download /></el-icon>
        </el-button>
        <el-button text title="删除选中" :disabled="!selectedPaths.length" @click="deleteSelected">
          <el-icon><Delete /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 文件列表 -->
    <div class="table-wrap" :class="{ 'drag-over': globalDragging }">
      <el-table
        :data="files"
        v-loading="loading"
        @selection-change="onSelectionChange"
        @row-dblclick="onRowDblClick"
        @row-click="onRowClick"
        style="width: 100%"
        row-key="path"
        empty-text="暂无文件，点击右上角上传"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column width="52">
          <template #default="{ row }">
            <el-icon :size="26" :color="row.is_dir ? '#e6a23c' : fileIconColor(row.ext)">
              <component :is="row.is_dir ? 'Folder' : fileIcon(row.ext)" />
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <span class="file-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="size_str" label="大小" width="100" align="right" class-name="hide-on-mobile" />
        <el-table-column prop="mtime" label="修改时间" width="160" class-name="hide-on-mobile" />
        <el-table-column label="操作" width="200" align="right" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click.stop="previewRow(row)">预览</el-button>
            <el-button text type="primary" size="small" @click.stop="downloadRow(row)">下载</el-button>
            <el-button text type="danger" size="small" @click.stop="renameRow(row)">重命名</el-button>
            <el-button text type="danger" size="small" @click.stop="removeRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 存储信息 -->
    <div class="footer">
      <span class="footer-item">
        <el-icon><Coin /></el-icon>
        已用空间：{{ storageInfo.used_str || '计算中...' }}
      </span>
      <span class="footer-sep">|</span>
      <span class="footer-item">
        <el-icon><Files /></el-icon>
        当前 {{ files.length }} 个项目
      </span>
      <span v-if="storageInfo.cache" class="footer-cache">（缓存）</span>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog v-model="showPreview" :title="previewItem?.name || '预览'" width="80%" top="5vh">
      <div class="preview-body" @click.stop>
        <!-- 图片 -->
        <img v-if="previewType === 'image'" :src="previewSrc" class="preview-media" alt="预览" />
        <!-- 视频 -->
        <video v-else-if="previewType === 'video'" :src="previewSrc" class="preview-media" controls autoplay />
        <!-- 音频 -->
        <audio v-else-if="previewType === 'audio'" :src="previewSrc" class="preview-audio" controls autoplay />
        <!-- PDF -->
        <iframe v-else-if="previewType === 'pdf'" :src="previewSrc" class="preview-pdf" />
        <!-- 文本 -->
        <pre v-else-if="previewType === 'text'" class="preview-text">{{ previewText }}</pre>
        <!-- 不支持 -->
        <div v-else class="preview-unsupported">
          该类型暂不支持在线预览，请点击下载查看
          <el-button type="primary" class="preview-dl-btn" @click="downloadRow(previewItem)">下载文件</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 新建文件夹 -->
    <el-dialog v-model="showMkdir" title="新建文件夹" width="360px">
      <el-input v-model="newDirName" placeholder="请输入文件夹名称" @keyup.enter="doMkdir" />
      <template #footer>
        <el-button @click="showMkdir = false">取消</el-button>
        <el-button type="primary" @click="doMkdir">创建</el-button>
      </template>
    </el-dialog>

    <!-- 下载悬浮面板 -->
    <transition name="dl-panel">
      <div v-if="activeDownloads.length" class="download-center">
        <div class="dl-center-head">
          <span class="dl-center-title">
            <el-icon><Download /></el-icon>
            下载进度（{{ activeDownloads.length }}）
          </span>
          <el-button text size="small" @click="downloadPanelCollapsed = !downloadPanelCollapsed">
            <el-icon><ArrowUp v-if="downloadPanelCollapsed" /><ArrowDown v-else /></el-icon>
          </el-button>
        </div>
        <div v-show="!downloadPanelCollapsed" class="dl-center-body">
          <div v-for="item in activeDownloads" :key="item.id" class="dl-item">
            <div class="dl-item-main">
              <span class="dl-item-name" :title="item.name">{{ item.name }}</span>
              <span class="dl-item-status" :class="item.status">{{ statusText(item.status) }}</span>
            </div>
            <el-progress
              :percentage="Math.round((item.loaded / item.total) * 100)"
              :status="item.status === 'error' ? 'exception' : item.status === 'done' ? 'success' : undefined"
              :stroke-width="6"
              :show-text="false"
            />
            <div class="dl-item-meta">
              <span>{{ formatSize(item.loaded) }} / {{ formatSize(item.total) }}</span>
              <span v-if="item.speed > 0">{{ formatSpeed(item.speed) }}</span>
              <span class="dl-item-actions">
                <el-button
                  v-if="item.status === 'downloading'"
                  text size="small" type="warning" @click="pauseDownload(item)"
                >暂停</el-button>
                <el-button
                  v-else-if="item.status === 'paused' || item.status === 'error'"
                  text size="small" type="primary" @click="resumeDownload(item)"
                >继续</el-button>
                <el-button text size="small" type="danger" @click="cancelDownload(item)">取消</el-button>
              </span>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 上传面板 -->
    <UploadPanel v-model="showUpload" :target-dir="currentPath" @uploaded="refresh" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import QRCode from 'qrcode'
import UploadPanel from './components/UploadPanel.vue'
import {
  listFiles, deleteFile, renameFile, mkdir, getStorage, getNetwork,
  downloadUrl, zipDownloadUrl, withToken,
  getAuthStatus, verifyPassword
} from './api'
import { shouldUseDownloader, createDownloadTask } from './utils/downloader'

// ===== 状态 =====
const currentPath = ref('')
const files = ref([])
const loading = ref(false)
const selectedPaths = ref([])
const storageInfo = ref({})
const searchKw = ref('')
const isSearching = ref(false)

// 上传
const showUpload = ref(false)
// 二维码
const showQr = ref(false)
const qrText = ref('')
const qrCanvas = ref(null)
// 密码
const showPassword = ref(false)
const password = ref('')
const verifying = ref(false)
// 新建文件夹
const showMkdir = ref(false)
const newDirName = ref('')
// 预览
const showPreview = ref(false)
const previewItem = ref(null)
const previewSrc = ref('')
const previewText = ref('')
const previewType = ref('')
// 全局拖拽
const globalDragging = ref(false)
// 活动下载任务（P0：悬浮下载面板）
const activeDownloads = ref([])
const downloadPanelCollapsed = ref(false)

// ===== 计算属性 =====
const crumbs = computed(() => {
  if (!currentPath.value) return []
  return currentPath.value.split('/').map((name, idx) => ({
    name,
    path: currentPath.value.split('/').slice(0, idx + 1).join('/')
  }))
})

const previewableExts = {
  image: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'],
  video: ['mp4', 'webm', 'ogv', 'mov', 'm4v'],
  audio: ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'],
  pdf: ['pdf'],
  text: ['txt', 'md', 'log', 'json', 'js', 'ts', 'py', 'html', 'css', 'xml', 'yml', 'yaml', 'ini', 'conf', 'csv', 'sh', 'bat', 'vue', 'java', 'go', 'c', 'cpp', 'sql']
}

// ===== 文件图标 =====
const fileIcon = (ext) => {
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'].includes(ext)) return 'Picture'
  if (['mp4', 'webm', 'mov', 'mkv', 'avi'].includes(ext)) return 'VideoCamera'
  if (['mp3', 'wav', 'ogg', 'flac', 'aac'].includes(ext)) return 'Headset'
  if (['pdf'].includes(ext)) return 'Document'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return 'Box'
  if (['doc', 'docx'].includes(ext)) return 'Document'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'Document'
  if (['ppt', 'pptx'].includes(ext)) return 'Document'
  if (['exe', 'msi', 'apk', 'dmg'].includes(ext)) return 'Cpu'
  if (['txt', 'md', 'log', 'json', 'js', 'py', 'html', 'css'].includes(ext)) return 'Memo'
  return 'Document'
}
const fileIconColor = (ext) => {
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return '#67c23a'
  if (['mp4', 'webm', 'mov', 'mkv'].includes(ext)) return '#409eff'
  if (['zip', 'rar', '7z', 'tar'].includes(ext)) return '#e6a23c'
  if (['exe', 'msi', 'apk'].includes(ext)) return '#f56c6c'
  return '#909399'
}

// ===== 数据加载 =====
async function refresh() {
  loading.value = true
  try {
    if (isSearching.value) {
      // 搜索结果模式（简单起见：搜索后停在当前视图）
      isSearching.value = false
    }
    files.value = await listFiles(currentPath.value)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function refreshStorage() {
  try {
    storageInfo.value = await getStorage()
  } catch (e) { /* ignore */ }
}

// ===== 自动轮询（多端同步：外部删除/新增/上传后自动刷新） =====
let pollTimer = null
const POLL_INTERVAL = 5000 // 轮询间隔：5 秒

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    // 加载中 / 搜索模式下跳过，避免干扰用户操作
    if (loading.value || isSearching.value) return
    try {
      files.value = await listFiles(currentPath.value)
    } catch (e) {
      /* 静默忽略：避免频繁弹错；401 由 api 层统一派发认证事件 */
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ===== 导航 =====
function goRoot() {
  currentPath.value = ''
  refresh()
}
function goPath(idx) {
  currentPath.value = crumbs.value[idx].path
  refresh()
}
function onRowDblClick(row) {
  if (row.is_dir) {
    currentPath.value = row.path
    refresh()
  }
}
function onRowClick(row) {
  // 单击文件夹进入（移动端友好）
  if (row.is_dir) {
    currentPath.value = row.path
    refresh()
  }
}

// ===== 选择 =====
function onSelectionChange(rows) {
  selectedPaths.value = rows.map((r) => r.path)
}

// ===== 搜索 =====
async function doSearch() {
  const kw = searchKw.value.trim()
  if (!kw) return
  isSearching.value = true
  loading.value = true
  try {
    const { searchFiles } = await import('./api')
    files.value = await searchFiles(currentPath.value, kw)
    ElMessage.success(`找到 ${files.value.length} 个结果`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
function cancelSearch() {
  isSearching.value = false
  refresh()
}

// ===== 下载 =====
function formatSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return ''
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  let v = bytesPerSec
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)} ${units[i]}`
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`
}

function statusText(status) {
  const map = { downloading: '下载中', paused: '已暂停', done: '已完成', error: '失败', canceled: '已取消', pending: '等待中' }
  return map[status] || status
}

function updateDownload(itemId, patch) {
  const item = activeDownloads.value.find((d) => d.id === itemId)
  if (item) Object.assign(item, patch)
}

function onDownloadState(itemId, { status, speed }) {
  updateDownload(itemId, { status, speed })
}

function pauseDownload(item) {
  item.task?.pause()
  updateDownload(item.id, { status: 'paused' })
}

function resumeDownload(item) {
  item.task?.resume()
  updateDownload(item.id, { status: 'downloading' })
}

function cancelDownload(item) {
  item.task?.cancel()
  const idx = activeDownloads.value.findIndex((d) => d.id === item.id)
  if (idx !== -1) activeDownloads.value.splice(idx, 1)
}

function downloadRow(row) {
  if (row.is_dir) {
    // 目录 → 打包下载（ZIP 流式后端已优化，仍走浏览器跳转）
    window.location.href = withToken(zipDownloadUrl([row.path]))
    return
  }
  if (shouldUseDownloader(row.size)) {
    const item = {
      id: 0,
      name: row.name,
      total: row.size,
      loaded: 0,
      speed: 0,
      status: 'downloading',
      task: null
    }
    const task = createDownloadTask({
      url: downloadUrl(row.path),
      name: row.name,
      totalSize: row.size,
      onProgress: ({ loaded }) => updateDownload(item.id, { loaded }),
      onState: (s) => onDownloadState(item.id, s),
      onDone: () => {
        ElMessage.success(`「${row.name}」下载完成`)
        setTimeout(() => {
          const idx = activeDownloads.value.findIndex((d) => d.id === item.id)
          if (idx !== -1) activeDownloads.value.splice(idx, 1)
        }, 1500)
      },
      onError: (e) => {
        updateDownload(item.id, { status: 'error' })
        ElMessage.error(`「${row.name}」下载失败：${e.message}`)
      }
    })
    item.id = task.id
    item.task = task
    activeDownloads.value.push(item)
    task.start()
  } else {
    // 小文件 / 不支持分片 / 超大文件 → 原生跳转下载
    window.location.href = withToken(downloadUrl(row.path))
  }
}
function downloadZip() {
  if (!selectedPaths.value.length) return
  window.location.href = withToken(zipDownloadUrl(selectedPaths.value))
}

// ===== 删除 =====
async function removeRow(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」吗？${row.is_dir ? '目录内容将一并删除！' : ''}`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch (e) { return }
  try {
    await deleteFile(row.path)
    ElMessage.success('删除成功')
    refresh()
    refreshStorage()
  } catch (e) {
    ElMessage.error(e.message)
  }
}
async function deleteSelected() {
  if (!selectedPaths.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedPaths.value.length} 个项目吗？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch (e) { return }
  try {
    for (const p of selectedPaths.value) {
      await deleteFile(p)
    }
    ElMessage.success('删除完成')
    selectedPaths.value = []
    refresh()
    refreshStorage()
  } catch (e) {
    ElMessage.error(e.message)
    refresh()
  }
}

// ===== 重命名 =====
async function renameRow(row) {
  let newName = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', '重命名', {
      inputValue: row.name,
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    newName = value.trim()
  } catch (e) { return }
  if (!newName || newName === row.name) return
  try {
    await renameFile(row.path, newName)
    ElMessage.success('重命名成功')
    refresh()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ===== 新建文件夹 =====
async function doMkdir() {
  const name = newDirName.value.trim()
  if (!name) return
  const target = currentPath.value ? `${currentPath.value}/${name}` : name
  try {
    await mkdir(target)
    ElMessage.success('创建成功')
    showMkdir.value = false
    newDirName.value = ''
    refresh()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ===== 上传 =====
function openUpload() {
  showUpload.value = true
}

// ===== 全局拖拽上传 =====
let dragCounter = 0
function onGlobalDrop(e) {
  dragCounter = 0
  globalDragging.value = false
  const filesList = Array.from(e.dataTransfer?.files || [])
  if (filesList.length) {
    // 交给 UploadPanel 处理（面板自动打开并加入队列）
    window.dispatchEvent(new CustomEvent('lanshare-drop-files', { detail: filesList }))
  }
}

// ===== 预览 =====
async function previewRow(row) {
  if (row.is_dir) return
  const ext = row.ext
  previewItem.value = row
  previewType.value = ''
  previewSrc.value = ''
  previewText.value = ''

  let type = 'none'
  for (const [t, exts] of Object.entries(previewableExts)) {
    if (exts.includes(ext)) { type = t; break }
  }

  if (type === 'image' || type === 'video' || type === 'audio' || type === 'pdf') {
    previewType.value = type
    previewSrc.value = withToken(downloadUrl(row.path))
  } else if (type === 'text') {
    previewType.value = 'text'
    try {
      const resp = await fetch(withToken(downloadUrl(row.path)))
      if (!resp.ok) throw new Error('加载失败')
      // 限制预览大小
      const text = await resp.text()
      previewText.value = text.length > 200000 ? text.slice(0, 200000) + '\n... (内容过长，已截断)' : text
    } catch (e) {
      previewText.value = '文本加载失败'
    }
  } else {
    previewType.value = 'none'
  }
  showPreview.value = true
}

// ===== 二维码 =====
async function showQrCode() {
  try {
    const net = await getNetwork()
    const ips = (net.ips || []).filter(Boolean)
    if (!ips.length) {
      // 后端没探测到局域网 IP（可能无网络/未连网卡）
      ElMessage.warning('未检测到局域网地址，请确认电脑已联网后重试')
      return
    }
    const ip = ips[0]
    qrText.value = `http://${ip}:${net.port}`
    showQr.value = true
    await nextTick()
    if (qrCanvas.value) {
      QRCode.toCanvas(qrCanvas.value, qrText.value, { width: 260, margin: 2 })
    }
  } catch (e) {
    ElMessage.error('获取网络信息失败')
  }
}

// ===== 密码验证 =====
async function checkAuth() {
  try {
    const status = await getAuthStatus()
    if (status.enabled) {
      // 检查是否已有 token（简单判断：尝试请求 files）
      try {
        await listFiles('')
      } catch (e) {
        if (e.message === '需要访问密码') {
          showPassword.value = true
        }
      }
    }
  } catch (e) { /* ignore */ }
}
async function doVerify() {
  if (!password.value) return
  verifying.value = true
  try {
    const res = await verifyPassword(password.value)
    if (res.token) {
      localStorage.setItem('lanshare_token', res.token)
      showPassword.value = false
      password.value = ''
      ElMessage.success('验证成功')
      refresh()
    }
  } catch (e) {
    ElMessage.error('密码错误')
  } finally {
    verifying.value = false
  }
}

// ===== 生命周期 =====
onMounted(() => {
  checkAuth().then(() => refresh())
  refreshStorage()
  startPolling()

  // 认证失败事件
  window.addEventListener('lanshare-auth-fail', () => {
    localStorage.removeItem('lanshare_token')
    showPassword.value = true
  })

  // 全局拖拽高亮
  document.addEventListener('dragover', (e) => {
    e.preventDefault()
    if (dragCounter === 0) globalDragging.value = true
    dragCounter++
  })
  document.addEventListener('dragleave', (e) => {
    dragCounter = Math.max(0, dragCounter - 1)
    if (dragCounter === 0) globalDragging.value = false
  })
})

// 组件卸载时清理轮询定时器，避免内存泄漏
onBeforeUnmount(stopPolling)

watch(showQr, (v) => { if (v) showQrCode() })
</script>

<style scoped>
.app {
  height: 100%;
  display: flex;
  flex-direction: column;
}
/* ===== 品牌渐变头部 ===== */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--lanshare-gradient);
  color: #fff;
  box-shadow: 0 4px 20px rgba(37, 99, 235, 0.25);
  flex-shrink: 0;
}
.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-logo {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.header-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.header-name {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.header-sub {
  font-size: 12px;
  opacity: 0.85;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.header-actions :deep(.el-button) {
  border: 1px solid rgba(255, 255, 255, 0.35);
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  transition: all 0.2s ease;
}
.header-actions :deep(.el-button:hover) {
  background: rgba(255, 255, 255, 0.32);
}
.header-actions :deep(.el-button--primary) {
  background: #fff;
  border-color: #fff;
  color: var(--lanshare-primary);
}
.header-actions :deep(.el-button--primary:hover) {
  background: #eef3ff;
  color: var(--lanshare-primary-dark);
}
/* ===== 工具栏 ===== */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}
.crumb-link {
  color: var(--lanshare-primary);
}
.crumb-sep {
  color: #c0c4cc;
  font-size: 12px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
}
.search-input {
  width: 200px;
  margin-right: 8px;
}
/* ===== 文件列表卡片 ===== */
.table-wrap {
  flex: 1;
  overflow: auto;
  margin: 8px 20px 16px;
  padding: 4px 12px;
  background: var(--lanshare-card);
  border-radius: var(--lanshare-radius-card);
  box-shadow: var(--lanshare-shadow-card);
  transition: all 0.2s;
}
.file-name {
  cursor: pointer;
}
.file-name:hover {
  color: var(--lanshare-primary);
}
/* ===== 存储信息卡片 ===== */
.footer {
  flex-shrink: 0;
  margin: 0 20px 20px;
  padding: 10px 16px;
  font-size: 12px;
  color: var(--lanshare-text-secondary);
  background: var(--lanshare-card);
  border-radius: var(--lanshare-radius-card);
  box-shadow: var(--lanshare-shadow-card);
  display: flex;
  align-items: center;
}
.footer-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.footer-cache {
  margin-left: 8px;
  font-size: 11px;
  color: #9ca3af;
}
.footer-sep {
  margin: 0 8px;
  color: #d1d5db;
}
.qr-body {
  text-align: center;
  padding: 8px;
}
.qr-tip {
  margin-top: 12px;
  font-size: 13px;
  color: var(--lanshare-text-secondary);
}
.qr-addr {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
  word-break: break-all;
}
.preview-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
.preview-media {
  max-width: 100%;
  max-height: 70vh;
  border-radius: 10px;
}
.preview-audio {
  width: 100%;
  max-width: 600px;
}
.preview-pdf {
  width: 100%;
  height: 70vh;
  border: 1px solid var(--lanshare-border);
  border-radius: 10px;
}
.preview-text {
  width: 100%;
  max-height: 70vh;
  overflow: auto;
  background: #f8fafd;
  border: 1px solid var(--lanshare-border);
  border-radius: 10px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
}
.preview-unsupported {
  text-align: center;
  color: var(--lanshare-text-secondary);
  padding: 40px 0;
}
.preview-dl-btn {
  display: block;
  margin: 20px auto 0;
}

/* ===== 下载悬浮面板 ===== */
.download-center {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 2000;
  width: 340px;
  max-width: calc(100vw - 40px);
  background: var(--lanshare-card, #fff);
  border: 1px solid var(--lanshare-border, #ebeef5);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.16);
  overflow: hidden;
}
.dl-center-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--lanshare-gradient);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
}
.dl-center-title {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dl-center-body {
  padding: 10px 12px;
  max-height: 280px;
  overflow-y: auto;
}
.dl-item {
  padding: 8px 0;
  border-bottom: 1px dashed #e4e7ed;
}
.dl-item:last-child {
  border-bottom: none;
}
.dl-item-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.dl-item-name {
  flex: 1;
  font-size: 13px;
  color: var(--lanshare-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dl-item-status {
  font-size: 12px;
  flex-shrink: 0;
}
.dl-item-status.downloading { color: #2563eb; }
.dl-item-status.paused { color: #e6a23c; }
.dl-item-status.done { color: #10b981; }
.dl-item-status.error { color: #ef4444; }
.dl-item-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.dl-item-actions {
  margin-left: auto;
  display: flex;
  gap: 2px;
}
.dl-panel-enter-active,
.dl-panel-leave-active {
  transition: all 0.25s ease;
}
.dl-panel-enter-from,
.dl-panel-leave-to {
  opacity: 0;
  transform: translateY(16px);
}
</style>
