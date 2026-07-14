# 安装依赖说明

本文说明运行或开发“砚台 · AI 辅助财务学习平台”前需要安装的工具。普通用户和开发者不需要安装同一套东西，请按自己的使用方式选择。

## 方式一：使用 Docker 运行（推荐）

这是依赖最少、最稳定的方式。Node.js、Python、PostgreSQL 和 pgvector 均由 Docker 容器提供，不需要在电脑上单独安装。

### 必须安装

| 工具 | 建议版本 | 用途 |
| --- | --- | --- |
| Git | 2.40 或更高 | 克隆和更新源码 |
| Docker Engine | 24 或更高 | 运行前端、API 和数据库容器 |
| Docker Compose | v2.20 或更高 | 编排三个服务；命令格式为 `docker compose` |

macOS 可以二选一：

- Docker Desktop：安装后启动 Docker Desktop。
- Colima + Docker CLI：安装后先执行 `colima start`。

不要同时混用两个 Docker context。出现“failed to connect to the docker API”时，先检查：

```bash
docker context show
docker info
```

如果当前 context 是 `colima`：

```bash
colima start
```

### 首次启动

```bash
git clone https://github.com/dadjuba542-ai/CAIWU.git
cd CAIWU
cp .env.example .env
docker compose up --build -d
```

启动完成后访问：

- 网页：<http://localhost:3000>
- API 文档：<http://localhost:8000/docs>

验证服务：

```bash
docker compose ps
curl http://localhost:8000/api/health
```

健康接口应返回：

```json
{"status":"ok","service":"ledger-study"}
```

### 环境变量

复制 `.env.example` 后，必须为正式使用生成独立的 `APP_ENCRYPTION_KEY`。不要使用示例值，也不要提交 `.env`。

如果本机已有 Python 和 `cryptography`：

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

如果没有 Python，可以使用 OpenSSL 生成随机值：

```bash
openssl rand -base64 32
```

将结果写入 `.env`：

```dotenv
APP_ENCRYPTION_KEY=替换为生成的随机值
```

更换此密钥后，数据库中已经保存的 DeepSeek Key 将无法解密，需要在系统设置中重新填写。

## 方式二：本地源码开发

只有需要修改源码、运行测试或调试服务时，才需要安装下面的开发环境。

### 必须安装

| 工具 | 项目验证版本 | 最低建议版本 |
| --- | --- | --- |
| Node.js | 22.x | 22 |
| npm | 10.x | 10 |
| Python | 3.11.x | 3.11 |
| pip | Python 3.11 配套版本 | 23 |

前端依赖由 `frontend/package-lock.json` 锁定，安装时优先使用：

```bash
cd frontend
npm ci
npm run dev
```

后端依赖由 `backend/requirements.txt` 锁定：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认本地开发使用 SQLite，不需要安装 PostgreSQL。只有脱离 Docker、并希望使用生产数据库结构时，才需要额外安装 PostgreSQL 16 和 pgvector。

### 主要项目依赖

前端核心：

- Next.js 15
- React 19
- TypeScript 5.8
- Lucide React

后端核心：

- FastAPI、Uvicorn
- SQLAlchemy、psycopg、pgvector
- PyMuPDF：解析 PDF
- python-docx：解析 DOCX
- cryptography：加密保存 DeepSeek Key
- httpx：调用 DeepSeek API
- pytest：后端测试

不要全局安装这些 npm 或 Python 包；必须安装在项目目录或 Python 虚拟环境中。

## DeepSeek 配置

DeepSeek API Key 不是项目启动依赖：

- 没有 Key：课程树、文件上传、资料解析、规则拆章、笔记和复习功能仍可使用。
- 配置 Key：启用严格引用 AI 问答、苏格拉底学习和目录知识点增强。

启动项目后，在“系统设置”页面填写 Key。Key 会在后端加密保存，不要写入源码、`.env.example` 或 Git 仓库。

## 可选测试依赖

端到端 UI 测试使用 Python Playwright。普通运行不需要安装。

```bash
pip install playwright
python3 -m playwright install chromium
```

项目基础验证：

```bash
cd backend
pytest -q

cd ../frontend
npm run build
```

## 常见问题

### Docker socket 不存在

```text
failed to connect to the docker API
```

Docker Desktop 用户需要启动 Docker Desktop；Colima 用户执行：

```bash
colima start
```

### 端口被占用

项目默认使用 `3000` 和 `8000`。检查占用：

```bash
lsof -i :3000
lsof -i :8000
```

### 扫描 PDF 无法解析

首版不包含 OCR。请使用文字可选择、可搜索的 PDF，或先用其他工具完成 OCR。

### 安装依赖后仍无法启动

依次执行：

```bash
docker compose config
docker compose ps
docker compose logs --tail 100 api
docker compose logs --tail 100 web
```

不要删除数据库卷来“试试看”，否则会丢失笔记、学习进度和上传资料索引。
