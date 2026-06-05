# HVAC Product Manual PDF Search — 项目文档

## 项目概述

从 Excel 需求表（482行 AHRI 认证数据，6个品牌）批量搜索并下载对应的产品手册/技术指南 PDF。

## 核心方法

```
厂商产品 Sitemap → 匹配 model token → 产品页 HTML → 提取 DocumentURL → CDN 下载 PDF → 验证
```

**关键认知**：PDF 托管在厂商 CDN（如 `files.myrheem.com`），搜索引擎不索引这些路径。必须通过产品 sitemap 发现。

## 已知 CDN/文档源

| 域名 | 品牌 | 状态 |
|------|------|------|
| `files.myrheem.com/webpartners/ProductDocuments/` | Rheem / Ruud | ✅ |
| `files.hvacnavigator.com/p/` | 多品牌 | 待验证 |
| `carriercca.com/pdf/products_pdf/` | Carrier | ✅ |
| `lennox.com/dA/` | Lennox | ✅ |
| `docs.johnsoncontrols.com/ductedsystems/api/khub/documents/{id}/content` | JCI Applied | ✅ JCI Unitary 需认证 |

## 文件位置

- Excel: `E:\HVAC_PDF_search\Unitary_pdf_manual_search_0519_lite.xlsx`
- GPT 5.5 Workflow: `E:\HVAC_PDF_search\PDF_manual_search_workflow_prompt.md`
- Pilot Results: `E:\HVAC_PDF_search\_handoff_extracted\pilot_first5_results_SANITIZED.csv`
- PDF 存储: `./pdf_downloads/`
- 框架: `framework.py`, `validate_pdf.py`

## 品牌分布

| 品牌 | 行数 | 约唯一手册数 |
|------|------|-------------|
| JOHNSON CONTROLS | 196 | 71 |
| BOSCH | 80 | 27 |
| RUUD | 58 | 21 |
| RHEEM / York | 57 | 21 |
| LENNOX / BRYANT | 54 | 14 |
| CARRIER | 37 | 34 |

## PDF 命名规则

`{OriginalPdfStem}__Ref{ReferenceId}_{Brand}_{ModelKey}_{Refrigerant}.pdf`

## 验证规则

| 置信度 | 条件 |
|--------|------|
| High confidence | brand + model + refrigerant + ≥1 performance field |
| Needs human confirmation | model/brand matched, performance incomplete |
| Low confidence | only brand or series |
| Not found | no PDF found |
