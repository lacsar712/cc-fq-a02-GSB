# FASTQ 质控流水线台（FASTQ QC Pipeline Console）

从零实现的全栈演示：上传/选择小型 FASTQ → **Actor 队列流水线**质控 → 查看阶段状态与指标。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL |
| 流水线 | `ParseActor` → `QualityHistActor` → `NContentActor` → `ReportActor`（asyncio.Queue） |
| 前端 | Vue 3 · Vite · Quasar · 中文 UI · nginx `/api` 反代 |
| 基建 | docker compose（db / backend / seed / frontend） |

## 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3184 |
| Backend API | http://localhost:8184 |
| PostgreSQL | localhost:54384 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| `bioops` | `fastq123456` | 可提交质控作业 |
| `auditor` | `audit123456` | 只读结果，不可提交 |

## 一键启动

```bash
cd projects/09-fastq-qc-pipeline
docker compose up --build
```

镜像源：Postgres/Node/Nginx 使用 `docker.m.daocloud.io`；npm 使用 `registry.npmmirror.com`；pip 使用清华源。

启动后 seed 会写入：

- `demo-good-r1`：合格样例（可算出 `mean_quality` / `n_rate`）
- `demo-broken-malformed`：损坏样例（`ParseActor` 失败，后续阶段 skipped）

## Verification（验收）

1. 打开 http://localhost:3184 ，用 `bioops` / `fastq123456` 登录。
2. **样例库** 看到 2 条样例 → 选合格样例 **提交质控作业**。
3. 作业详情页看到四个 Actor 阶段均为成功，指标卡出现 `reads` / `mean_quality` / `n_rate`。
4. 再跑损坏样例：`ParseActor` = failed，其余 = skipped。
5. 退出，用 `auditor` / `audit123456` 登录：可看历史与详情，提交作业接口返回 403 / 前端无提交入口。
6. 健康检查：`curl http://localhost:8184/api/health`

## 质量门禁（Quality Gate）

质控成功的作业按门禁阈值判定，超标作业进入**质量门禁**页的专用列表（失败作业不进列表）。

- 阈值：平均质量下限 `min_mean_quality`（默认 30）、N 率上限 `max_n_rate`（默认 0.05），保存在 `quality_gates` 表单例行。
- 仅 `bioops` 可改阈值（`PUT`，记录更新人）；`auditor` 只读超标列表。
- 阈值保存后立即生效，只判定**之后完成**的作业；历史作业需重跑才会按新阈值进入列表。
- 列表按作业聚合，行内写清每个超标字段（如「平均质量(mean_quality) 低于下限：实际 39.938 < 阈值 40」）。

### 验收口令复现步骤

1. `bioops` 登录，用合格样例 `demo-good-r1`（mean_quality≈39.94，n_rate≈0.021）提交作业 → 默认阈值下通过，不在门禁列表。
2. 打开 **质量门禁**，把平均质量下限抬高到 `40` 并保存。
3. 用同一样例**重跑**一次 → 新作业成功但触发门禁，门禁列表出现该条，行内显示「平均质量 低于下限：实际 39.938 < 阈值 40」。

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
- `GET  /api/jobs`
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`
- `GET  /api/quality-gate`（登录可读）
- `PUT  /api/quality-gate` `{ "min_mean_quality": 40, "max_n_rate": 0.05 }`（仅 bioops）
- `GET  /api/quality-gate/violations`（登录可读，触发门禁的成功作业）

## 本地单测（可选）

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

覆盖：畸形 FASTQ 在 `ParseActor` 失败；正常样例产出 `mean_quality`。

## 目录结构

```
09-fastq-qc-pipeline/
  PRD.md
  README.md
  docker-compose.yml
  backend/
    Dockerfile
    seed.py
    data/{good,broken}.fastq
    app/
      main.py api.py auth.py models.py schemas.py quality_gate.py
      pipeline/{actors,runner}.py
    tests/{conftest,test_actors,test_quality_gate}.py
  frontend/
    Dockerfile nginx.conf
    src/pages/{Login,Samples,JobSubmit,JobDetail,JobHistory,QualityGate}Page.vue
```
