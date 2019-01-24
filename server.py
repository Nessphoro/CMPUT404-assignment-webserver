#  coding: utf-8 
import asyncio
from urllib.parse import urlparse
import pathlib
import os
import stat

www_folder = pathlib.Path("./www").resolve()

class HttpException(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code
        self.reason = reason

    def write_error(self, writer):
        writer.write(get_status_line(self.code, self.reason))
        write_header(writer, ("Connection", "close"))

class MethodNotAllowed(HttpException):
    def __init__(self):
        super().__init__(405, "Method Not Allowed")

    def write_error(self, writer):
        super().write_error(writer)
        write_header(writer, ("Allow", "GET"))

class PermanentRedirect(HttpException):
    def __init__(self, location):
        super().__init__(301, "Moved Permanently")
        self.location = location

    def write_error(self, writer):
        super().write_error(writer)
        write_header(writer, ("Location", self.location))

class HttpEnd(Exception):
    pass

async def parse_http(reader):
    try:
        request_line = await reader.readline()
    except ConnectionResetError:
        raise HttpEnd()
    request_line = request_line.decode("utf-8")
    if not request_line:
        raise HttpEnd()

    request_line = request_line.strip()
    method, uri, version = request_line.split(" ")

    if method != "GET":
        raise MethodNotAllowed()
    
    if version != "HTTP/1.1":
        raise HttpException(400, "Bad Request")
    
    headers = {}

    while True:
        line = await reader.readline()
        line = line.decode("utf-8").strip().lower()
        if not line:
            break
        header, value = line.split(":", maxsplit=1)
        if header in headers:
            headers[header] = [headers[header], value]
        else:
            headers[header] = value

    if "host" in headers:
        uri = urlparse(f"//{headers['host']}{uri}").path
    else:
        uri = urlparse(uri).path

    return (uri, headers)

def write_header(writer, header):
    writer.write(f"{header[0]}: {str(header[1])}\r\n".encode("utf-8"))

async def send_file(writer, stats, filepath):
    try:
        filetype = filepath.suffix
        if filetype == ".html":
            filetype = "text/html; charset=utf-8"
        elif filetype == ".css":
            filetype = "text/css; charset=utf-8"
        else:
            filetype = "application/octet-stream"

        writer.write(get_status_line(200, "OK"))
        write_header(writer, ("Content-Type", filetype))
        write_header(writer, ("Content-Length", stats.st_size))
        writer.write(b"\r\n")
        with open(filepath, "rb") as fd:
            await asyncio.get_running_loop().sendfile(writer.transport, fd)
        await writer.drain()
    except:
        raise HttpEnd()

async def dispatch_request(writer, request):
    filepath = pathlib.Path(www_folder, f".{request[0]}")
    try:
        # Security check
        filepath.resolve().relative_to(www_folder)

        stats = os.stat(filepath)

        if stat.S_ISDIR(stats.st_mode):
            if request[0][-1] != "/":
                raise PermanentRedirect(request[0] + "/")
            filepath = pathlib.Path(filepath, "index.html")
            stats = os.stat(filepath)
            await send_file(writer, stats, filepath)
        else:
            # try to send directly
            await send_file(writer, stats, filepath)
    except (FileNotFoundError,ValueError):
        raise HttpException(404, "Not Found")
    
    
    
        

def get_status_line(code, message):    
    sline = ["HTTP/1.1", str(code), message, "\r\n"]
    return " ".join(sline).encode("utf-8")

async def error_response(writer, err: HttpException):
    err.write_error(writer)
    writer.write(b"\r\n")

    await writer.drain()
    writer.close()


async def handle(reader, writer):
    try:
        while True:
            request = await parse_http(reader)
            await dispatch_request(writer, request)
    except HttpException as err:
        await error_response(writer, err)
    except HttpEnd:
        pass

async def main():
    server = await asyncio.start_server(handle, host="127.0.0.1", port=8080)
    async with server:
        await server.serve_forever()


asyncio.run(main())