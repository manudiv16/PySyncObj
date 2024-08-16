#!/usr/bin/env python
from __future__ import print_function

import sys

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.append("../")
from pysyncobj import SyncObj, SyncObjConf, replicated, cluster_strategy
from logging import getLogger, StreamHandler, DEBUG

logger = getLogger()


class KVStorage(SyncObj):
    def __init__(self, dumpFile, cluster_strategy):
        conf = SyncObjConf(
            fullDumpFile=dumpFile,
            dynamicMembershipChange=True,
        )
        super(KVStorage, self).__init__(conf=conf, clustering_strategy=cluster_strategy)
        self.__data = {}

    @replicated
    def set(self, key, value):
        self.__data[key] = value

    @replicated
    def pop(self, key):
        self.__data.pop(key, None)

    def get(self, key):
        return self.__data.get(key, None)


_g_kvstorage = None


class KVRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            value = _g_kvstorage.get(self.path)

            if value is None:
                self.send_response(404)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(value.encode("utf-8"))
        except:
            pass

    def do_POST(self):
        try:
            key = self.path
            value = self.rfile.read(int(self.headers.get("content-length"))).decode(
                "utf-8"
            )
            logger.info("POST %s %s" % (key, value))
            _g_kvstorage.set(key, value)

            self.send_response(201)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
        except:
            pass


def main(port, cluster_port, application_domain):

    httpPort = int(port)
    dumpFile = "dump_file.bin"
    strategy = cluster_strategy.DnsPollingStrategy(
        domain=application_domain, port=cluster_port, poll_interval=5
    )
    global _g_kvstorage
    _g_kvstorage = KVStorage(dumpFile, strategy)
    httpServer = HTTPServer(("", httpPort), KVRequestHandler)
    logger.info("Starting http server on port %d..." % httpPort)
    httpServer.serve_forever()


if __name__ == "__main__":
    import os

    application_port = os.environ.get("APPLICATION_PORT", 8080)
    cluster_port = os.environ.get("CLUSTER_PORT", 45892)
    application_domain = os.environ.get("APPLICATION_DOMAIN", "pysyncobj")
    main(
        port=application_port,
        cluster_port=cluster_port,
        application_domain=application_domain,
    )
