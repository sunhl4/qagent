"""Isolate loopback framing and close behavior; inert bytes only, no platform import."""
import argparse
import http.client
import json
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for mode in ("close", "keepalive", "halfclose", "combined", "graceful"):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                data = b"x" * int(self.path[1:])
                if mode == "combined":
                    self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                                     + str(len(data)).encode() + b"\r\nConnection: close\r\n\r\n" + data)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(data)))
                    if mode != "keepalive":
                        self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(data)
                self.wfile.flush()
                if mode in ("halfclose", "graceful"):
                    self.connection.shutdown(socket.SHUT_WR)
                if mode == "graceful":
                    self.connection.settimeout(0.25)
                    try:
                        self.connection.recv(1024)
                    except (OSError, TimeoutError):
                        pass
                self.close_connection = mode != "keepalive"

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for client in ("urllib", "http_client"):
                for size in (2000, 8050, 32000, 64000):
                    for attempt in range(3):
                        row = {"mode": mode, "client": client, "size": size, "attempt": attempt}
                        try:
                            if client == "urllib":
                                request = urllib.request.Request(
                                    f"http://127.0.0.1:{server.server_port}/{size}", data=b"{}")
                                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                                    request, timeout=3
                                ) as response:
                                    row["received"] = len(response.read())
                            else:
                                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                                try:
                                    conn.request("POST", f"/{size}", body=b"{}")
                                    row["received"] = len(conn.getresponse().read())
                                finally:
                                    conn.close()
                        except Exception as error:
                            row["error"] = type(error).__name__
                        rows.append(row)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    with args.output.open("x") as stream:
        json.dump(rows, stream, indent=2)
    print(json.dumps({mode: sum("error" in row for row in rows if row["mode"] == mode)
                      for mode in ("close", "keepalive", "halfclose", "combined", "graceful")}))


if __name__ == "__main__":
    main()
