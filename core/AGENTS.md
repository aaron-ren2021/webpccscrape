# AGENTS.md

## Prime Directive

Before changing code, always produce and wait for user approval on:

1. Architecture impact
2. Risk analysis
3. Rollback strategy
4. Migration note

Do not edit code until the user explicitly approves the plan.

## Required Pre-Code Report

For every non-trivial change, first output:

### Architecture Impact
- Affected modules/files
- Data flow changes
- API/config/schema changes
- Runtime behavior changes
- Backward compatibility impact

### Risk Analysis
- Possible regressions
- Edge cases
- Security or data integrity risks
- Test coverage gaps
- Operational impact

### Rollback Strategy
- How to revert safely
- Git revert/tag/branch strategy
- Config fallback if applicable
- Data rollback if applicable

### Migration Note
- Required env/config changes
- Required manual steps
- Deployment order
- Compatibility notes
- User-facing changes

## Commit Discipline

- Never modify unrelated files.
- Never commit pre-existing user changes.
- Use a feature branch for all work.
- Prefer draft PRs for review.
- Mention uncommitted unrelated changes before committing.
- Do not push directly to protected branches.

## Implementation Rule

After approval:

1. Make the smallest safe change.
2. Add or update tests.
3. Run relevant tests.
4. Summarize diff.
5. Provide verification steps.