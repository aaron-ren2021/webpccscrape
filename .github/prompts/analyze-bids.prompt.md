---
description: "Analyze today's bid results and generate a prioritized recommendation report."
agent: "Bid Analyst"
tools: [read, search]
---

分析今日標案抓取結果，產生優先度排序的分析報告：

1. 讀取 `./output/preview.html` 中的標案資料
2. 對每筆標案進行評估：
   - 金額規模
   - 機關類型與歷史
   - 技術要求匹配度
   - 競爭態勢預估
3. 按照投標價值排序
4. 產出 Markdown 格式的分析報告
