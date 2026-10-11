/**
 * 密码强度评估。
 * 登录、注册、修改密码三处复用，保证提示口径一致。
 */

const COMMON_WEAK = new Set([
  '123456',
  '1234567',
  '12345678',
  '123456789',
  'password',
  'passw0rd',
  'qwerty',
  'qwerty123',
  'abc123',
  'admin',
  'admin123',
  'iloveyou',
  '111111',
  '000000',
  '666666',
  '888888',
  'a123456',
])

export const PASSWORD_MIN_LENGTH = 6
export const PASSWORD_MAX_LENGTH = 64
export const PASSWORD_RECOMMENDED_LENGTH = 8

/**
 * @param {string} input 待评估的密码
 * @param {string} [username] 用户名，用于提示「不要与用户名相同」
 * @returns {{ score: 0|1|2|3|4, level: string, label: string, percent: number, color: string, tips: string[] }}
 */
export function evaluatePassword(input, username = '') {
  const value = String(input ?? '')

  if (!value) {
    return {
      score: 0,
      level: 'empty',
      label: '未填写',
      percent: 0,
      color: 'app-active',
      tips: ['建议使用 8 位以上，包含大小写字母、数字与符号的组合'],
    }
  }

  let score = 0
  if (value.length >= PASSWORD_MIN_LENGTH) score += 1
  if (value.length >= PASSWORD_RECOMMENDED_LENGTH) score += 1
  if (/[A-Za-z]/.test(value) && /\d/.test(value)) score += 1
  if (/[^A-Za-z0-9]/.test(value)) score += 1

  // 明显弱口令直接压到最低档
  const repeated = /^(.)\1+$/.test(value)
  if (repeated || COMMON_WEAK.has(value.toLowerCase())) score = 1
  if (value.length < PASSWORD_MIN_LENGTH) score = Math.min(score, 1)

  const levels = {
    0: { level: 'empty', label: '未填写', color: 'app-active' },
    1: { level: 'weak', label: '弱', color: 'bg-red-500' },
    2: { level: 'fair', label: '一般', color: 'bg-amber-500' },
    3: { level: 'good', label: '强', color: 'bg-emerald-500' },
    4: { level: 'strong', label: '很强', color: 'bg-brand-light' },
  }

  const tips = []
  if (value.length < PASSWORD_RECOMMENDED_LENGTH) tips.push('长度建议不少于 8 位')
  if (!/[A-Za-z]/.test(value)) tips.push('加入字母可以更安全')
  if (!/\d/.test(value)) tips.push('加入数字可以更安全')
  if (!/[^A-Za-z0-9]/.test(value)) tips.push('加入符号（如 !@#）可以更安全')
  if (repeated) tips.push('不要使用重复的单一字符')
  if (username && value.toLowerCase() === String(username).toLowerCase()) {
    tips.push('不要与用户名相同')
  }

  return {
    score,
    percent: (score / 4) * 100,
    ...levels[score],
    tips: tips.slice(0, 2),
  }
}
