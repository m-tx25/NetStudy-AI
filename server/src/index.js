import express from 'express'

const app = express()
const PORT = Number(process.env.PORT ?? 3000)

app.use(express.json())

// 健康检查：前端「检测后端」按钮就是打这个接口
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    time: new Date().toISOString(),
    uptime: process.uptime(),
  })
})

// 示例接口：后续业务路由建议拆到 server/src/routes/ 下再挂载
app.get('/api/hello', (req, res) => {
  const name = req.query.name ?? 'world'
  res.json({ message: `hello, ${name}` })
})

app.use((req, res) => {
  res.status(404).json({ error: 'Not Found', path: req.originalUrl })
})

app.listen(PORT, () => {
  console.log(`[server] listening on http://localhost:${PORT}`)
})
