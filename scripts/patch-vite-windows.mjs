#!/usr/bin/env node
/**
 * Windows 兼容补丁 —— 修复 Vite 在受限 Windows 环境下的 `spawn EPERM`。
 *
 * 现象
 * ----
 * 启动或构建时报：
 *
 *     [plugin externalize-deps]
 *     Error: spawn EPERM   (errno -4048, syscall 'spawn')
 *       at optimizeSafeRealPathSync (.../vite/dist/node/chunks/node.js)
 *
 * 根因
 * ----
 * Windows 下 Vite 的 `windowsSafeRealPathSync()` 会执行一次 `exec("net use")`，
 * 用来探测「网络驱动器映射」。该调用使用管道式 stdio，在禁止命名管道的受限
 * 环境（如 DSH 的 Windows 沙箱）中必然抛出 EPERM。
 *
 * 它原本是「发后即忘」的（回调内 `if (error) return;`），但错误仍会被 rolldown
 * 的插件桥接层捕获并当作致命错误，导致 `vite` / `vite build` 直接失败。
 *
 * `optimizeSafeRealPathSync()` 的第一步是 `fs.realpathSync.native(process.cwd())`：
 * 老版本 Node 处理目录时会抛 `EISDIR`，从而**提前返回、根本不会执行 `net use`**；
 * 较新的 Node（实测 v24.20.0）不再抛错，于是继续走到 `exec("net use")`，触发限制。
 *
 * 修复
 * ----
 * 把 `firstSafeRealPathSyncRun` 初值改为 `true`（等价于「已完成探测」），跳过那次
 * `net use`，直接使用 Vite 的默认实现 `fs.realpathSync.native` —— 这也正是无网络
 * 映射时该分支的同一结果。对本机本地磁盘而言 `windowsNetworkMap` 本就为空，
 * 因此**行为完全等价，不改变任何构建产物**。
 *
 * 脚本幂等；`npm install` 后重新执行即可（已挂载到 postinstall）。
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// 定位 Vite 的产物文件。既支持本仓库的 monorepo 布局（vite 装在 client/ 下），
// 也支持把本脚本直接放在任意含 node_modules 的包内的用法。
const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..') // scripts/ 的上一级
const REL = path.join('node_modules', 'vite', 'dist', 'node', 'chunks', 'node.js')

const CANDIDATES = [
  path.join(repoRoot, 'client', REL), // 本仓库：client/node_modules
  path.join(process.cwd(), REL), // 从包目录内执行
  path.join(repoRoot, REL), // 脚本就在包内（扁平布局）
]

const target = CANDIDATES.find((p) => existsSync(p))

const BEFORE = 'let firstSafeRealPathSyncRun = false;'
const AFTER = 'let firstSafeRealPathSyncRun = true;'
const DRY_RUN = process.argv.includes('--dry-run')

if (!target) {
  console.warn('[patch-vite] 跳过：未找到 Vite 产物，已尝试：')
  for (const c of CANDIDATES) console.warn('            - ' + c)
  process.exit(0)
}

console.log('[patch-vite] 目标文件：' + target)

const source = readFileSync(target, 'utf8')
const occurrences = source.split(BEFORE).length - 1

if (source.includes(AFTER)) {
  console.log('[patch-vite] 补丁已存在，无需重复应用。')
  process.exit(0)
}

console.log('[patch-vite] 匹配到 ' + occurrences + ' 处目标代码')

if (occurrences !== 1) {
  console.warn(
    '[patch-vite] 警告：预期恰好 1 处匹配，实际 ' +
      occurrences +
      ' 处。为避免误改，未做任何写入。\n' +
      '            请手动检查 ' +
      target +
      ' 中的 windowsSafeRealPathSync。'
  )
  process.exit(0)
}

if (DRY_RUN) {
  console.log('[patch-vite] dry-run：可以安全应用补丁。')
  process.exit(0)
}

writeFileSync(target, source.replace(BEFORE, AFTER))
console.log('[patch-vite] 已应用 Windows EPERM 兼容补丁。')
