"""Launch the unified FastAPI API and Web Studio on one port."""

import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def start_server(port: int = 8088) -> None:
    from agent.api.app import app

    print("==================================================")
    print("[+] DataSphere Studio is running on FastAPI")
    print(f"[+] Local URL: http://localhost:{port}")
    print(f"[+] API docs: http://localhost:{port}/docs")
    print("==================================================")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    port = 8088
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port)
