# 砚台 · AI 辅助财务学习平台

面向个人 CPA、税务师备考的学习工作台。它不是一个随便开口的聊天壳子：AI 只能依据用户上传且解析成功的资料回答，每条关键结论都必须回到页码或段落原文。

## 已实现能力

- CPA、税务师两套可编辑课程树，支持科目、章节、知识点和掌握状态。
- PDF、DOCX、TXT、Markdown 解析，保留页码、标题和段落定位。
- 上传后自动识别 PDF 书签/字体标题、DOCX Heading、Markdown 层级和 TXT 编号，生成课程目录草稿。
- 目录草稿支持改名、拖动排序、新增、忽略、相似节点预合并和原文核对；确认后才写入正式课程。
- 本地确定性向量检索与词项重排，不依赖额外嵌入服务。
- DeepSeek 普通精讲与苏格拉底模式，服务端验证引用白名单。
- DeepSeek 可在严格来源约束下规范目录并补知识点；没有 Key 或调用失败时保留机械抽取结果。
- 证据不足严格拒答，引用可打开原文抽屉并定位。
- 会话存档、Markdown 笔记、学习现场、薄弱项和间隔复习。
- DeepSeek Key 服务端认证加密保存，前端永不读取明文。
- 桌面、平板和基础手机响应式界面。

## 一键启动

1. 生成服务端主密钥：

   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. 复制环境变量并填写 `APP_ENCRYPTION_KEY`：

   ```bash
   cp .env.example .env
   ```

3. 启动全部服务：

   ```bash
   docker compose up --build
   ```

4. 打开 `http://localhost:3000`，进入“系统设置”保存并验证 DeepSeek API Key。

API 文档位于 `http://localhost:8000/docs`。

> 如果更换 `APP_ENCRYPTION_KEY`，已有 DeepSeek Key 将无法解密，需要在设置页重新保存。生产环境禁止使用默认开发密钥。

## 本地开发

前端：

```bash
cd frontend
npm install
npm run dev
```

后端默认可使用 SQLite 进行本地开发：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端默认访问 `http://localhost:8000`。需要覆盖时设置 `NEXT_PUBLIC_API_URL`。

## 测试

```bash
cd backend && pytest
cd frontend && npm run build
```

测试覆盖文档页码/段落定位、检索相关性和复习调度。DeepSeek 联调需要用户自己的 Key，不会在测试中访问真实 API。

## 数据与安全边界

- 上传文件仅存放在后端 `STORAGE_DIR`，Docker 部署使用持久卷。
- API Key 经过服务端主密钥加密后写入数据库，接口只返回配置状态。
- 问答上下文只包含检索到的资料片段；模型返回的引用必须属于本次检索结果。
- 扫描 PDF 不做 OCR，会明确标记解析失败。
- 单机单用户版本没有账号隔离，不要直接暴露到不可信公网。

## 项目结构

```text
frontend/  Next.js 学习工作台
backend/   FastAPI、文档解析、检索、DeepSeek 和学习状态
docker-compose.yml  PostgreSQL/pgvector、API 与 Web 编排
```
