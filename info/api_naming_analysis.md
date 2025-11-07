# API Naming Analysis

After analyzing 167 @AddAPI decorators across the codebase, here are the patterns found:

## Common Patterns

### 1. Verb-First Pattern (Most Common)
- `add`, `get`, `remove`, `set`, `check`, `register`, `unregister`
- Examples:
  - `add.timer`, `get.plugin.info`, `remove.timer`, `set.reload`
  - `register.to.event`, `unregister.from.event`

### 2. Noun-First Pattern
- Used for resource-specific operations
- Examples:
  - `client.count`, `client.add`, `client.remove`
  - `trigger.add`, `trigger.remove`, `trigger.get`
  - `watch.add`, `watch.remove`

### 3. Domain-First Pattern
- Groups related APIs by domain/category
- Examples:
  - `colorcode.to.html`, `colorcode.strip`, `colorcode.escape`
  - `ansicode.to.colorcode`, `ansicode.strip`
  - `preamble.get`, `preamble.color.get`

### 4. Mixed Patterns (Inconsistencies)
- `data.get` vs `get.data.directory`
- `has.timer` vs `is.plugin.loaded`
- `does.plugin.exist` vs `is.plugin.id`

## Recommendations

### Standard Conventions:
1. **Use verb-first for actions**: `get.X`, `add.X`, `remove.X`, `set.X`
2. **Use noun-first for resource operations**: `plugin.get`, `client.add`, `timer.remove`
3. **Use domain-first for converters/utilities**: `colorcode.to.ansicode`, `format.time`
4. **Standardize boolean checks**: Use `is.X` consistently (not `does.X.exist`, `has.X`, `can.X`)

### Examples of Standardization:
- `does.plugin.exist` → `plugin.exists` or `is.plugin.exists`
- `has.timer` → `timer.exists` or `is.timer.exists`
- `can.log.to.console` → `log.can.to.console` or `is.log.console.enabled`

### Priority Changes:
Most APIs are already well-structured. The main inconsistencies are:
1. Boolean check methods (`has.*`, `does.*`, `can.*`, `is.*`)
2. Some get/set operations could be more consistent
3. A few mixed patterns that could be unified

## Decision
Given the large number of APIs (167+) and the fact that most follow reasonable patterns,
I recommend **documenting the existing conventions** rather than mass-renaming.
Mass API renames would break existing code and provide minimal benefit.

Instead:
1. Document API naming conventions in CONTRIBUTING.md
2. Enforce conventions for NEW APIs via code review
3. Only fix truly confusing inconsistencies on a case-by-case basis
