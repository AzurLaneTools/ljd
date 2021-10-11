#!/usr/bin/python3
#
# The MIT License (MIT)
#
# Copyright (c) 2013 Andrian Nord
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import logging
import io
import os
import sys
import time

import ljd.rawdump.parser
import ljd.rawdump.code
import ljd.pseudoasm.writer
import ljd.pseudoasm.instructions
import ljd.ast.builder
import ljd.ast.slotworks
import ljd.ast.validator
import ljd.ast.locals
import ljd.ast.unwarper
import ljd.ast.mutator
import ljd.ast.printast
import ljd.lua.writer

logger = logging.getLogger(__name__)


class MakeFileHandler(logging.FileHandler):
    def __init__(self, filename, *args, **kwargs):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        logging.FileHandler.__init__(self, filename, *args, **kwargs)


def set_luajit_version(bc_version):
    # If we're already on this version, skip resetting everything
    if ljd.CURRENT_VERSION == bc_version:
        return

    ljd.CURRENT_VERSION = bc_version
    # Now we know the LuaJIT version, initialise the opcodes
    if bc_version == 20:
        from ljd.rawdump.opcode.v20 import _OPCODES as opcodes
    elif bc_version == 21:
        from ljd.rawdump.opcode.v21 import _OPCODES as opcodes
    else:
        raise ValueError(f"Unknown LuaJIT opcode module name for version {bc_version}")

    ljd.rawdump.code.init(opcodes)
    ljd.ast.builder.init()
    ljd.pseudoasm.instructions.init()


def decompile(header, prototype):
    ast = ljd.ast.builder.build(header, prototype)
    assert ast, 'invalid ast %r' % ast

    ljd.ast.validator.validate(ast, warped=True)
    ljd.ast.mutator.pre_pass(ast)
    ljd.ast.validator.validate(ast, warped=True)
    ljd.ast.locals.mark_locals(ast)
    ljd.ast.slotworks.eliminate_temporary(ast, identify_slots=True)
    ljd.ast.unwarper.unwarp(ast, False)
    ljd.ast.locals.mark_local_definitions(ast)
    ljd.ast.mutator.primary_pass(ast)
    ljd.ast.validator.validate(ast, warped=False)
    ljd.ast.locals.mark_locals(ast, alt_mode=True)
    ljd.ast.locals.mark_local_definitions(ast)
    return ast


def process_file(path_in, path_out):
    logger.debug('process file start %s -> %s', path_in, path_out)

    header, prototype = ljd.rawdump.parser.parse(path_in)
    assert prototype

    ast = decompile(header, prototype)

    with open(path_out, 'w', -1, 'UTF8') as f:
        ljd.lua.writer.write(f, ast)


def process_bytes(data):
    f = io.BytesIO(data)

    header, prototype = ljd.rawdump.parser.parse(f)
    ast = decompile(header, prototype)
    fout = io.StringIO()
    ljd.lua.writer.write(fout, ast)
    return fout.getvalue()


def process_folder(in_dir, out_dir, update_outputname=None):
    from concurrent.futures.process import ProcessPoolExecutor
    from pathlib import Path

    start = time.time()

    in_dir = Path(in_dir)
    out_dir = Path(out_dir)

    executor = ProcessPoolExecutor()
    fs = []
    for root, _, names in os.walk(in_dir):
        root = Path(root)
        reldir = root.relative_to(in_dir)
        out_root = out_dir / reldir
        out_root.mkdir(parents=True, exist_ok=True)

        for name in names:
            relpath = reldir / name
            path_in = root / name
            if update_outputname is not None:
                out_name = update_outputname(name)
            else:
                out_name = Path(name).with_suffix('.lua')
            path_out = out_root / out_name
            f = executor.submit(process_file, str(path_in), str(path_out))
            f.path = str(relpath)
            fs.append(f)
    failed = []
    success = []
    for f in fs:
        try:
            f.result()
            logger.debug("SUCCESS %s" % f.path)
            success.append(f.path)
        except Exception as e:
            failed.append([f.path, e])

    dt = time.time() - start
    for path, e in failed:
        logger.info("FAILED %s %r", path, e)
    logger.warning(
        "Decompile folder %s -> %s: success %s, fail %s in %.3fs",
        in_dir,
        out_dir,
        len(success),
        len(failed),
        dt,
    )
    return success

# use LuaJIT-2.0.1 as default target
set_luajit_version(21)


if __name__ == '__main__':
    set_luajit_version(21)
    process_folder(sys.argv[1], sys.argv[2])
