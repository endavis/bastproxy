---
title: Utils Plugin
description: The formatting, time and value-conversion APIs of plugins.core.utils
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - utils
---

# Utils Plugin

## Overview

`plugins.core.utils` is a required plugin that holds shared helpers. It formats text for output (tables, columns, centered and capped lines), converts and formats time lengths, and converts setting values. It has no commands or settings of its own. Other plugins and `libs/` reach it through the API, for example `self.api("plugins.core.utils:table.format")(...)`.

**Location**: `src/bastproxy/plugins/core/utils/plugin/_utils.py`

Widths are display widths, measured on colour-stripped text with `bastproxy.libs.textwidth`. A colour code such as `@R` takes no room, and a wide character takes two columns.

## Output Formatting

### `table.format(table_name, data, columns, color="")`

Returns a list of lines: a header with `table_name`, a column header row, a separator, the data rows and a closing separator.

- `columns` is a list of dicts with `name` (the header label) and `key` (the row dict key). Column widths are computed from the cells; a `width` key passed in is ignored, and the column dicts are not modified.
- `data` is any iterable of row dicts. It is read once.
- `color` is the colour of the frame. It defaults to the `output_subheader_color` setting of `plugins.core.commands`.
- The table fits the client's line length (`plugins.core.proxy:line.length.get`). When rows are too wide, data cells wrap inside their columns, first at spaces and then inside words. If that is not enough, header labels wrap too. The table only grows past the line length when one column per cell still cannot fit.
- An empty `columns` gives `[]`.

### `column.format(obj, cols=4, columnwise=True, gap=4)`

Formats a list in evenly spaced columns and returns the lines. Each item is converted with `str()`.

- `cols` is the number of columns; a value below 1 is treated as 1.
- With `columnwise=True`, items run down each column, otherwise across each row.
- `gap` is the number of spaces after the widest item.
- An empty list gives `[]`.

### `string.center.colored(string_to_center, filler_character="", length=None, filler_color="", endcaps=False, capchar="|")`

Centers a string that may hold colour codes, with two spaces on each side and `filler_character` filling the rest.

- `length` defaults to the client's line length.
- A filler of several characters is repeated and trimmed to fill the width exactly. An empty filler leaves the sides empty.
- `filler_color` colours the filler.
- With `endcaps=True`, the line is capped with `capchar` through `line.cap`.

### `line.cap(line, capchar="|", color="", line_length=None, space=True, fullcolor=False)`

Pads `line` to `line_length` (default: the client's line length) and puts `capchar` at both ends, with a space inside each cap when `space` is true. `color` colours the caps; with `fullcolor`, the colour also runs into the line.

### `string.dedent(list_of_strings)`

Removes the smallest indentation of the non-blank lines from every line. A whitespace-only line becomes `""`. The input list is not modified.

### `object.dump(object)`

Returns a text dump of an object, made with the `dumper` package.

### `dict.key.list(d)`

Returns every key of a dict and of the dicts nested in it, depth first.

### `string.match.in.list(arg, item_list)`

Finds `arg` in a list, taking it literally:

1. If `arg` is in the list, returns `[arg]`.
2. Otherwise, returns the string items that start with `arg`.
3. If there are none, returns the string items that contain it.

Items that are not strings are skipped.

### `number.to.readable(num, places=2)`

Returns a short readable `str` for a number.

- Zero is `"0"`, and a magnitude under 1000 is its own text (`"999.5"`).
- Larger magnitudes are scaled to K, M, B or T with `places` decimals (`"1.50 M"`).
- A value that rounds up to 1000 of a unit moves up a unit (`999999` gives `"1.00 M"`).
- A negative number keeps its sign.

## Time Lengths

### Time length format

`timelength.to.seconds(timel)` converts text like `1d:2h:30m:40s` to whole seconds, and returns `None` for anything it cannot parse.

- The text is one or more `<number><unit>` parts, with the unit `d`, `h`, `m` or `s`.
- Units must come in that order, and each may appear only once. A single `:` may follow a part.
- Numbers may be decimals (`1.5h`, `.5d`). The total is rounded to whole seconds.
- Surrounding whitespace is ignored. A negative value, or a value with no unit, gives `None`.

The same parser is available in the module as `parse_timelength`.

### `seconds.to.dhms(seconds)`

Splits seconds into a dict with `years`, `days`, `hours`, `mins` and `secs` (a year is 365 days). For a negative input, each part is negated, so the parts still add up to the input.

### `timelength.format(length, nosec=False)`

Formats seconds as text, such as `01h:01m:40s` or `1y:01s`. Parts that are zero are left out at the front, and `0` is `00s`.

- A negative length gets a `-` prefix.
- With `nosec`, the seconds are left out, and a length under a minute is `00m`.

### `timedelta.to.string(start_time, end_time, fmin=False, colorn="", colors="", nosec=False)`

Formats the difference between two times as `##d:##h:##m:##s`.

- Each time may be a number of seconds, a `datetime.datetime` or a `time.struct_time`. The order does not matter, because the absolute difference is used.
- `fmin` always shows minutes.
- `colorn` and `colors` colour the numbers and the unit letters.
- With `nosec`, the seconds are left out, and a difference under a minute is `00m`.

## Value Conversion

### `value.verify(value, vtype)`

Converts `value` to a setting type, or raises `ValueError`. The settings plugin calls it whenever a setting is added or set. The types are:

| `vtype` | Accepts | Returns |
| :--- | :--- | :--- |
| `bool` | a bool, `0`/`1`, or `true`/`yes`/`on`/`1` and `false`/`no`/`off`/`0` in any case | `bool` |
| `int` | an int or an integer string; a bool is refused | `int` |
| `str` | anything | `str(value)` |
| `list` | a list or tuple; a str is refused | a new `list` |
| `"color"` | a valid colour code (`plugins.core.colors:colorcode.is.valid`) | the value |
| `"miltime"` | exactly four ASCII digits, `HHMM` from `0000` to `2359` | the value |
| `"timelength"` | an integer, or the time length format above; negative values are refused | `int` seconds |
| any other callable | whatever the callable accepts | `vtype(value)` |

Any other `vtype` raises `ValueError("unknown setting type ...")`. See [Settings System](settings_system.md) for how settings use these types.

## Module Helpers

`_utils.py` also defines helpers that take no plugin instance, so they can be imported and tested directly:

- `to_bool`, `to_int`, `to_str`, `to_list` and the `CONVERTERS` map behind `value.verify`;
- `parse_timelength`;
- `fit_column_widths` and `wrap_cell`, the width fitting and cell wrapping used by `table.format`.
