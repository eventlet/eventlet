#!/usr/bin/env python
import argparse
from datetime import datetime, timedelta
import os
import subprocess
import sys
from pathlib import Path

import trustme

cmdline = argparse.ArgumentParser()
cmdsub = cmdline.add_subparsers(required=True)
cmd_check = cmdsub.add_parser("check")
cmd_check.add_argument("data_dir", type=Path, default=Path.cwd())
cmd_check.set_defaults(fun="task_check")
cmd_generate = cmdsub.add_parser("generate")
cmd_generate.add_argument("data_dir", type=Path, default=Path.cwd())
cmd_generate.add_argument("-server-cn", default="localhost")
cmd_generate.set_defaults(fun="task_generate")

ALL_CERTS = (
    "ca.pem",
    "client_chain.pem",
    "client.pem",
    "server_chain.pem",
    "server.pem",
)
ALL_KEYS = ("ca.key", "client.key", "server.key")
GEN_VALID = timedelta(days=20 * 365)


def log(msg):
    print(msg, file=sys.stderr)


def run_openssl(*args):
    args = ("openssl",) + args
    rc = subprocess.call(args, stdin=subprocess.DEVNULL)
    if rc != 0:
        log(f"command '{' '.join(args)}' failed with return code {rc}")
        sys.exit(1)


def task_check(args):
    os.chdir(args.data_dir)

    checkend = 3600
    log("- check certificates valid within 1 hour")
    for cert_path in ALL_CERTS:
        run_openssl("x509", "-noout", "-in", cert_path, "-checkend", str(checkend))

    log("- check keys")
    for key_path in ALL_KEYS:
        run_openssl(
            "rsa",
            "-check",
            "-noout",
            "-in",
            key_path,
            *(("-passin", "pass:12345") if "_encrypted" in key_path else ()),
        )


def task_generate(args):
    moment = datetime.utcnow().replace(microsecond=0)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(args.data_dir)

    log("- generate CA")
    ca = trustme.CA()
    ca.cert_pem.write_to_path("ca.pem")
    ca.private_key_pem.write_to_path("ca.key")

    def issue_cert(slug, names):
        not_after = moment + GEN_VALID
        log(f"- issue certificate for {slug} valid not after {not_after}")
        cert = ca.issue_cert(*names, common_name=names[0], not_after=not_after)
        cert.private_key_pem.write_to_path(f"{slug}.key")
        cert.cert_chain_pems[0].write_to_path(f"{slug}.pem")
        Path(f"{slug}_chain.pem").write_bytes(
            cert.cert_chain_pems[0].bytes() + ca.cert_pem.bytes() + cert.private_key_pem.bytes()
        )

    issue_cert("client", (f"client1",))
    issue_cert("server", (args.server_cn,))

    task_check(args)


if __name__ == "__main__":
    args = cmdline.parse_args()
    args.data_dir = args.data_dir.resolve()
    cmd_fun = globals()[args.fun]
    cmd_fun(args)
