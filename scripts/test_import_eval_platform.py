import sys
import os
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)
current_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
try:
    import eval_platform.backend.api as api
    print('OK - imported', getattr(api.app, 'title', 'no-app'))
except Exception as e:
    print('ERROR', e)
