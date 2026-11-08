import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def test_symlinked_command_reads_notes_from_another_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            command = directory / 'hypr-glass'
            command.symlink_to(ROOT / 'bin/hypr-glass')
            notebook = directory / 'notebook'
            result = subprocess.run([str(command), 'notes', 'list'], cwd=directory,
                                    env=dict(os.environ, HYPR_NOTES_DIR=str(notebook),
                                             XDG_RUNTIME_DIR=temporary, PYTHONPATH=''),
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['tasks'], [])
            self.assertFalse(notebook.exists())

    @unittest.skipUnless(shutil.which('lua'), 'Lua interpreter is optional for Python checks')
    def test_application_binding_preserves_executable_and_argument_boundaries(self):
        program = '''
local original_getenv = os.getenv
os.getenv = function(name)
    if name == "HOME" then return "/home/test user" end
    return original_getenv(name)
end
local proxy
proxy = setmetatable({}, {
    __index = function() return proxy end,
    __call = function(_, ...) return {arguments={...}} end,
})
local noop = function() end
hl = setmetatable({
    dsp = proxy,
    on = noop,
    bind = function(key, action)
        if key == "SUPER + SPACE" then print(action.arguments[1]) end
    end,
}, {__index=function() return noop end})
dofile = noop
assert(loadfile(arg[1]))()
'''
        result = subprocess.run(['lua', '-', str(ROOT / 'hyprglass/desktop/config.lua')],
                                input=program, capture_output=True, text=True, check=True)
        self.assertEqual(shlex.split(result.stdout.strip()),
                         ['/home/test user/.config/hypr/bin/hypr-glass', 'launcher'])
