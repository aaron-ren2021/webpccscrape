#!/bin/bash
# Phase 1 Issue Update Script
# 用途：將 Phase 1 報告更新到 GitHub Issue #3 並關閉該 Issue

set -e

REPO="aaron-ren2021/webpccscrape"
ISSUE_NUMBER=3
COMMENT_FILE="/tmp/phase1_issue_comment.md"

echo "=========================================="
echo "Phase 1 Issue Update Script"
echo "=========================================="
echo ""

# 檢查 gh CLI 是否已安裝
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) 未安裝"
    echo "請執行: sudo apt install gh"
    exit 1
fi

# 檢查是否已登入
if ! gh auth status &> /dev/null; then
    echo "⚠️  GitHub CLI 尚未登入"
    echo "請執行以下命令登入："
    echo "  gh auth login"
    echo ""
    read -p "是否現在登入? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gh auth login
    else
        echo "❌ 取消操作"
        exit 1
    fi
fi

echo "✅ GitHub CLI 已認證"
echo ""

# 檢查評論檔案是否存在
if [ ! -f "$COMMENT_FILE" ]; then
    echo "❌ 評論檔案不存在: $COMMENT_FILE"
    exit 1
fi

echo "📝 準備更新 Issue #$ISSUE_NUMBER..."
echo ""

# 添加評論到 Issue
echo "1️⃣ 添加 Phase 1 報告摘要到 Issue..."
if gh issue comment "$ISSUE_NUMBER" --repo "$REPO" --body-file "$COMMENT_FILE"; then
    echo "✅ 評論已成功添加"
else
    echo "❌ 添加評論失敗"
    exit 1
fi

echo ""

# 詢問是否關閉 Issue
read -p "2️⃣ 是否關閉 Issue #$ISSUE_NUMBER? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if gh issue close "$ISSUE_NUMBER" --repo "$REPO" --comment "Phase 1 現況盤點已完成，報告已產出並審閱通過。進入 Phase 2：架構設計與成本估算。"; then
        echo "✅ Issue #$ISSUE_NUMBER 已關閉"
    else
        echo "❌ 關閉 Issue 失敗"
        exit 1
    fi
else
    echo "⚠️  Issue #$ISSUE_NUMBER 保持開啟狀態"
fi

echo ""
echo "=========================================="
echo "✅ 操作完成！"
echo "=========================================="
echo ""
echo "📌 後續步驟："
echo "  1. 前往 GitHub 確認 Issue #$ISSUE_NUMBER 狀態"
echo "  2. 查看完整報告: docs/PHASE1_AUDIT_REPORT.md"
echo "  3. 準備執行 Phase 2：架構設計與成本估算"
echo ""
