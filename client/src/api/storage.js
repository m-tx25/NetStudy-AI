import request from './request'

/** 存储状态：磁盘容量、配额、上传限制（由后端配置决定，前端不写死） */
export function fetchStorageStatus(config = {}) {
  return request.get('/storage/status', { silent: true, ...config })
}
