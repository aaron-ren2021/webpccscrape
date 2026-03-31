---
description: "Use when modifying core pipeline logic, filters, dedup, AI classification, or data models."
applyTo: "core/**/*.py"
---

# 核心邏輯規範

- 所有資料結構使用 `dataclass(slots=True)`
- 過濾函式保持純函式設計，輸入 `Iterable[BidRecord]` 輸出 `list[BidRecord]`
- AI 分類為可選功能，`ENABLE_AI_CLASSIFICATION=false` 時完全跳過
- 去重邏輯分 exact / approx 兩階段
- UID 由 `build_bid_uid()` 產生（基於 title + org + date + amount 的 hash）
- `Settings.from_env()` 是所有設定的唯一來源
