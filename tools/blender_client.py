"""Client for the installed official Blender MCP add-on's local transport."""
import argparse
import json
import socket
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

def execute(code, timeout=600):
    with socket.create_connection(('127.0.0.1', 9876), timeout=10) as sock:
        sock.settimeout(timeout)
        sock.sendall(json.dumps({'type': 'execute', 'code': code, 'strict_json': True}).encode() + b'\0')
        buf = bytearray()
        while b'\0' not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
        return json.loads(buf.split(b'\0')[0])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('script', nargs='?')
    parser.add_argument('--models', nargs='+')
    args = parser.parse_args()
    code = Path(args.script).read_text(encoding='utf-8') if args.script else "import bpy\nresult = {'file': bpy.data.filepath, 'objects': [{'name': o.name, 'type': o.type, 'dimensions': list(o.dimensions)} for o in bpy.context.scene.objects]}"
    if args.models:
        code = 'FLEET_IDS = ' + repr(args.models) + '\n' + code
    response = execute(code)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    if response.get('status') == 'error':
        raise SystemExit(1)
