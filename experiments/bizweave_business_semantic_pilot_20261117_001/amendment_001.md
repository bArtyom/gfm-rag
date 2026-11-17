# Amendment 001 — launcher wrapper recovery

Before the smoke process started, the first shell command exited with code 127 because `/usr/bin/time` is not installed on this host. The captured log contains only that launcher error; the Python runner did not start and no result file was created. The next attempt uses Bash's built-in `time` keyword. Dataset, interpreter, code, limits, and preregistered decisions are unchanged; the retry writes to a new output/log filename so the failed attempt remains preserved.
