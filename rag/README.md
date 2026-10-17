# RAG 检索模块

把 PDF 语料切片、向量化，存入本地 ChromaDB，并提供检索验证工具。

这一块和仓库里的 Vue + Express 主项目是**相互独立**的：主项目是 Web 应用，这里是 Python 的
检索底座（后续如果需要"文档问答"功能，可以作为后端服务接进主项目）。

---

## 目录结构

```
rag/
├── build_db.py        建库脚本：PDF → 切片 → 向量化 → ChromaDB
├── query_db.py        检索脚本：提问 → 向量检索（可叠加关键词混合检索）
├── requirements.txt   依赖清单
├── .env.example       环境变量模板（复制为 .env 后填 Key）
├── .env               本机密钥（已被 gitignore，不要提交）
├── test.pdf           测试语料（已提交）
└── chroma_db/         向量库（本地生成，已被 gitignore）
```

---

## 快速开始

```powershell
cd rag

# 1) 安装依赖
pip install -r requirements.txt

# 2) 配置 API Key
Copy-Item .env.example .env
# 编辑 .env，把 your-key-here 换成你的智谱 Key

# 3) 建库（先试跑 20 页确认链路，再跑全量）
python build_db.py --provider zhipu --limit-pages 20 --dry-run   # 只看切片，不调 API
python build_db.py --provider zhipu --rebuild                    # 全量建库

# 4) 检索验证
python query_db.py --info                       # 看库的统计
python query_db.py -q "综合布线的长度限制"        # 单次提问
python query_db.py                              # 交互模式
```

实测在本机（Python 3.13）：83 页 / 5.0 万字符 → 148 条切片，建库耗时约 **4.4 秒**，
费用约几分钱（智谱 embedding-3 单价 0.5 元/百万 tokens）。

---

## 为什么用智谱 embedding-3

- **DeepSeek 没有 embedding 接口**：实测 `POST /api/deepseek.com/embeddings` 返回 404，
  其开放平台只有对话模型（`deepseek-flash`、`deepseek-v4-pro`）。所以建向量库用不了 DeepSeek，
  它只能用在后续"检索 + 生成"的**生成**环节。

- 智谱向量模型有两个，**价格相同**（都是 0.5 元/百万 tokens，Batch 0.25）：

  | 模型 | 代次 | 向量维度 | 说明 |
  | --- | --- | --- | --- |
  | **embedding-3** | V3 | 256~2048 可自定义（默认 2048） | 语义更强，本模块采用 |
  | embedding-2 | V2 | 固定 | 旧版 |

- 注意：LangChain 的 `ZhipuAIEmbeddings` 内部 import 的是**旧包 `zhipuai`**，
  不是智谱现在主推的 `zai-sdk`——走 LangChain 就必须装 `zhipuai`。

---

## 关键实现说明

### 1. Unicode 归一化（重要）

Chrome/Skia 导出的 PDF，文本层常把汉字写成 **Unicode 兼容码位**：

| 看到的字 | 实际码位 | 标准汉字 |
| --- | --- | --- |
| ⼀ | U+2F00 康熙部首 | 一 U+4E00 |
| ⼆ | U+2F02 | 二 U+4E8C |
| ⻓ | U+2ED3 CJK部首补充 | 长 U+957F |

它们屏幕上一样，但码位不同。实测本语料里的分布：

```
Kangxi Radicals (2F00-2FDF)     1567 个
CJK Radicals Suppl (2E80-2EFF)    90 个
Halfwidth/Fullwidth (FF00-FFEF) 2285 个
```

**不修的话，用标准汉字搜关键词直接搜不到：**

```
流水线   归一化前 0 次  →  归一化后 12 次
二进制   归一化前 0 次  →  归一化后 13 次
子网掩码  归一化前 0 次  →  归一化后  7 次
```

`build_db.py` 在读取后会做 **NFKC 归一化**，把变体字映射回标准形式，并在日志里报告
修正了多少个字符。这个步骤不需要额外依赖（Python 标准库 `unicodedata`）。

> 副作用：NFKC 也会把全角标点转成半角（`（` → `(`、`：` → `:`）。对检索无影响。

### 2. 切片参数

- `RecursiveCharacterTextSplitter`，`chunk_size=500`、`chunk_overlap=50`
- 分隔符改成**中文优先**：`["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""]`
  （默认是英文标点，对中文 PDF 切得不好）
- 每条切片用 `文件-序号-哈希` 作稳定 ID，重复建库不会产生重复条目

### 3. 检索质量（实测，别期待过高）

对同一份语料，全量排序后正确切片的排名：

| 提问 | 正确切片排名 |
| --- | --- |
| 「流水线的加速比怎么算」 | **1 / 148** ✅ |
| 「流水线相关计算」 | **2 / 148** ✅ |
| 「什么是流水线」 | 8 / 148 ⚠️ |

**结论：提问越具体，命中越准。** 空泛提问（"什么是X"）容易把语义相近但不切题的段落排到前面——
这是 embedding 检索的固有特性，靠调参解决不了。

两种模式可对比使用：

```powershell
python query_db.py -q "流水线相关计算"              # 纯向量
python query_db.py -q "流水线相关计算" --hybrid     # 向量 + 关键词重排
```

`--hybrid` 对**术语/公式类**提问（考试、手册文档）提升明显，因为它额外统计了词面命中。

### 4. 页码字段

Chroma 的元数据里有两个页码，别搞混：

- `page`：**0 基**索引（PyPDFLoader 的默认行为）
- `page_label`：**人类可读**页码（1 基），引用时用这个

---

## 常见问题

**Q: 报「未找到智谱 API Key」**

`.env` 里变量名必须是 `ZHIPUAI_API_KEY`。**特别注意 BOM 问题**：Windows 上用
`Set-Content -Encoding UTF8` 写文件会带 UTF-8 BOM，导致变量名变成 `\ufeffZHIPUAI_API_KEY`，
读起来就像"没设置"。而 `python-dotenv` 遇到 BOM **不报错、静默失败**。

正确写法：

```powershell
$enc = New-Object System.Text.UTF8Encoding($false)   # false = 不加 BOM
[System.IO.File]::WriteAllText('E:\传智杯web\rag\.env', "ZHIPUAI_API_KEY=你的key`n", $enc)
```

`build_db.py` / `query_db.py` 都已用 `utf-8-sig` 解码并自行解析，能兼容带 BOM 的文件，
启动时还会打印实际读到的键名。

**Q: 建库日志说「平均每页只有 N 个字符，文本层几乎为空」**

说明 PDF 是扫描件（图片），文字层是空的。直接建库只会得到极少、且高度重复的内容，
检索没有意义。需要先 OCR（ocrmypdf / PaddleOCR / 智谱 GLM-OCR）再建库。

**Q: 关键词明明在文档里，却搜不到**

检查是不是 Unicode 变体字问题（见上文第 1 节）。重新建库即可修复。

**Q: 检索时能用别的 embedding 吗**

**不能混用。** 检索用的 embedding 必须与建库时完全一致（同模型、同维度），
否则向量空间不同，结果无意义。换模型必须重建库。

---

## 后续可做

- **接生成环节**：把 `query_db.py --json` 的 Top-K 结果拼进 prompt，交给大模型组织答案
  （DeepSeek 可用在这里；它不能做 embedding）
- **接进主项目**：把检索封装成 Express 的一个接口（如 `POST /api/ask`）
- **Rerank**：智谱有 `Rerank` 模型（0.8 元/百万 tokens），可对 Top-K 重排以提升精度
