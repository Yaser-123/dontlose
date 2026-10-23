from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger("dontlose.notify")

APP_ID = "DontLose.Desktop"
_claimed = False
_warned = False


def notifications_enabled() -> bool:
    """Whether Windows is allowing app notifications on this computer."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\PushNotifications",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ToastEnabled")
        return int(value) != 0
    except OSError:
        return True


def claim_app_id() -> None:
    global _claimed
    if _claimed or sys.platform != "win32":
        return
    try:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()
        shell.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        _claimed = True
    except Exception:
        logger.exception("Could not register Don'tLose with Windows notifications")


def _shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Don'tLose.lnk"


def _ensure_shortcut(launch: str) -> None:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    path = _shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    pythoncom.CoInitialize()
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLink,
    )
    link.SetPath(sys.executable)
    link.SetArguments(f'-c "import webbrowser; webbrowser.open({launch!r})"')
    link.SetDescription("Don'tLose")
    link.SetShowCmd(0)
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), True)


def show_toast(title: str, message: str, launch: str = "") -> bool:
    """Post a Windows notification. Returns False when this computer can't show one."""
    global _warned
    if sys.platform != "win32":
        return False
    destination = launch or "http://localhost:3000/reminders"
    try:
        claim_app_id()
        _ensure_shortcut(destination)
        if not notifications_enabled():
            if not _warned:
                logger.warning("Windows notifications are turned off, so Don'tLose cannot pop up a reminder.")
                _warned = True
            return False
        from winrt.windows.data.xml.dom import XmlDocument
        from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager

        document = XmlDocument()
        document.load_xml(
            "<toast activationType=\"protocol\" launch=\"%s\" duration=\"long\">"
            "<visual><binding template=\"ToastGeneric\"><text>%s</text><text>%s</text></binding></visual>"
            "<audio src=\"ms-winsoundevent:Notification.Reminder\" />"
            "</toast>"
            % (
                escape(destination, {"\"": "&quot;"}),
                escape(title or "Don'tLose"),
                escape(message or "A reminder is due."),
            )
        )
        notifier = ToastNotificationManager.create_toast_notifier_with_id(APP_ID)
        if int(notifier.setting) != 0:
            if not _warned:
                logger.warning("Windows is not showing Don'tLose notifications (setting %s).", notifier.setting)
                _warned = True
            return False
        notifier.show(ToastNotification(document))
        return True
    except Exception:
        logger.exception("Windows notification failed")
        return False
