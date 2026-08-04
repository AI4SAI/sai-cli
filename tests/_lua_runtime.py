from __future__ import annotations

import ctypes
from ctypes.util import find_library
from functools import lru_cache


@lru_cache(maxsize=1)
def _lua() -> ctypes.CDLL:
    library_name = find_library("lua5.4") or find_library("lua5.3")
    if not library_name:
        raise RuntimeError("liblua 5.3 or 5.4 is required for job_submit.lua tests")
    library = ctypes.CDLL(library_name)
    library.luaL_newstate.restype = ctypes.c_void_p
    library.luaL_openlibs.argtypes = [ctypes.c_void_p]
    library.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    library.luaL_loadstring.restype = ctypes.c_int
    library.lua_pcallk.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_longlong,
        ctypes.c_void_p,
    ]
    library.lua_pcallk.restype = ctypes.c_int
    library.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    library.lua_tolstring.restype = ctypes.c_void_p
    library.lua_close.argtypes = [ctypes.c_void_p]
    return library


def run_lua(chunk: str) -> None:
    library = _lua()
    state = library.luaL_newstate()
    if not state:
        raise AssertionError("could not create Lua state")
    try:
        library.luaL_openlibs(state)
        status = library.luaL_loadstring(state, chunk.encode("utf-8"))
        if status == 0:
            status = library.lua_pcallk(state, 0, 0, 0, 0, None)
        if status != 0:
            length = ctypes.c_size_t()
            pointer = library.lua_tolstring(state, -1, ctypes.byref(length))
            message = ctypes.string_at(pointer, length.value).decode("utf-8", errors="replace") if pointer else "unknown Lua error"
            raise AssertionError(message)
    finally:
        library.lua_close(state)
