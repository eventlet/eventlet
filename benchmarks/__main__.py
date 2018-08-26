# this file is required to support `python -m benchmarks` syntax
import sys
import benchmarks
try:
    benchmarks.main()
except KeyboardInterrupt:
    sys.exit(1)
