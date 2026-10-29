#!/usr/bin/env python3
"""Record every XNU compile as <object>.json and then run the real compiler.

`scripts/build-arm-driver.py` and `scripts/check-native-arch-timer-checkpoints.py`
both read a per-object compile recipe, `{directory, file, arguments}`, to
rebuild one translation unit with the flags the kernel build actually used.
Nothing in the tree produces those records on Linux: the objects and their .cpd
dependency files appear, but no .json does, and makedefs has no rule for one.
`BUILD_JSON_COMPILATION_DATABASE` is a different mode that replaces compilation
outright instead of recording it.

MakeInc.def compiles every kernel object through `$(CCACHE) $(CC)`, and nothing
defines CCACHE. Pointing it at this script fills the gap without touching the
build:

    CCACHE="python3 /path/to/compile-records.py" ./unixnu build kernel -D ../device

The script is a transparent wrapper: it writes the record and then execs the
command it was given, so a failing compile still fails and the record matches
the invocation that produced the object.
"""
from __future__ import annotations

import json
import os
import sys


def output_path(arguments: list[str]) -> str | None:
    for index, value in enumerate(arguments):
        if value == '-o' and index + 1 < len(arguments):
            return arguments[index + 1]
        if value.startswith('-o') and len(value) > 2:
            return value[2:]
    return None


def input_file(arguments: list[str]) -> str | None:
    for value in arguments:
        if value == '-c' or value == '-x':
            continue
        if value.endswith(('.c', '.cc', '.cpp', '.S', '.s', '.sx')):
            return value
    return None


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        return os.execvp('true', ['true'])

    output = output_path(arguments)
    source = input_file(arguments)
    # XNU's C rule compiles without -o and lets clang derive the object name from
    # the source, so fall back to that. The make working directory is the object
    # directory, which is where the archive builders look for the record.
    if not output and source:
        stem = os.path.basename(source)
        stem = os.path.splitext(stem)[0]
        output = f'{stem}.o'
    if output and source:
        record = {
            'directory': os.getcwd(),
            'file': source,
            'arguments': arguments,
        }
        target = f'{output}.json'
        try:
            # The build reads these with .rstrip(',\\n'), so a trailing
            # separator is accepted and a plain object is too.
            with open(target, 'w', encoding='utf-8') as handle:
                json.dump(record, handle)
        except OSError as error:
            print(f'compile-records: cannot write {target}: {error}', file=sys.stderr)

    os.execvp(arguments[0], arguments)


if __name__ == '__main__':
    raise SystemExit(main())
