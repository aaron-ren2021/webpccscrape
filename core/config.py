from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(slots=True)
class Settings:
    timezone: str = "Asia/Taipei"
    user_agent: str = "Mozilla/5.0 (compatible; bid-monitor/1.0)"
    request_timeout_seconds: int = 20
    request_retry_total: int = 3
    request_backoff_factor: float = 0.8

    request_delay_min: float = 2.0
    request_delay_max: float = 5.0

    enable_playwright: bool = True  # 🔥 預設啟用 Playwright+Stealth
    playwright_timeout_ms: int = 20000

    # --- Stealth / anti-detection ---
    stealth_enabled: bool = True
    stealth_human_behavior: bool = True
    stealth_session_persistence: bool = True
    stealth_session_ttl_hours: float = 24.0
    stealth_session_dir: str = ""
    stealth_artifact_dir: str = ""
    stealth_max_retries: int = 2
    stealth_headless: bool = True
    stealth_throttle_delay_min: float = 2.0
    stealth_throttle_delay_max: float = 6.0
    stealth_throttle_cooldown_after: int = 5
    stealth_throttle_cooldown_min: float = 8.0
    stealth_throttle_cooldown_max: float = 15.0
    stealth_throttle_backoff_base: float = 5.0

    # --- Proxy ---
    proxy_enabled: bool = False
    proxy_list: list[str] = field(default_factory=list)
    proxy_strategy: str = "round_robin"

    recent_days: int = 1
    high_amount_threshold: float = 5_000_000.0

    taiwanbuying_url: str = "https://www.taiwanbuying.com.tw/"
    taiwanbuying_method: str = "GET"
    taiwanbuying_params: dict[str, Any] = field(default_factory=dict)
    taiwanbuying_row_selectors: list[str] = field(default_factory=lambda: ["table tbody tr", ".result-item", ".list-group-item"])
    taiwanbuying_title_selectors: list[str] = field(default_factory=lambda: ["a", ".title", ".subject", "td:nth-child(2)"])
    taiwanbuying_org_selectors: list[str] = field(default_factory=lambda: [".org", ".unit", "td:nth-child(3)"])
    taiwanbuying_date_selectors: list[str] = field(default_factory=lambda: [".date", ".publish-date", "time", "td:nth-child(1)"])
    taiwanbuying_amount_selectors: list[str] = field(default_factory=lambda: [".amount", ".price", "td:nth-child(5)"])
    taiwanbuying_summary_selectors: list[str] = field(default_factory=lambda: [".summary", ".desc", "td:nth-child(4)"])
    taiwanbuying_link_selectors: list[str] = field(default_factory=lambda: ["a"])

    gov_url: str = "https://web.pcc.gov.tw/pis/"
    gov_method: str = "GET"
    gov_params: dict[str, Any] = field(default_factory=dict)
    gov_row_selectors: list[str] = field(default_factory=lambda: ["table tbody tr", ".result-item", ".list-group-item"])
    gov_title_selectors: list[str] = field(default_factory=lambda: ["a", ".title", ".subject", "td:nth-child(2)"])
    gov_org_selectors: list[str] = field(default_factory=lambda: [".org", ".unit", "td:nth-child(3)"])
    gov_date_selectors: list[str] = field(default_factory=lambda: [".date", ".publish-date", "time", "td:nth-child(1)"])
    gov_amount_selectors: list[str] = field(default_factory=lambda: [".amount", ".price", "td:nth-child(5)"])
    gov_summary_selectors: list[str] = field(default_factory=lambda: [".summary", ".desc", "td:nth-child(4)"])
    gov_link_selectors: list[str] = field(default_factory=lambda: ["a"])
    gov_detail_delay_seconds: float = 2.0
    gov_detail_max_per_identity: int = 3  # 🔥 Max requests per identity for detail pages

    g0v_api_url: str = "https://pcc-api.openfun.app/api/listbydate"
    g0v_enabled: bool = True
    api_only_mode: bool = False

    azure_storage_connection_string: str = ""
    azure_table_name: str = "BidNotifyState"
    azure_blob_container: str = "bid-state"
    azure_blob_name: str = "notified_state.json"

    email_to: list[str] = field(default_factory=list)
    email_subject_prefix: str = "[教育資訊標案監控]"

    acs_connection_string: str = ""
    acs_email_sender: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    dry_run: bool = False
    preview_html_path: str = ""

    # --- AI classification ---
    enable_ai_classification: bool = False
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ai_model: str = ""  # e.g. "gpt-4o-mini" or "claude-sonnet-4-20250514"
    
    # --- Local LLM (Ollama) ---
    ollama_base_url: str = ""  # e.g. "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b"  # 輕量版模型
    ollama_timeout_seconds: int = 90
    use_validation_mode: bool = True  # 是否使用驗證模式（僅驗證+評分，不生成摘要）
    
    # --- Embedding semantic recall ---
    enable_embedding_recall: bool = False
    embedding_model: str = "BAAI/bge-m3"
    embedding_top_k: int = 30
    embedding_similarity_threshold: float = 0.68

    # --- GitHub Issue tracking ---
    github_token: str = ""
    github_repo: str = ""  # e.g. "aaron-ren2021/webpccscrape"
    github_labels: list[str] = field(default_factory=list)

    @property
    def has_acs(self) -> bool:
        return bool(self.acs_connection_string and self.acs_email_sender)

    @property
    def has_smtp(self) -> bool:
        return bool(self.smtp_host and self.smtp_from and self.email_to)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            timezone=os.getenv("TZ", "Asia/Taipei"),
            user_agent=os.getenv("USER_AGENT", cls.user_agent),
            request_timeout_seconds=_parse_int(os.getenv("REQUEST_TIMEOUT_SECONDS"), 20),
            request_retry_total=_parse_int(os.getenv("REQUEST_RETRY_TOTAL"), 3),
            request_backoff_factor=_parse_float(os.getenv("REQUEST_BACKOFF_FACTOR"), 0.8),
            request_delay_min=_parse_float(os.getenv("REQUEST_DELAY_MIN"), 2.0),
            request_delay_max=_parse_float(os.getenv("REQUEST_DELAY_MAX"), 5.0),
            enable_playwright=_parse_bool(os.getenv("ENABLE_PLAYWRIGHT"), True),
            playwright_timeout_ms=_parse_int(os.getenv("PLAYWRIGHT_TIMEOUT_MS"), 20000),
            recent_days=_parse_int(os.getenv("RECENT_DAYS"), 1),
            high_amount_threshold=_parse_float(os.getenv("HIGH_AMOUNT_THRESHOLD"), 5_000_000.0),
            taiwanbuying_url=os.getenv("TAIWANBUYING_URL", "https://www.taiwanbuying.com.tw/"),
            taiwanbuying_method=os.getenv("TAIWANBUYING_METHOD", "GET").upper(),
            taiwanbuying_params=_parse_json(os.getenv("TAIWANBUYING_PARAMS_JSON")),
            taiwanbuying_row_selectors=_parse_csv(os.getenv("TAIWANBUYING_ROW_SELECTORS"))
            or ["table tbody tr", ".result-item", ".list-group-item"],
            taiwanbuying_title_selectors=_parse_csv(os.getenv("TAIWANBUYING_TITLE_SELECTORS"))
            or ["a", ".title", ".subject", "td:nth-child(2)"],
            taiwanbuying_org_selectors=_parse_csv(os.getenv("TAIWANBUYING_ORG_SELECTORS"))
            or [".org", ".unit", "td:nth-child(3)"],
            taiwanbuying_date_selectors=_parse_csv(os.getenv("TAIWANBUYING_DATE_SELECTORS"))
            or [".date", ".publish-date", "time", "td:nth-child(1)"],
            taiwanbuying_amount_selectors=_parse_csv(os.getenv("TAIWANBUYING_AMOUNT_SELECTORS"))
            or [".amount", ".price", "td:nth-child(5)"],
            taiwanbuying_summary_selectors=_parse_csv(os.getenv("TAIWANBUYING_SUMMARY_SELECTORS"))
            or [".summary", ".desc", "td:nth-child(4)"],
            taiwanbuying_link_selectors=_parse_csv(os.getenv("TAIWANBUYING_LINK_SELECTORS")) or ["a"],
            gov_url=os.getenv("GOV_URL", "https://web.pcc.gov.tw/pis/"),
            gov_method=os.getenv("GOV_METHOD", "GET").upper(),
            gov_params=_parse_json(os.getenv("GOV_PARAMS_JSON")),
            gov_row_selectors=_parse_csv(os.getenv("GOV_ROW_SELECTORS"))
            or ["table tbody tr", ".result-item", ".list-group-item"],
            gov_title_selectors=_parse_csv(os.getenv("GOV_TITLE_SELECTORS"))
            or ["a", ".title", ".subject", "td:nth-child(2)"],
            gov_org_selectors=_parse_csv(os.getenv("GOV_ORG_SELECTORS"))
            or [".org", ".unit", "td:nth-child(3)"],
            gov_date_selectors=_parse_csv(os.getenv("GOV_DATE_SELECTORS"))
            or [".date", ".publish-date", "time", "td:nth-child(1)"],
            gov_amount_selectors=_parse_csv(os.getenv("GOV_AMOUNT_SELECTORS"))
            if os.getenv("GOV_AMOUNT_SELECTORS") is not None
            else [".amount", ".price", "td:nth-child(5)"],
            gov_summary_selectors=_parse_csv(os.getenv("GOV_SUMMARY_SELECTORS"))
            or [".summary", ".desc", "td:nth-child(4)"],
            gov_link_selectors=_parse_csv(os.getenv("GOV_LINK_SELECTORS")) or ["a"],
            gov_detail_delay_seconds=_parse_float(os.getenv("GOV_DETAIL_DELAY_SECONDS"), 2.0),
            gov_detail_max_per_identity=_parse_int(os.getenv("GOV_DETAIL_MAX_PER_IDENTITY"), 3),
            g0v_api_url=os.getenv("G0V_API_URL", "https://pcc-api.openfun.app/api/listbydate"),
            g0v_enabled=_parse_bool(os.getenv("G0V_ENABLED"), True),
            api_only_mode=_parse_bool(os.getenv("API_ONLY_MODE"), False),
            azure_storage_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""),
            azure_table_name=os.getenv("AZURE_TABLE_NAME", "BidNotifyState"),
            azure_blob_container=os.getenv("AZURE_BLOB_CONTAINER", "bid-state"),
            azure_blob_name=os.getenv("AZURE_BLOB_NAME", "notified_state.json"),
            email_to=_parse_csv(os.getenv("EMAIL_TO")),
            email_subject_prefix=os.getenv("EMAIL_SUBJECT_PREFIX", "[教育資訊標案監控]"),
            acs_connection_string=os.getenv("ACS_CONNECTION_STRING", ""),
            acs_email_sender=os.getenv("ACS_EMAIL_SENDER", ""),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=_parse_int(os.getenv("SMTP_PORT"), 587),
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from=os.getenv("SMTP_FROM", ""),
            smtp_use_tls=_parse_bool(os.getenv("SMTP_USE_TLS"), True),
            smtp_use_ssl=_parse_bool(os.getenv("SMTP_USE_SSL"), False),
            dry_run=_parse_bool(os.getenv("DRY_RUN"), False),
            preview_html_path=os.getenv("PREVIEW_HTML_PATH", ""),
            # --- AI classification ---
            enable_ai_classification=_parse_bool(os.getenv("ENABLE_AI_CLASSIFICATION"), False),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            ai_model=os.getenv("AI_MODEL", ""),
            # --- Local LLM (Ollama) ---
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", ""),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            ollama_timeout_seconds=_parse_int(os.getenv("OLLAMA_TIMEOUT_SECONDS"), 90),
            use_validation_mode=_parse_bool(os.getenv("USE_VALIDATION_MODE"), True),
            # --- Embedding semantic recall ---
            enable_embedding_recall=_parse_bool(os.getenv("ENABLE_EMBEDDING_RECALL"), False),
            embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
            embedding_top_k=_parse_int(os.getenv("EMBEDDING_TOP_K"), 30),
            embedding_similarity_threshold=_parse_float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD"), 0.68),
            # --- Stealth / anti-detection ---
            stealth_enabled=_parse_bool(os.getenv("STEALTH_ENABLED"), True),
            stealth_human_behavior=_parse_bool(os.getenv("STEALTH_HUMAN_BEHAVIOR"), True),
            stealth_session_persistence=_parse_bool(os.getenv("STEALTH_SESSION_PERSISTENCE"), True),
            stealth_session_ttl_hours=_parse_float(os.getenv("STEALTH_SESSION_TTL_HOURS"), 24.0),
            stealth_session_dir=os.getenv("STEALTH_SESSION_DIR", ""),
            stealth_artifact_dir=os.getenv("STEALTH_ARTIFACT_DIR", ""),
            stealth_max_retries=_parse_int(os.getenv("STEALTH_MAX_RETRIES"), 2),
            stealth_headless=_parse_bool(os.getenv("STEALTH_HEADLESS"), True),
            stealth_throttle_delay_min=_parse_float(os.getenv("STEALTH_THROTTLE_DELAY_MIN"), 2.0),
            stealth_throttle_delay_max=_parse_float(os.getenv("STEALTH_THROTTLE_DELAY_MAX"), 6.0),
            stealth_throttle_cooldown_after=_parse_int(os.getenv("STEALTH_THROTTLE_COOLDOWN_AFTER"), 5),
            stealth_throttle_cooldown_min=_parse_float(os.getenv("STEALTH_THROTTLE_COOLDOWN_MIN"), 8.0),
            stealth_throttle_cooldown_max=_parse_float(os.getenv("STEALTH_THROTTLE_COOLDOWN_MAX"), 15.0),
            stealth_throttle_backoff_base=_parse_float(os.getenv("STEALTH_THROTTLE_BACKOFF_BASE"), 5.0),
            # --- Proxy ---
            proxy_enabled=_parse_bool(os.getenv("PROXY_ENABLED"), False),
            proxy_list=_parse_csv(os.getenv("PROXY_LIST")),
            proxy_strategy=os.getenv("PROXY_STRATEGY", "round_robin"),
            # --- GitHub Issue tracking ---
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
            github_labels=_parse_csv(os.getenv("GITHUB_LABELS")),
        )
