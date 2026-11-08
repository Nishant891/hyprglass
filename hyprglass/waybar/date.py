#!/usr/bin/env python3
"""Waybar's local date, including English ordinal day suffixes."""

from datetime import datetime

def format_date(now):
    day = now.day
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{now:%a}, {day}{suffix} {now.strftime('%b').upper()} {now:%Y}"

if __name__ == "__main__":
    print(format_date(datetime.now()))
