# Left Toolbar Cluster Autoscale (Experiment)

This change is an experiment behind a reversible patch.

## Files touched

- (pending)

## Symbols / classes added or modified

- (pending)

## Constraints added/changed

- (pending)

## Constants introduced

- (pending)

## Kill switch (fast rollback, no git)

- Set `ToolbarAutoScale.isEnabled = false`.

## Git rollback (exact commands)

- List the rollback tag:
  - `git tag --list "pre-left-toolbar-autoscale-rollback-*"`
- Reset this branch back to the pre-work tag:
  - `git reset --hard pre-left-toolbar-autoscale-rollback-YYYYMMDD_HHMMSS`
- Or hard-revert the last commit:
  - `git reset --hard HEAD~1`
