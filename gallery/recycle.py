"""Recycle-only Windows operations with per-item COM progress and vetoed permanent deletion."""

import os


def recycle(path):
    if os.name != 'nt':
        raise OSError('Recycle Bin operations require Windows')
    import pythoncom
    import pywintypes
    from win32com.server.policy import DesignatedWrapPolicy
    from win32com.shell import shell, shellcon

    class Sink(DesignatedWrapPolicy):
        _com_interfaces_ = [shell.IID_IFileOperationProgressSink]
        _public_methods_ = ['StartOperations', 'FinishOperations', 'PreRenameItem', 'PostRenameItem',
                           'PreMoveItem', 'PostMoveItem', 'PreCopyItem', 'PostCopyItem', 'PreDeleteItem',
                           'PostDeleteItem', 'PreNewItem', 'PostNewItem', 'UpdateProgress', 'ResetTimer',
                           'PauseTimer', 'ResumeTimer']

        def __init__(self):
            self._wrap_(self)
            self.result = None
            self.recycled = False

        def PreDeleteItem(self, flags, item):
            if not flags & shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE:
                from win32com.server.exception import COMException
                raise COMException('Permanent fallback is forbidden', scode=-2147467260)
            return 0

        def PostDeleteItem(self, flags, item, result, new_item):
            self.result = result
            self.recycled = new_item is not None

    pythoncom.CoInitialize()
    try:
        sink = Sink()
        progress = pythoncom.WrapObject(sink, shell.IID_IFileOperationProgressSink)
        operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None, pythoncom.CLSCTX_ALL,
                                               shell.IID_IFileOperation)
        operation.SetOperationFlags(shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI | shellcon.FOFX_EARLYFAILURE
                                   | 0x00080000 | 0x20000000)
        item = shell.SHCreateItemFromParsingName(str(path), None, shell.IID_IShellItem)
        operation.DeleteItem(item, progress)
        operation.PerformOperations()
        if (operation.GetAnyOperationsAborted() or sink.result is None or sink.result < 0
                or sink.result >= 0x80000000 or not sink.recycled):
            raise OSError(f'Recycling was not confirmed (HRESULT={sink.result}); permanent fallback refused')
        if path.exists():
            raise OSError('Source still exists after recycling')
    except pywintypes.com_error as exc:
        raise OSError(f'Recycle Bin operation failed: {exc}') from exc
    finally:
        pythoncom.CoUninitialize()
