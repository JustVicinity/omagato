"""Apply renderer limits in a fresh process, without preexec_fn in threads."""
import os
import resource
import sys

resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
os.execv(sys.argv[1], [sys.argv[1], '-w', '256', '-h', '256', '--keep-aspect-ratio'])
