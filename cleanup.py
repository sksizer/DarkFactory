#!/usr/bin/env python3
import os
import subprocess
import sys

# Delete the test file
try:
    if os.path.exists('tests/test_builtins.py'):
        os.remove('tests/test_builtins.py')
        print(f"Deleted tests/test_builtins.py")

        # Stage the deletion with git
        result = subprocess.run(['git', 'add', '-u'], check=True)
        print("Staged deletion with git add -u")
        sys.exit(0)
    else:
        print("File does not exist")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
