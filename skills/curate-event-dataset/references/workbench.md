# FinMycelium 接口与验收

本说明依据 EPG-dataset 的 `event-epg/workbench-import.md` 和主表规范整理。每个入口依赖目标 checkout 的实现，用 [预检脚本](runbook.md)与实际运行验证。

| 入口 | 交付要求 |
| --- | --- |
| Workbench CSV 上传 | 默认投影 19 个业务字段。`status`、`epg_path`、`gantt_path`、`review_path`、`duplicate_status` 留在目录。上传完整表时在映射里跳过这些列。 |
| 数据集页面直接读取 | 使用 `finmy/dataset.py` 的 `DatasetCatalog`。它可能仍要求 `event_name` 和 `period` 等旧字段或有文件字节上限。结构检查或上传成功不能说明此入口可用。 |
| Builder | 需经确认的范围和已获取并审核的来源正文材料。ID 对应 `user_query.user_query_id`，范围形成 `query_text`，`keywords` 对应 `key_words`，证据正文形成 `samples`。 |

## 导出

在运行手册中的 PowerShell 变量设置完成后运行。

```powershell
python -X utf8 -B "$Skill/scripts/workbench_export.py" --source "$Run/stage/events.csv" --output "$Run/workbench-import" --chunk-size 2500 --finmy-root $Finmy
```

导出器使用目标版本的 `read_table` 和 `event_record` 对每份文件真实解析回环，再写 manifest，记录源文件哈希、各分片 ID、行数、字节和哈希。超出字节或行数限制时调小 `--chunk-size`，重新验证。现行 13,000 条曾验证为 5 份各 2,500 行与 1 份 500 行，以实际生成结果为准。

已有工作台任务时加 `--baseline <真实前版 events.csv>` 获得新增、同 ID 修改和撤回的审阅数据。既有同 ID 任务不会被批量上传覆盖。允许撤回的导出参数只生成审阅表，实际工作台不执行删除。超过单一新增文件上限时使用按真实基线拆分的批次。空工作台可导入完整分片。

导出仅交付文件。已支持的结论与流程状态保留原审计；新的任务仍需确认范围、检索、审核证据及审图。来源 URL 只作检索线索。公开数据库内容可在许可范围内按定位保存必要引用，不需要把所有网页全文置入目录。
