"""Run BastProxy with ``python -m bastproxy``.

Equivalent to the ``bastproxy`` console script. ``BASTPROXY_HOME`` must point
at an existing, writable directory.
"""

from bastproxy import main

if __name__ == "__main__":
    main()
