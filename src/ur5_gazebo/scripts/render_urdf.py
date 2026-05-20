#!/usr/bin/env python3

import re
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: render_urdf.py ROBOT_XACRO [name:=value ...]", file=sys.stderr)
        return 2

    command = ["xacro", *sys.argv[1:]]
    result = subprocess.run(command, check=True, capture_output=True, text=True)

    xml = result.stdout
    xml = re.sub(r"<\?xml[^>]*\?>", "", xml)
    xml = re.sub(r"<!--.*?-->", "", xml, flags=re.DOTALL)
    xml = re.sub(r">\s+<", "><", xml)
    xml = re.sub(r"\s+", " ", xml)
    print(xml.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
