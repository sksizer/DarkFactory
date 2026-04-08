#!/usr/bin/env python3
import os
import stat

# Make pre-push hook executable
pre_push = '.scripts/git-hooks/pre-push'
st = os.stat(pre_push)
os.chmod(pre_push, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

# Make install script executable
install_script = 'scripts/install-hooks.sh'
st = os.stat(install_script)
os.chmod(install_script, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

print('Files made executable')
