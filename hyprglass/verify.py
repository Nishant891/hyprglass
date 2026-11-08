#!/usr/bin/env python3
"""Exercise the visible widgets. --notes also adds and removes one test task."""
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

from hyprglass.paths import BASE
from hyprglass.notes.storage import DailyNotes
os.chdir(BASE)

def walk(node):
    yield node
    for index in range(node.get_child_count()):
        yield from walk(node.get_child_at_index(index))

def nodes(app_name):
    root = Atspi.get_desktop(0)
    app = next(node for node in walk(root)
               if node.get_role_name() == 'application' and node.get_name() in ((app_name, 'Hypr glass') if app_name == 'hypr-glass' else (app_name,)))
    return list(walk(app))

def find(app, role, name=None):
    return next(node for node in nodes(app) if node.get_role_name() == role
                and (name is None or node.get_name() == name))

def press(app, name):
    assert find(app, 'button', name).get_action_iface().do_action(0)
    time.sleep(.3)

def wait_for(predicate, message, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.25)
    raise AssertionError(message)

def launch(action):
    subprocess.run([str(BASE / 'bin/hypr-glass'), action], check=True, timeout=5)
    time.sleep(.5)

def layers():
    data = json.loads(subprocess.check_output(['hyprctl', '-j', 'layers']))
    return [item for monitor in data.values() for group in monitor['levels'].values() for item in group]

def visible_text():
    return [node.get_name() for node in nodes('hypr-glass') if node.get_role_name() == 'label']

def input_text(app, text):
    assert find(app, 'text').get_editable_text_iface().set_text_contents(text)

if '--notes-only' not in sys.argv:
    if not any(item['namespace'] == 'hypr-assistant' for item in layers()):
        launch('assistant')
    press('hypr-glass', 'New conversation')
    input_text('hypr-glass', 'Reply with just: desktop widget is ready')
    press('hypr-glass', '↑')
    wait_for(lambda: any(text.lower().strip() == 'desktop widget is ready' for text in visible_text()),
             'No local AI answer appeared', 100)
    print('PASS: the visible AI panel produced a local answer')
    launch('calendar')
    month = date.today().replace(day=1)
    press('hypr-glass', '›')
    number = month.year * 12 + month.month
    next_month = date(number // 12, number % 12 + 1, 1)
    assert next_month.strftime('%B %Y') in visible_text()
    press('hypr-glass', '‹')
    assert month.strftime('%B %Y') in visible_text()
    assert not any(node.get_name().lower() == 'today' for node in nodes('hypr-glass'))
    print('PASS: calendar navigation works without a Today button')
    launch('calendar')
if any(item['namespace'] == 'hypr-assistant' for item in layers()):
    launch('assistant')
if not any(item['namespace'] == 'swaync-control-center' for item in layers()):
    launch('panel')
assert any(item['namespace'] == 'swaync-control-center' for item in layers())
assert not any(item['namespace'] == 'hypr-todo' for item in layers())
assert find('swaync', 'button', '+')
print('PASS: Todo belongs to the single native SwayNC window')

if '--notes' in sys.argv or '--notes-only' in sys.argv:
    notes = DailyNotes()
    before = notes.list()
    path = Path(before['path'])
    original = path.read_bytes() if path.exists() else b''
    marker = 'Desktop verification ' + uuid.uuid4().hex
    try:
        press('swaync', '+')
        input_text('swaync', marker)
        caps_visibility = []
        for _ in range(2):
            subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.send_shortcut({mods="", key="Caps_Lock"}))'],
                           check=True, capture_output=True, text=True)
            time.sleep(.2)
            caps_visibility.append(any(item['namespace'] == 'swaync-control-center' for item in layers()))
        assert all(caps_visibility), 'Caps Lock closed Todo'
        print('PASS: Caps Lock kept the focused Todo input open', flush=True)
        subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.send_shortcut({mods="", key="Return"}))'],
                       check=True, capture_output=True, text=True)
        wait_for(lambda: any(task['text'] == marker for task in notes.list()['tasks']),
                 'Todo did not save the task')
        wait_for(lambda: any(node.get_role_name() == 'check box' and marker in node.get_name()
                            for node in nodes('swaync')), 'No native checkbox appeared')
        check = next(node for node in nodes('swaync')
                     if node.get_role_name() == 'check box' and marker in node.get_name())
        for _ in range(2):
            subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.send_shortcut({mods="SHIFT", key="Tab"}))'],
                           check=True, capture_output=True, text=True)
        subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.send_shortcut({mods="", key="space"}))'],
                       check=True, capture_output=True, text=True)
        wait_for(lambda: any(task['text'] == marker and task['done'] for task in notes.list()['tasks']),
                 'Checkbox did not update Markdown')
        press('swaync', 'Delete task: ' + marker)
        wait_for(lambda: all(task['text'] != marker for task in notes.list()['tasks']),
                 'Delete button did not remove the task')
        assert path.read_bytes() == original, 'Unrelated Markdown changed'
        print('PASS: Caps Lock kept Todo open; add, toggle, and delete updated Markdown')
    finally:
        for task in notes.list()['tasks']:
            if task['text'] == marker:
                notes.delete(task['line'], task['fingerprint'])
subprocess.run([str(BASE / 'bin/hypr-glass'), 'notifications', '-cp', '-sw'], check=True)
