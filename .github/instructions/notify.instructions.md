---
description: "Use when modifying notification logic, email sending, GitHub Issue creation, or adding new notification channels."
applyTo: "notify/**/*.py"
---

# 通知層規範

- 通知優先順序：ACS Email → SMTP → GitHub Issue
- `send_email()` 在 `dispatcher.py` 中統一調度
- `dry_run=true` 時不實際寄信
- GitHub Issue 僅針對 `ai_priority == "high"` 的標案建立
- 敏感資訊（token, password）不得寫入 log
- 所有通知失敗都應 log 但不中止整體流程
