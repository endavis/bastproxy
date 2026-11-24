Skill: portable-tests

Self-check before writing an exact-value assertion in a test:

1. Is the expected value built from a path? A `Path` renders with `\` on
   Windows. Build the expected value with the same `Path` type, or feed
   `PurePosixPath` input — never compare it to a POSIX literal such as
   `"/some/dir"` (pynetappfoundry#1164).
2. Does the test need a scratch directory? Use pytest's `tmp_path`, never a
   hard-coded `/tmp`.
3. Does the behavior depend on file mode bits, executable bits or a POSIX
   shell? Mark the test `skipif(sys.platform == "win32", reason=...)`, with
   a reason naming the POSIX-only behavior (bastproxy#380, bastproxy#499).

Observed failures: endavis/pynetappfoundry#1164, endavis/bastproxy#380, endavis/bastproxy#499
