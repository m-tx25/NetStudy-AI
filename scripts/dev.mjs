/**
 * 根目录一键启动：同时跑前端（Vite）和后端（Python + FastAPI）。
 *
 *   npm run dev              # 前端 + 后端
 *   npm run dev -- --client  # 只跑前端（Mock 模式完全够用）
 *   npm run dev -- --server  # 只跑后端
 *
 * 说明：这里用 stdio: 'inherit' 而不是管道，受管环境下管道会以 EPERM 失败；
 *      输出直接打印到当前终端，Ctrl+C 会同时结束两个子进程。
 *
 * 历史：后端最初是 Express（server 下的 npm start），后来迁到 Python + FastAPI，
 *      这里若仍按 Express 启动会「跳过后端 / 后端立刻退出」，前端随之被一起收掉。
 *      因此后端改为用 server/.venv 里的解释器跑 uvicorn。
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const IS_WIN = process.platform === 'win32'
const VENV_PYTHON = join(ROOT, 'server', '.venv', IS_WIN ? 'Scripts/python.exe' : 'bin/python')

const targets = [
  {
    name: 'client',
    label: '前端',
    cwd: join(ROOT, 'client'),
    command: 'npm run dev',
    hint: 'http://localhost:5173',
    ready: () => existsSync(join(ROOT, 'client', 'node_modules')),
    missing: 'client/node_modules 不存在，先执行 npm run install:client',
  },
  {
    name: 'server',
    label: '后端',
    cwd: join(ROOT, 'server'),
    command: `"${VENV_PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload`,
    hint: 'http://127.0.0.1:3000/docs',
    ready: () => existsSync(VENV_PYTHON),
    missing: 'server/.venv 不存在，先在 server 目录执行 .\\start.ps1 建虚拟环境并装依赖',
  },
]

const flags = process.argv.slice(2)
const only = flags.includes('--client') || flags.includes('--server')
const picked = only
  ? targets.filter((item) => flags.includes(`--${item.name}`))
  : targets

if (!picked.length) {
  console.error('用法：npm run dev [-- --client | -- --server]')
  process.exit(1)
}

const children = []

for (const target of picked) {
  if (!target.ready()) {
    console.warn(`[dev] 跳过${target.label}：${target.missing}`)
    continue
  }

  console.log(`[dev] 启动${target.label}：${target.command}  (${target.hint})`)

  const child = spawn(target.command, {
    cwd: target.cwd,
    stdio: 'inherit',
    shell: true,
    windowsHide: true,
  })

  child.on('exit', (code) => {
    if (stopping) return
    console.log(`[dev] ${target.label}已退出（exit ${code ?? 0}）`)
    // 一个退了就把另一个也收掉，避免留下孤儿进程
    shutdown()
  })

  child.on('error', (error) => {
    console.error(`[dev] ${target.label}启动失败：${error.message}`)
  })

  children.push(child)
}

if (!children.length) {
  console.error('[dev] 没有可启动的进程，请先执行 npm run install:all')
  process.exit(1)
}

let stopping = false

function shutdown() {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) {
      try {
        child.kill()
      } catch {
        /* ignore */
      }
    }
  }
  setTimeout(() => process.exit(0), 300)
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
