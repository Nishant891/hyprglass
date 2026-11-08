"""Find a literal terminal field without executing or rewriting a Lua program."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    quoted: bool = False


def tokens(text):
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        comment = text.startswith('--', position)
        start = position + 2 if comment else position
        bracket = re.match(r'\[(=*)\[', text[start:])
        if bracket:
            closing = ']' + bracket[1] + ']'
            end = text.find(closing, start + bracket.end())
            if end < 0:
                raise ValueError('Unclosed Lua comment or string in local.lua.')
            end += len(closing)
            if not comment:
                yield Token(text[start:end], start, end, True)
            position = end
        elif comment:
            end = text.find('\n', start)
            position = end if end >= 0 else len(text)
        elif text[position] in ('"', "'"):
            quote, end = text[position], position + 1
            while end < len(text) and text[end] != quote:
                end += 2 if text[end] == '\\' else 1
            if end >= len(text):
                raise ValueError('Unclosed Lua string in local.lua.')
            yield Token(text[position + 1:end], position, end + 1, True)
            position = end + 1
        else:
            word = re.match(r'[A-Za-z_][A-Za-z_0-9]*', text[position:])
            end = position + (word.end() if word else 1)
            yield Token(text[position:end], position, end)
            position = end


def terminal_field(text):
    items = list(tokens(text))
    returns = [index + 1 for index, item in enumerate(items[:-1])
               if not item.quoted and item.value == 'return' and items[index + 1].value == '{']
    if len(returns) != 1:
        raise ValueError('local.lua must have one literal return table. Set terminal = "kitty" inside it.')
    opening = returns[0]
    depth, found = 1, []
    for index in range(opening + 1, len(items)):
        item = items[index]
        if not item.quoted and item.value in ('{', '}'):
            depth += 1 if item.value == '{' else -1
            if depth == 0:
                break
        if depth != 1:
            continue
        offset = 1
        if item.quoted and item.value == 'terminal' and items[index - 1].value == '[':
            offset = 2
        elif item.quoted or item.value != 'terminal':
            continue
        if index + offset + 2 >= len(items) or items[index + offset].value != '=':
            continue
        value = items[index + offset + 1]
        following = items[index + offset + 2].value
        if not value.quoted or text[value.start] not in ('"', "'") or following not in (',', ';', '}') \
                or not re.fullmatch(r'[A-Za-z0-9_.+-]+', value.value):
            raise ValueError('Use a literal executable terminal field in local.lua, for example terminal = "kitty".')
        found.append(value)
    if depth != 0:
        raise ValueError('Unclosed return table in local.lua.')
    if len(found) > 1:
        raise ValueError('local.lua has multiple terminal assignments. Keep one terminal field before setup.')
    return (found[0] if found else None), items[opening].end
