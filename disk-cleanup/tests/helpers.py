"""Small helpers shared by the disk-cleanup tests."""
import os

from fixture import FakeWin
import scan


def run_scan(pc, root, env=None, win=None, **kw):
    sc = scan.Scanner(env or pc.env(), win or FakeWin(), root, **kw)
    return sc, sc.run()


def rel(pc, path):
    """`path` relative to the made-up PC, as is (relpath would drop a trailing space or dot)."""
    base = pc.base.rstrip("\\") + "\\"
    assert os.path.normcase(path).startswith(os.path.normcase(base)), path
    return path[len(base):]


def group(report, gid):
    return next((g for g in report["groups"] if g["id"] == gid), None)


def item_paths(pc, report, gid):
    g = group(report, gid)
    return {rel(pc, i["path"]) for i in g["items"]} if g else set()


def skipped(pc, report, gid):
    """{relative path: reason} of a group's skipped list, listed or not."""
    for g in report["groups"] + report["left_out"]:
        if g["id"] == gid:
            return {rel(pc, s["path"]): s["reason"] for s in g["skipped"]}
    return {}


def all_items(report):
    return [i for g in report["groups"] for i in g["items"]]


U = "C\\Users\\you\\"
LO = U + "AppData\\Local\\"
RO = U + "AppData\\Roaming\\"
