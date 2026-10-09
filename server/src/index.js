import cors from 'cors'
import dotenv from 'dotenv'
import express from 'express'

dotenv.config()

const app = express()
const PORT = process.env.PORT || 3000

// 中间件
app.use(cors())
app.use(express.json())

// 健康检查（前端首页用它验证前后端连通）
app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    service: 'chuangzhibei-server',
    time: new Date().toISOString(),
  })
})

// 业务路由挂载在这里，例如：
// import userRouter from './routes/user.js'
// app.use('/api/users', userRouter)

// 404
app.use((req, res) => {
  res.status(404).json({ ok: false, message: 'Not Found' })
})

// 统一错误处理
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  console.error(err)
  res.status(err.status || 500).json({
    ok: false,
    message: err.message || 'Internal Server Error',
  })
})

app.listen(PORT, () => {
  console.log(`[server] listening on http://localhost:${PORT}`)
})

export default app
