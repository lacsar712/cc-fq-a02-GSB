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
| `bioops` | `fastq123456` | 可提交质控作业、修改质量门禁阈值 |
| `auditor` | `audit123456` | 只读结果与门禁超标列表，不可提交/改阈值 |

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
5. 退出，用 `auditor` / `audit123456` 登录：可看历史、详情与**质量门禁/超标列表**，提交作业与修改阈值接口返回 403 / 前端无入口。
6. **质量门禁验收**：导航进入「质量门禁」，把平均质量下限抬高到高于样例实际均值（如 45），保存后重跑合格样例 → 门禁「超标作业列表」出现该条，行内写明「平均质量分 39.938 低于下限 45」；失败的损坏样例不会进入列表。
7. 健康检查：`curl http://localhost:8184/api/health`

## 质量门禁策略子系统

- 阈值（**平均质量下限** `mean_quality_min`、**N 率上限** `n_rate_max`）持久化在 `quality_gate_settings`，默认 20 / 0.10；每次修改写入 `quality_gate_changes` 审计表（变更人、时间、新旧值）。
- 门禁在流水线成功后评估，作业留存判定结论与当时阈值快照（`jobs.gate_passed / gate_violations / gate_thresholds`），阈值只对之后重跑的作业生效。
- **超标列表只收录流水线成功但触发门禁的作业**；失败/排队作业门禁字段为 NULL，不会出现。
- 运维（bioops）可改阈值，审计员（auditor）只读阈值与列表。导航栏「质量门禁」为独立入口页，不做全站监控墙。

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
- `GET  /api/jobs`
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`
- `GET  /api/gate/settings`（登录可读）
- `PUT  /api/gate/settings` `{ "mean_quality_min": 0, "n_rate_max": 0 }`（仅 bioops，变更落审计）
- `GET  /api/gate/violations`（仅成功且触发门禁的作业）

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
      main.py api.py auth.py models.py schemas.py gate.py
      pipeline/{actors,runner}.py
    tests/{test_actors,test_gate,test_gate_api}.py
  frontend/
    Dockerfile nginx.conf
    src/pages/{Login,Samples,JobSubmit,JobDetail,JobHistory,Gate}Page.vue
```
