#!/usr/bin/env python3
"""CLI tool for analyzing crawler detection logs and generating KPI reports.

Usage:
    python analyze_crawler_logs.py                    # Analyze latest detection logs
    python analyze_crawler_logs.py --json events.json # Analyze from JSON file
    python analyze_crawler_logs.py --export report.json # Export metrics to JSON
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from crawler.analytics.kpi_analyzer import KPIAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze crawler detection logs and generate KPI reports"
    )
    parser.add_argument(
        "--json",
        type=str,
        help="Path to JSON file containing detection events",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export metrics to JSON file at specified path",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=".detection_logs",
        help="Directory containing detection artifacts (default: .detection_logs)",
    )
    
    args = parser.parse_args()
    
    analyzer = KPIAnalyzer()
    
    # Load events
    if args.json:
        print(f"Loading events from: {args.json}")
        try:
            analyzer.load_events_from_json(args.json)
        except FileNotFoundError:
            print(f"Error: File not found: {args.json}")
            sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Note: To analyze logs, you need to save DetectionLogger events to a JSON file first.")
        print("Example usage:")
        print("  1. In your code: det_logger.export_events_json('events.json')")
        print("  2. Then run: python analyze_crawler_logs.py --json events.json")
        sys.exit(0)
    
    # Analyze
    print("Analyzing events...")
    metrics = analyzer.analyze()
    
    # Generate and print report
    report = analyzer.generate_report(metrics)
    print("\n" + report)
    
    # Export if requested
    if args.export:
        analyzer.export_metrics_json(metrics, args.export)
        print(f"\nMetrics exported to: {args.export}")


if __name__ == "__main__":
    main()
