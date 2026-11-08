#!/usr/bin/env python3
"""Read and update the current daily note, returning one JSON object."""
import json
import sys
from hyprglass.notes.storage import DailyNotes

def main(arguments):
    notes = DailyNotes()
    if arguments == ['list']:
        return notes.list()
    if arguments == ['ensure']:
        return notes.ensure()
    if len(arguments) == 2 and arguments[0] == 'add':
        return notes.add(arguments[1])
    if len(arguments) == 3 and arguments[0] == 'delete':
        return notes.delete(int(arguments[1]), arguments[2])
    if len(arguments) == 4 and arguments[0] == 'toggle':
        if arguments[3].lower() not in ('true', 'false'):
            raise ValueError('Task state must be true or false.')
        return notes.toggle(int(arguments[1]), arguments[2], arguments[3].lower() == 'true')
    raise ValueError('Usage: daily-notes.py list|ensure|add TEXT|delete LINE FINGERPRINT|toggle LINE FINGERPRINT true|false')

if __name__ == '__main__':
    try:
        print(json.dumps(main(sys.argv[1:]), ensure_ascii=False))
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        sys.exit(1)
