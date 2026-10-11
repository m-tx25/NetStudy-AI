/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // 与 style.css 里的 --app-accent / --el-color-primary 保持一致
        brand: {
          DEFAULT: '#0f9b7a',
          hover: '#0b7c62',
          soft: 'rgba(15, 155, 122, 0.12)',
          light: '#2fd1a6',
        },
        // 深灰科技风底色阶梯（首页 / 装饰用）
        ink: {
          900: '#0b0e12',
          800: '#101318',
          700: '#151a20',
          600: '#1a2028',
          500: '#232a33',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'Roboto',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'SF Mono',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'bounce-dot': {
          '0%, 80%, 100%': { transform: 'translateY(0)', opacity: '0.45' },
          '40%': { transform: 'translateY(-4px)', opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '0.35' },
          '50%': { opacity: '0.7' },
        },
        scan: {
          from: { transform: 'translateY(-100%)' },
          to: { transform: 'translateY(400%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.22s ease-out both',
        'bounce-dot': 'bounce-dot 1.2s ease-in-out infinite',
        float: 'float 6s ease-in-out infinite',
        'pulse-glow': 'pulse-glow 4.5s ease-in-out infinite',
        scan: 'scan 3.6s linear infinite',
      },
    },
  },
  plugins: [],
}
