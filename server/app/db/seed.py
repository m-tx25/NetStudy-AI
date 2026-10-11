"""演示数据：与前端 client/src/api/mock.js 的种子数据保持一致。

这样把 VITE_USE_MOCK 改成 false 后，界面看到的仍是同一套内容，
便于「同一份数据在 mock 与真实后端之间无缝切换」的对照验证。

存储分工：
    文档元信息 → MySQL
    切片向量   → ChromaDB
其中「技术文档库」与「规章制度库」各有一份**真实落盘文件**（.md 与 .docx），
其余文档仅保留元信息（stored_path 为空），因此不可重新索引 —— 这是有意为之：
既保证界面数据完整，又演示了「有原始文件才能重建索引」的真实行为。

仅当演示账号不存在时才写入，可重复执行。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    Conversation,
    ConversationKnowledgeBase,
    Document,
    KnowledgeBase,
    Message,
    MessageSource,
    User,
)
from app.services import chunking, parser, vectorstore
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "123456"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_ago(hours: float) -> datetime:
    return _now() - timedelta(hours=hours)


# --------------------------------------------------------------------------
# 演示正文（与 mock.js 内容对应）
# --------------------------------------------------------------------------
_CONTENT: dict[str, str] = {
    "doc_prd": (
        "# 产品需求规格说明书 v2\n\n"
        "## 一、项目目标\n"
        "本系统面向企业内部的文档知识管理场景，目标是让员工用自然语言提问，"
        "系统从已上传的资料中检索依据并生成带引用的回答，降低查找文档的时间成本。\n\n"
        "## 二、功能范围\n"
        "1. 账号体系：注册、登录、资料维护、修改密码。\n"
        "2. 知识库管理：新建知识库、上传文档、启用或停用文档、重新向量化、删除文档。\n"
        "3. 智能问答：支持流式输出、多轮对话、按知识库范围检索、展示引用来源与相关度分数。\n\n"
        "## 三、非功能需求\n"
        "单个文件上传上限为 50MB；常见问答的首字延迟应控制在 2 秒以内；"
        "回答必须标注引用编号，资料不足时明确说明未找到依据，不允许编造内容。\n\n"
        "## 四、竞品分析结论\n"
        "同类产品普遍在引用可追溯性上做得不足，用户无法确认答案来自哪份文档的哪一段，"
        "因此本项目把「引用来源面板」列为一级功能。"
    ),
    "doc_roadmap": (
        "# 产品路线图 2025\n\n"
        "## 第一阶段（1-2 月）\n"
        "完成账号体系与知识库管理，打通文档上传到向量化的链路。\n\n"
        "## 第二阶段（3-4 月）\n"
        "上线流式问答与引用溯源，支持多轮对话记忆。\n\n"
        "## 第三阶段（5-6 月）\n"
        "引入重排序模型提升召回精度，支持跨知识库联合检索。\n\n"
        "## 第四阶段（7 月及以后）\n"
        "接入权限体系，按部门隔离知识库可见范围，并补充问答质量评估与埋点统计。"
    ),
    "doc_compete": (
        "# 竞品分析报告\n\n"
        "## 对比对象\n三类企业知识问答产品。\n\n"
        "## 共性做法\n"
        "都采用「检索增强生成」架构，即先向量检索出相关片段，再让大模型依据片段作答。\n\n"
        "## 差异点一：引用展示\n"
        "多数产品只给出文档名，不给出具体片段与相关度分数，用户难以判断答案可信度。\n\n"
        "## 差异点二：知识库范围控制\n"
        "部分产品只能在全局检索，无法在提问时限定范围。\n\n"
        "## 差异点三：失败兜底\n"
        "多数产品在检索不到内容时仍会强行生成，容易产生幻觉。\n\n"
        "## 结论\n"
        "本项目应在引用粒度、范围控制与失败兜底三方面建立差异。"
    ),
    "doc_arch": (
        "# 系统架构设计\n\n"
        "## 整体架构\n"
        "前后端分离：前端 Vue 3 + Vite，后端 Python + FastAPI，"
        "大模型通过 OpenAI 兼容接口调用；关系型数据存 MySQL，向量存 ChromaDB。\n\n"
        "## RAG 链路\n"
        "检索增强生成（RAG）链路由五个环节组成：文档解析、文本分块、向量化、向量检索、大模型生成。\n\n"
        "## 文档解析\n"
        "负责把 PDF、Word、Markdown、Excel、PPT 等格式转成纯文本，并尽量保留页码，"
        "以便回答时能定位到具体页。PDF 文本层常含 Unicode 变体字，"
        "需要做 NFKC 归一化，否则关键词检索会失配。\n\n"
        "## 文本分块\n"
        "采用递归字符切分，优先在段落和句号处断开，块大小默认 500 字，"
        "相邻块保留 50 字重叠，避免语义被硬切断。\n\n"
        "## 向量化与检索\n"
        "向量模型使用智谱 embedding-3（2048 维），向量库存入 ChromaDB。"
        "检索采用混合策略：0.5 乘向量相似度加 0.5 乘词面命中分数，"
        "术语与公式密集的手册类文档下比纯向量更稳定。\n\n"
        "## 异步任务\n"
        "文档上传后的解析与向量化耗时较长，放入 Celery 队列由独立 worker 处理，"
        "消息中间件使用 Redis，避免阻塞 Web 进程。"
    ),
    "doc_api": (
        "# API 接口文档\n\n"
        "## 鉴权\n"
        "除健康检查外，所有接口都需要在请求头携带 Authorization: Bearer 令牌。\n"
        "令牌为 JWT，包含用户标识与版本号；修改密码后版本号递增，此前签发的令牌立即失效。\n\n"
        "## 统一响应\n"
        "可直接返回数据对象，也可使用 code、message、data 信封；code 为 0 或 200 表示成功。\n\n"
        "## 流式问答\n"
        "POST /api/chat/stream 以 text/event-stream 返回增量内容，"
        "事件类型包含 meta、sources、delta、done、error；"
        "sources 事件先于正文推送，因此前端可以在答案生成前就展示引用来源。\n\n"
        "## 文档上传\n"
        "POST /api/documents/upload 使用 multipart/form-data，"
        "字段为 file 与 knowledgeBaseId；文件超过 50MB 时返回 413。\n\n"
        "## 错误码约定\n"
        "401 表示登录失效，前端会清除本地令牌并跳转登录页；"
        "403 表示无权限；404 表示资源或接口不存在；413 表示文件过大。"
    ),
    "doc_deploy": (
        "# 部署运维手册\n\n"
        "## 依赖服务\n"
        "Python 3.11 及以上、MySQL 8.0 及以上、Redis（用于 Celery 队列）。\n\n"
        "## 安装步骤\n"
        "创建虚拟环境，安装 requirements.txt；复制 .env.example 为 .env 并填写密钥。\n\n"
        "## 启动 Web 服务\n"
        "uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload\n\n"
        "## 启动异步 worker\n"
        "celery -A app.tasks.celery_app worker -l info\n"
        "若本地没有 Redis，可把 CELERY_TASK_ALWAYS_EAGER 设为 true，"
        "此时文档处理会在 Web 进程内同步执行，仅适合开发环境。\n\n"
        "## 数据存储\n"
        "关系型数据在 MySQL 的 chuangzhibei 库；向量数据在 server/data/chroma_db；"
        "上传的原始文件在 server/data/uploads。\n\n"
        "## 故障排查\n"
        "健康检查接口 /api/health 会返回大模型是否已配置、向量库与向量模型模式、"
        "MySQL 连接目标、以及任务队列是否可用，可据此快速定位配置问题。"
    ),
    "doc_staff": (
        "# 员工手册 2025\n\n"
        "## 工作时间\n"
        "标准工作制为每日 8 小时，核心工作时段为 10:00 至 16:00，其余时间可弹性安排。\n\n"
        "## 请假制度\n"
        "事假需提前 1 个工作日申请；病假需提供医疗机构证明；"
        "年假按工龄计算，入职满一年起享受 5 天，此后每满一年增加 1 天，上限 15 天。\n\n"
        "## 考勤\n"
        "每月累计迟到超过 3 次将计入绩效记录。\n\n"
        "## 保密要求\n"
        "员工不得将内部文档上传至外部公共网盘或第三方大模型服务，违反者按公司保密制度处理。"
    ),
    "doc_reimburse": (
        "# 报销流程说明\n\n"
        "## 标准流程\n"
        "标准流程分为四步。第一步提交票据，由申请人在费用发生后 15 日内提交，"
        "逾期需部门主管书面说明。第二步直属主管审批，时限 2 个工作日。"
        "第三步财务复核，时限 3 个工作日。第四步打款，财务出纳在每月 15 日与 30 日统一打款。\n\n"
        "## 注意事项\n"
        "单张发票金额超过 5000 元时，需额外附上采购申请单编号。\n\n"
        "## 差旅报销\n"
        "差旅报销需提供行程单与住宿发票，市内交通费按实际发生额报销，"
        "餐补标准为每人每日 100 元。\n\n"
        "## 特殊约定\n"
        "蓝色鲸鱼协议的内部编号是 CZ-2025，仅用于系统联调测试。"
    ),
}

_DOCUMENTS: list[dict] = [
    {"id": "doc_prd", "name": "需求规格说明书_v2.md", "size": 4_512_000, "hours": 30,
     "kb": "kb_product", "suffix": ".md"},
    {"id": "doc_roadmap", "name": "产品路线图2025.md", "size": 86_000, "hours": 52,
     "kb": "kb_product", "suffix": ".md"},
    {"id": "doc_compete", "name": "竞品分析报告.md", "size": 2_140_000, "hours": 100,
     "kb": "kb_product", "suffix": ".md"},
    {"id": "doc_arch", "name": "系统架构设计.docx", "size": 3_260_000, "hours": 12,
     "kb": "kb_tech", "suffix": ".docx", "write_docx": True},
    {"id": "doc_api", "name": "API接口文档.md", "size": 154_000, "hours": 6,
     "kb": "kb_tech", "suffix": ".md"},
    {"id": "doc_deploy", "name": "部署运维手册.md", "size": 6_880_000, "hours": 48,
     "kb": "kb_tech", "suffix": ".md"},
    {"id": "doc_staff", "name": "员工手册2025.md", "size": 5_120_000, "hours": 70,
     "kb": "kb_hr", "suffix": ".md"},
    {"id": "doc_reimburse", "name": "报销流程说明.word.docx", "size": 512_000, "hours": 5,
     "kb": "kb_hr", "suffix": ".docx", "write_docx": True},
]

_KNOWLEDGE_BASES = [
    {"id": "kb_product", "name": "产品需求文档库",
     "description": "需求规格、产品路线图、竞品分析等产品侧资料",
     "hours_created": 288, "hours_updated": 48},
    {"id": "kb_tech", "name": "技术文档库",
     "description": "系统架构、接口文档、部署运维手册",
     "hours_created": 480, "hours_updated": 24},
    {"id": "kb_hr", "name": "规章制度库",
     "description": "员工手册、报销与审批流程",
     "hours_created": 120, "hours_updated": 6},
]


def _uploads_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_demo_file(document_id: str, name: str, content: str, write_docx: bool) -> Path:
    """把演示正文落盘为真实文件，使文档可被重新索引。"""
    target = _uploads_dir() / f"{document_id}{Path(name).suffix}"

    if write_docx:
        try:
            import docx

            document = docx.Document()
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    level = len(stripped) - len(stripped.lstrip("#"))
                    document.add_heading(stripped.lstrip("# ").strip(), level=min(level, 4))
                else:
                    document.add_paragraph(stripped)
            document.save(str(target))
            return target
        except ImportError:
            logger.warning("未安装 python-docx，%s 改用 .md 落盘", document_id)
            target = target.with_suffix(".md")

    target.write_text(content, encoding="utf-8")
    return target


async def seed_demo_data() -> None:
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.username == DEMO_USERNAME))
        ).scalar_one_or_none()
        if existing is not None:
            return

        logger.info("初始化演示数据（账号 %s / %s）", DEMO_USERNAME, DEMO_PASSWORD)

        now = _now()
        user = User(
            id="user_demo",
            username=DEMO_USERNAME,
            nickname="演示用户",
            email="demo@example.com",
            avatar="",
            role="user",
            password_hash=hash_password(DEMO_PASSWORD),
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()

        for spec in _KNOWLEDGE_BASES:
            db.add(
                KnowledgeBase(
                    id=spec["id"],
                    owner_id=user.id,
                    name=spec["name"],
                    description=spec["description"],
                    embedding_model=settings.ZHIPUAI_EMBEDDING_MODEL,
                    created_at=_hours_ago(spec["hours_created"]),
                    updated_at=_hours_ago(spec["hours_updated"]),
                )
            )
        await db.flush()

        kb_names = {spec["id"]: spec["name"] for spec in _KNOWLEDGE_BASES}

        # ---------- 文档：元信息进 MySQL，切片进 Chroma ----------
        for spec in _DOCUMENTS:
            content = _CONTENT[spec["id"]]
            stored_path = _write_demo_file(
                spec["id"], spec["name"], content, bool(spec.get("write_docx"))
            )

            document = Document(
                id=spec["id"],
                knowledge_base_id=spec["kb"],
                name=spec["name"],
                stored_path=str(stored_path),
                size=spec["size"],
                chunks=0,
                status="processing",
                enabled=True,
                uploaded_at=_hours_ago(spec["hours"]),
                updated_at=_hours_ago(spec["hours"]),
            )
            db.add(document)
            await db.flush()

            # 走与上传完全相同的解析 → 切片 → 向量化链路
            try:
                documents = parser.parse_document(stored_path)
                chunks = chunking.split_documents(documents)
                payload = []
                for ordinal, chunk in enumerate(chunks):
                    metadata = chunk.metadata or {}
                    page = metadata.get("page_label") or metadata.get("page")
                    payload.append(
                        (
                            ordinal,
                            chunk.page_content or "",
                            int(page) if isinstance(page, (int, float)) and page else None,
                        )
                    )
                stored = vectorstore.add_chunks(
                    owner_id=user.id,
                    knowledge_base_id=spec["kb"],
                    knowledge_base_name=kb_names[spec["kb"]],
                    document_id=document.id,
                    document_name=document.name,
                    chunks=payload,
                )
                document.chunks = stored
                document.status = "ready"
                document.error = ""
            except Exception as exc:
                document.status = "failed"
                document.error = str(exc)[:500]
                logger.warning("演示文档 %s 向量化失败：%s", spec["id"], exc)

        await db.flush()

        # ---------- 会话与消息 ----------
        conversation = Conversation(
            id="conv_demo",
            owner_id=user.id,
            title="RAG 检索流程是怎样的",
            created_at=_hours_ago(3),
            updated_at=_hours_ago(3),
        )
        db.add(conversation)
        db.add(
            ConversationKnowledgeBase(
                conversation_id=conversation.id, knowledge_base_id="kb_tech"
            )
        )
        db.add(
            Message(
                id=new_id("msg"),
                conversation_id=conversation.id,
                role="user",
                content="RAG 的检索流程是怎样的？",
                created_at=_hours_ago(3),
            )
        )

        # 用真实检索跑一遍，让演示回答里的引用与库内切片一致
        hits = vectorstore.search(
            db,
            "RAG 的检索流程是怎样的？",
            owner_id=user.id,
            knowledge_base_ids=["kb_tech"],
            top_k=2,
        )

        answer = (
            "RAG（Retrieval-Augmented Generation）的核心是**先检索、再生成**，"
            "整体分为离线索引与在线问答两个阶段。\n\n"
            "### 一、离线索引阶段\n"
            "1. **文档解析**：把 PDF / Word / Markdown 等转成纯文本，并保留页码；"
            "PDF 需做 NFKC 归一化修正变体字。\n"
            "2. **分块（Chunking）**：按 500 字滑窗切分，相邻块保留 50 字重叠。\n"
            "3. **向量化**：用智谱 embedding-3 把每个块编码成 2048 维向量。\n"
            "4. **入库**：向量与元数据写入 ChromaDB。\n\n"
            "### 二、在线问答阶段\n"
            "1. 用同一个向量模型编码用户问题；\n"
            "2. 在 ChromaDB 中召回候选（默认取 Top-K，K=5）；\n"
            "3. 按 0.5×向量相似度 + 0.5×词面命中重排，过滤弱相关结果；\n"
            "4. 把命中片段作为「参考资料」注入 Prompt，并约束模型只依据资料作答；\n"
            "5. 大模型逐 token 生成，服务端通过 SSE 推给前端，形成打字机效果。\n\n"
            "> 关键点：资料里没有的内容，应明确回答「知识库中未找到相关依据」，而不是编造。"
        )

        assistant = Message(
            id=new_id("msg"),
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            status="done",
            created_at=_hours_ago(3),
        )
        db.add(assistant)
        await db.flush()

        for index, hit in enumerate(hits):
            db.add(
                MessageSource(
                    id=new_id("src"),
                    message_id=assistant.id,
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    document_name=hit.document_name,
                    knowledge_base_id=hit.knowledge_base_id,
                    knowledge_base_name=hit.knowledge_base_name,
                    score=hit.score,
                    page=hit.page,
                    snippet=hit.snippet(),
                    ordinal=index,
                )
            )

        await db.commit()

        total_documents = (
            await db.execute(select(func.count(Document.id)))
        ).scalar_one()
        total_chunks = vectorstore.count_chunks(owner_id=user.id)
        logger.info(
            "演示数据初始化完成：3 个知识库、%s 份文档、%s 个切片（向量模式 %s）",
            total_documents,
            total_chunks,
            vectorstore.embeddings.current_mode(),
        )
