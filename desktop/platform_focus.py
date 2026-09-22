from __future__ import annotations

import ctypes
import sys
from typing import Optional

from PySide6.QtWidgets import QWidget


def activate_application(
    window: Optional[QWidget] = None,
) -> None:
    if (
        sys.platform == "darwin"
        and getattr(sys, "frozen", False)
    ):
        _activate_macos_foreground()

    if window is None:
        return

    window.raise_()
    window.activateWindow()
    handle = window.windowHandle()
    if handle is not None:
        handle.requestActivate()


def _activate_macos_foreground() -> None:
    try:
        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/"
            "AppKit.framework/AppKit"
        )
        objc = ctypes.cdll.LoadLibrary(
            "/usr/lib/libobjc.A.dylib"
        )

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [
            ctypes.c_char_p
        ]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [
            ctypes.c_char_p
        ]

        send0 = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(
            ("objc_msgSend", objc)
        )
        send_bool = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_bool,
        )(
            ("objc_msgSend", objc)
        )

        app_class = objc.objc_getClass(
            b"NSApplication"
        )
        app = send0(
            app_class,
            objc.sel_registerName(
                b"sharedApplication"
            ),
        )
        send_bool(
            app,
            objc.sel_registerName(
                b"activateIgnoringOtherApps:"
            ),
            True,
        )
    except Exception:
        pass
